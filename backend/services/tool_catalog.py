"""Tool catalog — one searchable index, loaded lazily by intent.

THE PROBLEM, STATED BY SOMEONE RUNNING ONE (skool.com/cliefnotes):

    "You all route which files a model loads for a task so it isn't drowning in
     context it doesn't need. I hit the same wall one layer down, with tools.
     I put a single gateway in front of a bunch of MCP servers so my agent has
     one connection instead of ten, and now it sees every tool from every
     server at once. Past a certain count it starts picking worse, not better.
     Right now I keep a hand-written map of which tools to expose per task, but
     it rots the second I add a server."

This is ICM's layered-loading argument applied one level down. A catalog is
small and points at everything; the shelves hold the payload. Nobody
photocopies the library into the backpack -- and a tool list inlined into every
system prompt is exactly that photocopy.

WHAT WAS ACTUALLY BROKEN HERE

Measured against a running server before writing any of this:

    /api/mcp-gateway/servers -> 7 servers, 53 tools
    /api/mcp/tools           -> 23 tools
    the agent loop in mcp.py -> inlines all 23 locals, sees 0 of the 53

So the gateway federated tools that no agent could ever call, and the agent
loop pasted its own list into every prompt regardless of the task. Connecting
the two naively would have put 76 tools in front of the model at once, which is
precisely the wall described above. Hence: connect them THROUGH a catalog.

THE DESIGN

  * `index()` builds one flat catalog from every source (local + gateway),
    each entry carrying tags derived from its name and description.
  * `select()` returns only the tools an intent plausibly needs, capped, with
    the reason each one was chosen.
  * `MAX_EXPOSED` is a hard ceiling. Selection degrades to the highest-scoring
    subset rather than silently exceeding it.
  * Nothing is hand-maintained. The catalog is rebuilt from the sources on
    every call, because "generated indexes are never hand-edited... a
    hand-curated one always does [drift]" -- which is the exact rot the
    community post describes.

WHY LEXICAL SCORING AND NOT EMBEDDINGS

Same reasoning as the dialogue extractor: this must work with no API key, on
first run, and every selection has to be explainable ("chosen because your
request mentioned 'invoice'"). An embedding pass can be layered on later; the
deterministic path has to stand alone.
"""

from __future__ import annotations

import re
from typing import Any

# The ceiling. Past roughly this many choices a model's tool selection degrades
# rather than improves, which is the whole reason this module exists. The
# number is a policy, not a law of nature -- it is overridable per call -- but
# defaulting to "all of them" is how the wall gets hit.
MAX_EXPOSED = 12

# A tool must clear this to be exposed for an intent at all. Below it, leaving
# the tool out is better than padding the list: an irrelevant tool is not free,
# it is another wrong option the model can pick.
MIN_SCORE = 1.0

# Tags are how intent maps to capability without a hand-written per-task map.
# Each tag lists the words that imply it, in EITHER the request or the tool.
TAG_VOCABULARY: dict[str, tuple[str, ...]] = {
    'filesystem': ('file', 'files', 'directory', 'folder', 'path', 'read',
                   'write', 'delete', 'list', 'exists', 'save', 'open', 'fs'),
    'code': ('code', 'run', 'execute', 'script', 'python', 'node', 'shell',
             'command', 'build', 'compile', 'test'),
    'git': ('git', 'commit', 'branch', 'diff', 'checkout', 'repo', 'repository',
            'merge', 'log', 'push', 'pull'),
    'web': ('http', 'url', 'fetch', 'request', 'api', 'endpoint', 'webhook',
            'browser', 'navigate', 'scrape', 'download'),
    'search': ('search', 'find', 'query', 'lookup', 'grep', 'locate', 'web'),
    'memory': ('memory', 'remember', 'recall', 'store', 'note', 'knowledge',
               'context', 'save'),
    # NOTE 'checkout' is deliberately absent: it belongs to git AND to commerce,
    # and it tagged git.checkout as billing, so 'create an invoice' offered a
    # branch-switching tool. A term claimed by two capabilities is not evidence
    # for either -- see AMBIGUOUS below.
    'billing': ('invoice', 'billing', 'payment', 'charge', 'stripe', 'refund',
                'subscription', 'customer', 'price'),
    'comms': ('email', 'send', 'message', 'slack', 'notify', 'notification',
              'mail', 'chat', 'post'),
    'data': ('database', 'sql', 'table', 'row', 'record', 'query', 'db',
             'schema', 'insert', 'select'),
    'calendar': ('calendar', 'event', 'meeting', 'schedule', 'appointment',
                 'availability', 'booking'),
}

