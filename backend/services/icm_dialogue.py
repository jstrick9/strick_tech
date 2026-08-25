"""Dialogue → workspace. Extract ICM structure from how someone describes work.

Build mode, step 1, from Van Clief's icm-architect:

    "Extract the structure from dialogue. The structure is already in how the
     person describes the work -- don't impose a shape, surface theirs.
     Their pauses become stage boundaries. Their 'I always check X before Y'
     become human gates. Their 'it always has to sound like / follow Z'
     becomes factory reference material."

This is the onboarding move that makes the methodology usable by someone who
has never heard of it. They describe their work in their own words; the shape
they are already living gets named back to them for confirmation.

WHY THIS IS DELIBERATELY NOT AN LLM CALL

Extraction here is lexical and rule-based, and that is a design decision rather
than a limitation:

  * It must work with no API key configured, on first run, before the user has
    connected a provider. Onboarding that requires credentials is not
    onboarding.
  * Every extraction cites the phrase that produced it. A user confirming a
    proposed structure needs to see "stage 2 because you said 'then I draft'",
    not a black box that is usually right.
  * It is a PROPOSAL awaiting confirmation, not an answer. The canon's whole
    posture is propose-then-confirm, so a fast, explainable, wrong-sometimes
    extractor a human corrects beats a slow, opaque, wrong-sometimes one.

An LLM pass can be layered on later as an enrichment; the contract here is that
the deterministic path always produces something reviewable.

THE GUARDRAIL

    "Don't over-structure. The ladder runs: chat -> saved prompt/skill ->
     folders + one agent. A workspace for a thing done twice is scaffolding,
     not architecture."

So `analyse()` can and does return a recommendation NOT to build a workspace.
A tool that only ever says yes is a tool that produces empty folders.
"""

from __future__ import annotations

import re
from typing import Any

# ── form selection ────────────────────────────────────────────────────────────
# "Ask one question first: what is the repeating unit of work?" Each form is
# matched on the vocabulary people actually use when they have that unit.
FORM_SIGNALS: dict[str, tuple[str, ...]] = {
    'pipeline': (
        'every week', 'every month', 'each week', 'weekly', 'monthly', 'daily',
        'every time', 'each time', 'same process', 'same steps', 'pipeline',
        'workflow', 'production line', 'repeat', 'routine', 'each episode',
    ),
    'umbrella': (
        'several different', 'a few different', 'different kinds of',
        'multiple pipelines', 'same brand', 'same voice across',
        'different types of content', 'various projects',
    ),
    'record_library': (
        'each client', 'per client', 'each customer', 'each patient',
        'each student', 'per project', 'each candidate', 'each deal',
        'one folder per', 'each session', 'every client', 'case file',
    ),
    'knowledge_bundle': (
        'second brain', 'knowledge base', 'my notes', 'wiki', 'research notes',
        'everything i know', 'reference library', 'vault', 'zettelkasten',
    ),
    'context_map': (
        'my team', 'our team', 'the company', 'departments', 'who does what',
        'org chart', 'handoffs between', 'across teams',
    ),
    'system_map': (
        'this repo', 'the codebase', 'my code', 'existing folder', 'audit',
        'map this', 'legacy', 'someone else wrote',
    ),
}

FORM_LABELS = {
    'pipeline': 'Pipeline — a production line',
    'umbrella': 'Umbrella — a portfolio of pipelines',
    'record_library': 'Record library — the unit is a record',
    'knowledge_bundle': 'Knowledge bundle — the product is the knowledge',
    'context_map': 'Context map — an organisation as a graph',
    'system_map': 'System map — a folder later agents will edit',
}

FORM_WHY = {
    'pipeline': 'the same sequence runs repeatedly, producing a deliverable each run',
    'umbrella': 'several distinct production lines share one identity and reference layer',
    'record_library': 'the repeating unit is a record that accumulates, not a run',
    'knowledge_bundle': 'the deliverable is a navigable body of knowledge',
    'context_map': 'the subject is an organisation: teams, processes and handoffs',
    'system_map': 'the subject is a tree someone will change, and needs change-impact',
}

# ── stage extraction ──────────────────────────────────────────────────────────
# Sequence markers: the words people use when narrating a process in order.
# "Their pauses become stage boundaries."
SEQUENCE_MARKERS = (
    'first', 'firstly', 'to start', 'start by', 'begin by', 'initially',
    'then', 'next', 'after that', 'afterwards', 'once that', 'second',
    'secondly', 'third', 'thirdly', 'finally', 'lastly', 'at the end',
    'eventually', 'subsequently', 'and then', 'later',
)
_SEQ_RE = re.compile(
    r'(?:^|[.;,]\s*|\band\s+)(' + '|'.join(re.escape(m) for m in SEQUENCE_MARKERS) + r')\b',
    re.I,
)

# "I always check X before Y" -> a human gate.
GATE_MARKERS = (
    'i check', 'i review', 'i approve', 'i verify', 'i confirm', 'i look over',
    'i read through', 'i sign off', 'i proof', 'i always check', 'i make sure',
    'we review', 'we approve', 'we check', 'needs approval', 'gets approved',
    'before i send', 'before sending', 'before publishing', 'before it goes',
    'manually check', 'human review', 'i edit', 'i tweak',
)

# "It always has to sound like / follow Z" -> factory reference material.
FACTORY_MARKERS = (
    'always has to', 'always needs to', 'has to sound', 'has to follow',
    'must follow', 'must match', 'brand', 'tone of voice', 'style guide',
    'our voice', 'house style', 'template', 'guidelines', 'conventions',
    'the rules', 'standard format', 'consistent', 'every time it must',
)

# The verb that names what a stage DOES. Used to slug the stage folder.
STAGE_VERBS = (
    'research', 'gather', 'collect', 'find', 'source', 'interview',
    'outline', 'plan', 'spec', 'design', 'draft', 'write', 'script',
    'edit', 'revise', 'polish', 'review', 'check', 'proof',
    'build', 'produce', 'render', 'generate', 'create', 'make',
    'record', 'film', 'shoot', 'animate', 'export',
    'publish', 'send', 'ship', 'deploy', 'post', 'deliver', 'schedule',
    'analyse', 'analyze', 'summarise', 'summarize', 'report', 'format',
    'test', 'validate', 'approve', 'file', 'invoice', 'bill',
    # Common everyday phrasings people reach for before the formal verb.
    # Omitting these made the slug fall through to whatever noun came first
    # ("week"), so a real stage got an unreadable name.
    'pull', 'sort', 'pick', 'choose', 'select', 'read', 'reconcile',
    'update', 'upload', 'import', 'clean', 'tag', 'label', 'log', 'track',
)

# Words that describe *doing work* rather than naming the subject of the work.
# These are never useful as routing triggers: every description contains them.
GENERIC_PROCESS_WORDS = frozenset({
    'always', 'never', 'every', 'each', 'thing', 'things', 'stuff', 'time',
    'times', 'week', 'weeks', 'month', 'months', 'week\'s', 'again', 'about',
    'through', 'worth', 'three', 'four', 'five', 'able', 'quickly', 'often',
    'usually', 'sometimes', 'really', 'quite', 'need', 'needs', 'want',
    'wants', 'like', 'good', 'better', 'best', 'sure', 'that', 'this',
    'them', 'they', 'their', 'there', 'here', 'when', 'where', 'what',
    'which', 'while', 'with', 'from', 'into', 'over', 'after', 'before',
    'down', 'loud', 'more', 'most', 'much', 'many', 'some', 'been', 'have',
    'having', 'does', 'doing', 'done', 'goes', 'going', 'gets', 'give',
    'own', 'out', 'set', 'same', 'whole', 'part', 'bit', 'lot',
})

# Words that can never name a stage: prepositions, auxiliaries and pronouns.
# A stage folder is read as "the job done here", so it must be a job.
NON_NAMING_WORDS = frozenset({
    'through', 'about', 'after', 'before', 'until', 'while', 'with', 'from',
    'into', 'onto', 'over', 'under', 'against', 'between', 'across', 'along',
    'around', 'above', 'below', 'them', 'they', 'their', 'this', 'that',
    'these', 'those', 'there', 'here', 'when', 'where', 'which', 'what',
    'would', 'could', 'should', 'might', 'must', 'have', 'been', 'being',
    'does', 'doing', 'goes', 'going', 'gets', 'getting', 'each', 'every',
    'some', 'much', 'many', 'more', 'most', 'also', 'just', 'then', 'than',
    'very', 'really', 'quite', 'again', 'back', 'down', 'once',
})

STOP_FRAGMENT = re.compile(r'^\W*$')
MIN_WORDS_FOR_WORKSPACE = 12
MAX_STAGES = 8


def _sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+|\n+', str(text or ''))
    return [p.strip() for p in parts if p.strip()]


def _find_phrases(text: str, markers: tuple[str, ...]) -> list[str]:
    """Return the sentences containing any marker, with the marker cited."""
    hits: list[str] = []
    for sent in _sentences(text):
        low = sent.lower()
        for m in markers:
            if m in low:
                if sent not in hits:
                    hits.append(sent)
                break
    return hits