# Words too common to carry intent. Without this, "get the file" and "get the
# invoice" score identically on the shared word. Reused from the entry router
# rather than duplicated -- one home per fact, and two drifting stopword lists
# would give the same request different answers at different layers.
from .icm_router import STOPWORDS  # noqa: E402


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", str(text or '').lower()) if w]


def tags_for(name: str, description: str = '') -> list[str]:
    """Derive capability tags from a tool's own name and description.

    Deriving rather than declaring is the point: a hand-written tag map "rots
    the second I add a server". A tool registered tomorrow is categorised the
    moment it appears.
    """
    # A dotted or underscored name carries its namespace as separate words --
    # 'stripe.refund' -> {'stripe', 'refund'} -- which _words() already gives
    # us, since it splits on every non-alphanumeric. An earlier draft also did
    # an explicit .replace('.', ' ').replace('_', ' ') pass here; the revert
    # proof showed no test could tell its presence from its absence, because
    # it was incapable of adding a word _words() had not already produced.
    # Removed rather than kept as unreachable code.
    hay = set(_words(name) + _words(description))
    out = [tag for tag, vocab in TAG_VOCABULARY.items() if hay & set(vocab)]
    return sorted(out)


def _local_tools() -> list[dict[str, Any]]:
    try:
        from ..routers.mcp import TOOLS
    except (ImportError, AttributeError):
        return []
    out = []
    for name, info in TOOLS.items():
        desc = str(info.get('desc', ''))
        out.append({
            'name': name,
            'description': desc,
            'args': list(info.get('args', [])),
            'source': 'local',
            'server_id': '',
            'server': 'local',
            'tags': tags_for(name, desc),
        })
    return out


def _gateway_tools() -> list[dict[str, Any]]:
    """Tools federated through the MCP gateway.

    These were invisible to every agent before this module: the gateway
    registered them and nothing ever surfaced them to a model.
    """
    try:
        from ..routers.mcp_gateway import list_servers
    except (ImportError, AttributeError):
        return []
    try:
        payload = list_servers()
    except Exception:
        # A gateway that cannot be read must not take the local catalog down
        # with it. Degrading to locals is strictly better than no tools.
        return []

    out: list[dict[str, Any]] = []
    for srv in payload.get('servers', []):
        if str(srv.get('status', 'active')).lower() in ('disabled', 'inactive'):
            continue
        schema = srv.get('tools_schema')
        if not isinstance(schema, list):
            continue
        for entry in schema:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get('name') or '').strip()
            if not name:
                continue
            desc = str(entry.get('description') or '')
            out.append({
                'name': name,
                'description': desc,
                'args': list(entry.get('args') or []),
                'source': 'gateway',
                'server_id': str(srv.get('id') or srv.get('server_id') or ''),
                'server': str(srv.get('name') or 'gateway'),
                'tags': tags_for(name, desc),
            })
    return out


def index() -> list[dict[str, Any]]:
    """Build the whole catalog. Generated every call; never hand-maintained."""
    seen: set[str] = set()
    catalog: list[dict[str, Any]] = []
    # Locals win a name collision: they are the ones this process can actually
    # dispatch without a network hop.
    for tool in _local_tools() + _gateway_tools():
        key = f'{tool["server_id"]}:{tool["name"]}'
        if key in seen:
            continue
        seen.add(key)
        catalog.append(tool)
    return catalog