def _slug_verb(fragment: str) -> str:
    """Name a stage after the work it does, preferring an explicit verb."""
    low = fragment.lower()
    for verb in STAGE_VERBS:
        if re.search(r'\b' + re.escape(verb) + r'\w*\b', low):
            return verb
    # Fallback: the first word that could plausibly name a job. Without the
    # filter this returned prepositions -- "go through the receipts" produced
    # a stage folder literally called "through", which is not a job and is not
    # readable as one. A generic "stage" beats a confidently wrong name.
    words = [w for w in re.findall(r"[a-z]+", low)
             if len(w) > 3 and w not in NON_NAMING_WORDS]
    return words[0] if words else 'stage'


def _weigh(signal: str) -> float:
    """Score a signal by how specific it is, not merely how long.

    A flat "multi-word beats single-word" rule got this wrong on a real
    description: "Each client gets their own folder ... and my notes from every
    call" scored as a knowledge bundle, because the incidental phrase "my
    notes" outweighed "each client" -- which is the actual repeating unit and
    the whole basis of form selection. Distinctive phrases now outrank generic
    ones regardless of length.
    """
    return 3.0 if signal in HIGH_SIGNAL else (2.0 if ' ' in signal else 1.0)


# Phrases that name the repeating unit outright. These are the answer to the
# form-selection question ("what is the repeating unit of work?") rather than
# atmosphere around it, so they dominate.
HIGH_SIGNAL = frozenset({
    'each client', 'per client', 'each customer', 'each patient', 'each student',
    'per project', 'each candidate', 'each deal', 'one folder per',
    'each session', 'every client', 'case file',
    'second brain', 'knowledge base', 'zettelkasten',
    'org chart', 'who does what', 'handoffs between', 'across teams',
    'this repo', 'the codebase', 'someone else wrote',
    'production line', 'multiple pipelines',
})

# Signals so generic they should never decide a form on their own.
SIGNAL_WEIGHTS: dict[str, float] = {
    'my notes': 0.5,
    'template': 0.5,
    'workflow': 0.5,
    'repeat': 0.5,
    'routine': 0.5,
    'audit': 0.5,
    'vault': 0.5,
    'wiki': 1.0,
}

def detect_form(text: str) -> dict[str, Any]:
    """Pick the form by scoring the vocabulary of the repeating unit."""
    low = ' ' + ' '.join(str(text or '').lower().split()) + ' '
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for form, signals in FORM_SIGNALS.items():
        for sig in signals:
            if sig in low:
                scores[form] = scores.get(form, 0.0) + SIGNAL_WEIGHTS.get(sig, _weigh(sig))
                evidence.setdefault(form, []).append(sig)

    if not scores:
        # Pipeline is the paper's canonical shape and the safest default, but
        # say so rather than presenting a guess as a finding.
        return {
            'form': 'pipeline',
            'label': FORM_LABELS['pipeline'],
            'why': 'no clear signal for another form; pipeline is the default shape',
            'confident': False,
            'evidence': [],
            'runners_up': [],
        }

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top, top_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    return {
        'form': top,
        'label': FORM_LABELS[top],
        'why': FORM_WHY[top],
        # A near-tie is worth surfacing: forms compose, and the user may want
        # both. Claiming confidence we do not have is how the wrong skeleton
        # gets built and then lived with.
        'confident': top_score >= 2.0 and top_score > second,
        'evidence': evidence.get(top, [])[:5],
        'runners_up': [
            {'form': f, 'label': FORM_LABELS[f], 'score': s} for f, s in ranked[1:3]
        ],
    }


def extract_stages(text: str) -> list[dict[str, Any]]:
    """Split the narrative at sequence markers. Their pauses ARE the boundaries."""
    clean = ' '.join(str(text or '').split())
    if not clean:
        return []

    cuts: list[tuple[int, str]] = []
    for m in _SEQ_RE.finditer(clean):
        cuts.append((m.start(1), m.group(1).lower()))

    fragments: list[tuple[str, str]] = []
    if not cuts:
        fragments = [(clean, '')]
    else:
        if cuts[0][0] > 0:
            head = clean[:cuts[0][0]].strip(' .,;')
            if head and not STOP_FRAGMENT.match(head):
                fragments.append((head, ''))
        for i, (pos, marker) in enumerate(cuts):
            end = cuts[i + 1][0] if i + 1 < len(cuts) else len(clean)
            body = clean[pos + len(marker):end].strip(' .,;')
            if body and not STOP_FRAGMENT.match(body):
                fragments.append((body, marker))

    stages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for body, marker in fragments:
        if len(body.split()) < 2:
            continue
        name = _slug_verb(body)
        # Two fragments naming the same verb are one stage described twice, not
        # two stages. "One stage, one job" cuts both ways.
        if name in seen:
            continue
        seen.add(name)
        stages.append({
            'name': name,
            'said': body[:180],
            'marker': marker,
            'why': f'you said {marker!r}' if marker else 'the opening of your description',
        })
        if len(stages) >= MAX_STAGES:
            break
    return stages


def analyse(text: str) -> dict[str, Any]:
    """Turn a description of work into a proposed ICM workspace.

    Returns a PROPOSAL. Nothing is created here -- confirmation is a separate,
    explicit call, because "propose before building" is the same human gate the
    rest of this system honours.
    """
    text = str(text or '').strip()
    words = len(text.split())

    form = detect_form(text)
    stages = extract_stages(text)
    gates = _find_phrases(text, GATE_MARKERS)
    factory = _find_phrases(text, FACTORY_MARKERS)

    # ── the over-structuring guardrail ──
    # "A workspace for a thing done twice is scaffolding, not architecture."
    recommend = True
    advice = ''
    if words < MIN_WORDS_FOR_WORKSPACE:
        recommend = False
        advice = (
            'That is too short to find a shape in. Walk me through one run '
            'start to finish: where do you stop and check something?'
        )
    elif len(stages) < 2 and form['form'] == 'pipeline':
        # The stage-count guard is a PIPELINE guard. Only a pipeline is made of
        # stages; a record library is made of records, a knowledge bundle of
        # layers. Applying it to every form refused a perfectly good record
        # library with advice about pipelines -- found when the form builders
        # were wired in, because until then every form WAS a pipeline.
        recommend = False
        advice = (
            'This reads like a single step, not a pipeline. If it fits in one '
            'saved prompt, use a prompt -- a workspace for a one-step job is '
            'scaffolding, not architecture. Describe what happens before and '
            'after it if there is more.'
        )

    return {
        'ok': True,
        'word_count': words,
        'form': form,
        'stages': stages,
        'human_gates': [{'said': g, 'becomes': 'a human check in the stage contract'}
                        for g in gates[:6]],
        'factory': [{'said': f, 'becomes': 'reference material in _shared/'}
                    for f in factory[:6]],
        'recommend_workspace': recommend,
        'advice': advice,
        # The questions the canon says to ask, minus any this description has
        # already answered. Asking what someone just told you is how an
        # onboarding wizard earns its reputation.
        'follow_up': _follow_up(stages, gates, factory),
    }


def _follow_up(stages: list, gates: list, factory: list) -> list[str]:
    qs: list[str] = []
    if len(stages) < 3:
        qs.append('Walk me through one run start to finish — what happens first, then what?')
    if not gates:
        qs.append('Where do you stop and check something before continuing?')
    if not factory:
        qs.append('What stays the same every run — voice, rules, brand, a format?')
    qs.append('What does "done" look like — what artifact leaves at the end?')
    return qs[:3]


def to_scaffold_args(analysis: dict[str, Any], name: str = '') -> dict[str, Any]:
    """Turn a confirmed analysis into arguments for icm.scaffold()."""
    stages = [s['name'] for s in analysis.get('stages', [])]
    return {
        'name': name or 'workspace',
        'description': analysis.get('form', {}).get('why', ''),
        'stages': stages,
    }


def routes_block(text: str, limit: int = 6) -> str:
    """Propose a `## Routes` section from the subject nouns in the description.

    Wires the new workspace into the entry router immediately. A workspace with
    no declared routes can only be reached by name, which is exactly the
    "nobody can find the right folder" problem the router exists to solve --
    so scaffolding one without routes would reintroduce it at birth.

    Selection is NOT by raw frequency. An earlier draft ranked words by count
    with a >=2 threshold and, on a newsletter description, proposed
    "always, links" while dropping "newsletter" entirely -- the subject was
    mentioned once and the filler twice. Frequency measures how much a word is
    repeated, not whether it names the thing. Instead: drop stopwords, stage
    verbs, sequence markers and generic process filler, then prefer the nouns
    the description opens with, since people name their subject early.
    """
    from .icm_router import STOPWORDS

    raw = str(text or '')
    words = re.findall(r"[a-z][a-z'-]{3,}", raw.lower())
    if not words:
        return ''

    skip = (set(STOPWORDS) | set(STAGE_VERBS) | set(SEQUENCE_MARKERS)
            | GENERIC_PROCESS_WORDS)
    freq: dict[str, int] = {}
    order: list[str] = []
    for w in words:
        # NOT rstrip("'s") -- that strips a CHARACTER SET from the end, so
        # "always" became "alway" and "links" became "link", which both
        # mangled the word and defeated the stopword check it was feeding.
        base = w[:-2] if w.endswith("'s") else w
        if base in skip or len(base) < 4:
            continue
        if base not in freq:
            order.append(base)
        freq[base] = freq.get(base, 0) + 1

    if not order:
        return ''

    # Rank by position first (subjects get named early), with repetition as a
    # tie-breaker rather than the primary signal.
    picks = sorted(order, key=lambda w: (order.index(w) - 2 * (freq[w] - 1)))[:limit]
    return '\n## Routes\n' + '\n'.join(f'- {w}' for w in picks) + '\n'