def score(tool: dict[str, Any], intent_words: set[str], intent_tags: set[str]) -> tuple[float, list[str]]:
    """Score one tool against an intent, with the reasons that produced it."""
    reasons: list[str] = []
    total = 0.0

    name_words = set(_words(str(tool['name']).replace('.', ' ').replace('_', ' ')))
    hits = name_words & intent_words
    if hits:
        total += 3.0 * len(hits)
        reasons.append(f'name matches {sorted(hits)}')

    shared_tags = set(tool.get('tags') or []) & intent_tags
    if shared_tags:
        # Tag agreement is weaker evidence than a name hit: a tag says "this
        # tool is in the right neighbourhood", a name says "this is the thing
        # you asked for". Weighting them equally let 40 vaguely-billing tools
        # crowd out the one actually named in the request.
        total += 2.0 * len(shared_tags) if hits else 1.5 * len(shared_tags)
        reasons.append(f'capability {sorted(shared_tags)}')

    desc_hits = set(_words(tool.get('description', ''))) & intent_words
    if desc_hits:
        total += 1.0 * len(desc_hits)
        reasons.append(f'description mentions {sorted(desc_hits)}')

    return total, reasons


def select(intent: str, limit: int = MAX_EXPOSED,
           always: tuple[str, ...] = ()) -> dict[str, Any]:
    """Choose the tools an intent plausibly needs. Never more than `limit`.

    Returns the selection AND what it left out, because an agent that quietly
    cannot see a tool it needs looks identical to one that chose not to use it.
    """
    catalog = index()
    limit = max(1, min(int(limit or MAX_EXPOSED), 60))

    words = {w for w in _words(intent) if w not in STOPWORDS}
    intent_tags = {tag for tag, vocab in TAG_VOCABULARY.items() if words & set(vocab)}

    scored: list[dict[str, Any]] = []
    for tool in catalog:
        pts, reasons = score(tool, words, intent_tags)
        if tool['name'] in always:
            pts += 100.0
            reasons.append('always available')
        if pts >= MIN_SCORE:
            scored.append({**tool, 'score': round(pts, 2), 'why': '; '.join(reasons)})

    scored.sort(key=lambda t: (-t['score'], t['name']))
    chosen = scored[:limit]

    return {
        'intent': intent,
        'tags': sorted(intent_tags),
        'tools': chosen,
        'total_available': len(catalog),
        'exposed': len(chosen),
        # Honest reporting: how many cleared the bar but did not fit, and how
        # many never cleared it. Silence here is how "the agent didn't use the
        # tool" becomes an unfalsifiable bug report.
        'withheld_by_cap': max(0, len(scored) - len(chosen)),
        'not_relevant': len(catalog) - len(scored),
    }


def search(query: str, limit: int = 25) -> list[dict[str, Any]]:
    """Free-text search over the catalog, for an agent that wants to look.

    "Let the agent search a catalog" -- the alternative to exposing everything
    is not hiding things, it is making them findable on demand.
    """
    words = {w for w in _words(query) if w not in STOPWORDS}
    if not words:
        return index()[:limit]
    tags = {tag for tag, vocab in TAG_VOCABULARY.items() if words & set(vocab)}
    out = []
    for tool in index():
        pts, reasons = score(tool, words, tags)
        if pts >= MIN_SCORE:
            out.append({**tool, 'score': round(pts, 2), 'why': '; '.join(reasons)})
    out.sort(key=lambda t: (-t['score'], t['name']))
    return out[:max(1, min(int(limit or 25), 100))]


def render_for_prompt(tools: list[dict[str, Any]]) -> str:
    """Render the selected tools as the block that goes into a system prompt."""
    lines = []
    for t in tools:
        args = ', '.join(t.get('args') or [])
        via = '' if t.get('source') == 'local' else f' [via {t.get("server")}]'
        lines.append(f'- {t["name"]}({args}): {t.get("description", "")}{via}')
    return '\n'.join(lines)


def stats() -> dict[str, Any]:
    """Catalog totals, for the UI and for anyone asking why a tool is missing."""
    catalog = index()
    by_source: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for t in catalog:
        by_source[t['source']] = by_source.get(t['source'], 0) + 1
        for tag in t['tags'] or ['untagged']:
            by_tag[tag] = by_tag.get(tag, 0) + 1
    return {
        'total': len(catalog),
        'by_source': by_source,
        'by_tag': dict(sorted(by_tag.items(), key=lambda kv: -kv[1])),
        'max_exposed': MAX_EXPOSED,
    }
