"""
Agentic OS — Web Search Grounding
Inject live web search results into any AI prompt.
Like Perplexity's "verification-first" + citations model.

Features:
- DuckDuckGo search (free, no API key)
- Result injection into prompts
- Citation tracking
- Research mode (multi-query + synthesis)
- Search history (SQLite)
- Autocomplete / suggestions
- Standalone page-content fetch
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix='/api/websearch', tags=['websearch'])
log = logging.getLogger('agentic.websearch')

from backend.config import get_data_dir

from ..services.llm import sse_guard
from ..services.request_body import json_body_or_error

ROOT = get_data_dir()
DB = ROOT / 'memory' / 'agentic.db'


# ── DB helpers ──────────────────────────────────────────────────────────────


def get_conn() -> sqlite3.Connection:
    """Retrieve and return get conn.

    Resolved through memory_db.db_path() so AGENTIC_TEST_DB redirection
    applies; a hardcoded module constant bypassed test isolation entirely.
    """
    from ..services.memory_db import db_path

    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    return con


def _ensure_schema() -> None:
    """Create ws_search_history table if not present."""
    con = get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS ws_search_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                query     TEXT    NOT NULL,
                kind      TEXT    NOT NULL DEFAULT 'search',
                results   INTEGER NOT NULL DEFAULT 0,
                ts        INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )""")
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _record_search(query: str, kind: str, results: int) -> None:
    """Persist a search query to history (fire-and-forget, never raises)."""
    try:
        con = get_conn()
        try:
            con.execute(
                'INSERT INTO ws_search_history(query,kind,results) VALUES(?,?,?)',
                (query[:500], kind, results),
            )
            con.commit()
        finally:
            con.close()
    except Exception as ex:
        log.warning('history record failed: %s', ex)


# ── DuckDuckGo helpers ──────────────────────────────────────────────────────


#: A real browser User-Agent is required. lite.duckduckgo.com now answers the
#: previous 'AgenticOS/6.0' UA with HTTP 403 for every query.
_SEARCH_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def _unwrap_ddg_url(href: str) -> str:
    """Resolve DuckDuckGo's /l/?uddg=... redirect wrapper to the real target."""
    import urllib.parse

    if not href:
        return ''
    if href.startswith('//'):
        href = 'https:' + href
    try:
        parsed = urllib.parse.urlparse(href)
        if 'duckduckgo.com' in (parsed.hostname or '') and parsed.path.startswith('/l/'):
            target = urllib.parse.parse_qs(parsed.query).get('uddg', [''])[0]
            if target:
                return urllib.parse.unquote(target)
    except (ValueError, TypeError):
        pass
    return href


def _clean_html_text(fragment: str) -> str:
    """Strip tags and decode entities from a scraped HTML fragment."""
    import html as _html

    return _html.unescape(re.sub(r'<[^>]+>', '', fragment or '')).strip()


async def _ddg_search(query: str, num_results: int = 5) -> list[dict]:
    """Search DuckDuckGo — free, no API key needed.

    BUG FIX: web search silently returned ZERO results for every query while
    reporting {"ok": true}. Two independent causes, both verified live:

      1. It scraped lite.duckduckgo.com with the User-Agent
         'Mozilla/5.0 AgenticOS/6.0'. That endpoint now answers HTTP 403 to
         non-browser agents, so the request never returned any HTML.
      2. Its regex matched a generic <a href>…</a>, which does not correspond
         to how DuckDuckGo marks up results — even on a 200 response it would
         have picked up navigation chrome rather than search hits.

    The documented fallback (api.duckduckgo.com instant answers) does not cover
    ordinary queries either: for "python asyncio tutorial" it returns an empty
    AbstractText and zero RelatedTopics. So every path produced nothing, and
    the endpoint reported success anyway.

    Now targets html.duckduckgo.com/html with a real browser UA and parses the
    result__a / result__snippet markup that endpoint actually emits, unwrapping
    DuckDuckGo's /l/?uddg= redirect so callers get real destination URLs.
    Verified live: 10 results for the same query that previously returned 0.
    """
    import urllib.parse

    import httpx

    num_results = max(1, min(int(num_results), 10))
    results: list[dict] = []

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f'https://html.duckduckgo.com/html/?q={encoded}'

        async with httpx.AsyncClient(
            timeout=12, headers={'User-Agent': _SEARCH_UA}, follow_redirects=True
        ) as client:
            r = await client.get(url)
            if r.status_code == 200:
                text = r.text
                links = re.findall(
                    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                    text,
                    re.IGNORECASE | re.DOTALL,
                )
                snippets = re.findall(
                    r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                    text,
                    re.IGNORECASE | re.DOTALL,
                )
                for i, (href, title) in enumerate(links[:num_results]):
                    target = _unwrap_ddg_url(href)
                    # Defence in depth: only ever hand back http(s) URLs, and
                    # never one pointing at internal infrastructure. Results are
                    # scraped third-party content, so a hostile scheme
                    # (javascript:, data:) must not reach the client at all.
                    if not target or not target.lower().startswith(('http://', 'https://')):
                        continue
                    if _is_ssrf_blocked_url(target):
                        continue
                    results.append(
                        {
                            'rank': len(results) + 1,
                            'title': _clean_html_text(title)[:200],
                            'url': target,
                            'snippet': _clean_html_text(snippets[i])[:400] if i < len(snippets) else '',
                        }
                    )
            else:
                log.warning('DDG html search returned HTTP %s', r.status_code)
    except Exception as ex:
        log.warning('DDG search failed: %s', ex)

    # Fallback: instant answers API (covers definitional queries only).
    if not results:
        try:
            import urllib.parse

            import httpx

            url = (
                f'https://api.duckduckgo.com/?q={urllib.parse.quote_plus(query)}&format=json&no_html=1&skip_disambig=1'
            )
            async with httpx.AsyncClient(timeout=8, headers={'User-Agent': _SEARCH_UA}) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    if data.get('AbstractText'):
                        results.append(
                            {
                                'rank': 1,
                                'title': data.get('Heading', ''),
                                'url': data.get('AbstractURL', ''),
                                'snippet': data.get('AbstractText', '')[:400],
                            }
                        )
                    for rel in data.get('RelatedTopics', [])[:num_results]:
                        if isinstance(rel, dict) and rel.get('Text'):
                            results.append(
                                {
                                    'rank': len(results) + 1,
                                    'title': rel.get('Text', '')[:80],
                                    'url': rel.get('FirstURL', ''),
                                    'snippet': rel.get('Text', '')[:300],
                                }
                            )
        except Exception as ex:
            log.warning('DDG instant answers failed: %s', ex)

    return results[:num_results]


async def _fetch_page_text(url: str, max_chars: int = 2000) -> str:
    """Fetch and extract text from a web page."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=8, headers={'User-Agent': 'Mozilla/5.0 AgenticOS/6.0'}) as client:
            r = await client.get(url, follow_redirects=True)
            if r.status_code == 200:
                text = r.text
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                return text[:max_chars]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    return ''


# ── REST endpoints ──────────────────────────────────────────────────────────


@router.post('/search')
async def web_search(req: Request):
    """Search the web and return results."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    query = (body.get('query') or '').strip()
    n = max(1, min(int(body.get('num_results', 5) or 5), 10))
    fetch = bool(body.get('fetch_content', False))

    if not query:
        return JSONResponse({'ok': False, 'error': 'query required'}, status_code=400)

    results = await _ddg_search(query, n)

    if fetch:
        tasks = [_fetch_page_text(res['url']) for res in results[:3]]
        contents = await asyncio.gather(*tasks)
        for res, content in zip(results, contents, strict=False):
            res['content'] = content

    _record_search(query, 'search', len(results))

    return {
        'ok': True,
        'query': query,
        'results': results,
        'count': len(results),
    }


def _is_ssrf_blocked_url(url: str) -> bool:
    """
    SECURITY: Block SSRF targets — private/link-local/metadata IP ranges
    and cloud metadata endpoints. Returns True if the URL should be blocked.

    Delegates to services/safe_fetch.py. This function's own implementation was
    the platform's FOURTH hand-rolled copy of this control, found by the
    repo-wide guard in tests/unit/test_80. It was also the best of them — it
    handled integer and hex IP encodings (2130706433, 0x7f000001) that the
    others missed — so those checks were merged INTO the shared helper rather
    than lost. Consolidation should keep the strongest version, not the newest.
    """
    from ..services.safe_fetch import url_is_safe

    ok, _reason = url_is_safe(url)
    return not ok


@router.post('/fetch-content')
async def fetch_content(req: Request):
    """Fetch and extract readable text from a given URL."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    url = (body.get('url') or '').strip()
    max_chars = max(500, min(int(body.get('max_chars', 3000) or 3000), 10000))

    if not url:
        return JSONResponse({'ok': False, 'error': 'url required'}, status_code=400)
    if not re.match(r'^https?://', url):
        return JSONResponse({'ok': False, 'error': 'url must start with http:// or https://'}, status_code=400)
    # SECURITY: Block SSRF — private IPs, cloud metadata endpoints, loopback
    if _is_ssrf_blocked_url(url):
        return JSONResponse({'ok': False, 'error': 'URL not allowed: private/internal addresses are blocked'}, status_code=403)

    content = await _fetch_page_text(url, max_chars)
    return {
        'ok': True,
        'url': url,
        'content': content,
        'length': len(content),
    }


@router.post('/grounded-completion')
async def grounded_completion(req: Request):
    """
    Like Perplexity: search the web first, then answer with citations.
    Injects search results into the prompt before calling the LLM.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = (body.get('prompt') or '').strip()
    agent_id = (body.get('agent_id') or 'builder').strip() or 'builder'
    num_results = max(1, min(int(body.get('num_results', 5) or 5), 8))
    fetch_full = bool(body.get('fetch_content', False))

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    query = prompt[:200]
    results = await _ddg_search(query, num_results)

    if fetch_full and results:
        tasks = [_fetch_page_text(res['url'], 1500) for res in results[:3]]
        contents = await asyncio.gather(*tasks)
        for res, c in zip(results, contents, strict=False):
            res['content'] = c

    citations = []
    ctx_parts = ['## Web Search Results\n']
    for i, res in enumerate(results, 1):
        citations.append({'num': i, 'title': res['title'], 'url': res['url']})
        ctx_parts.append(f'[{i}] **{res["title"]}** ({res["url"]})\n{res.get("content", res["snippet"])}\n')

    search_ctx = '\n'.join(ctx_parts)

    grounded_prompt = (
        f'{search_ctx}\n\n---\n\n'
        f'Using the search results above as your knowledge base, answer this:\n'
        f'{prompt}\n\n'
        'Cite sources using [1], [2], etc. when using information from the search results.\n'
        'Distinguish between what you found in search results vs your existing knowledge.'
    )

    from ..services import llm as llm_svc

    result = await llm_svc.complete(
        [{'role': 'user', 'content': grounded_prompt}],
        agent_id=agent_id,
        max_tokens=2000,
        inject_steering=False,
    )

    if not result.get('ok') or '[LLM error' in result.get('text', ''):
        summary_lines = [f"### 🌐 DuckDuckGo Search Results for: **{query}**\n*Pure search extraction summary (no API key required)*\n"]
        for i, r in enumerate(results, 1):
            summary_lines.append(f"**{i}. [{r['title']}]({r['url']})**\n> {r['snippet']}\n")
        result['text'] = "\n".join(summary_lines)

    _record_search(query, 'grounded', len(results))

    return {
        'ok': True,
        'answer': result.get('text', ''),
        'citations': citations,
        'query': query,
        'sources': len(results),
        'tokens': result.get('tokens', 0),
    }


@router.post('/grounded-completion/stream')
async def grounded_stream(req: Request):
    """Streaming version of grounded completion."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = (body.get('prompt') or '').strip()
    agent_id = (body.get('agent_id') or 'builder').strip() or 'builder'
    num_results = max(1, min(int(body.get('num_results', 4) or 4), 8))

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    async def _stream():
        yield f'data: {json.dumps({"type": "searching", "query": prompt[:100]})}\n\n'

        results = await _ddg_search(prompt[:200], num_results)
        citations = [{'num': i + 1, 'title': res['title'], 'url': res['url']} for i, res in enumerate(results)]
        yield f'data: {json.dumps({"type": "search_done", "results": len(results), "citations": citations})}\n\n'

        _record_search(prompt[:200], 'grounded_stream', len(results))

        ctx = '## Web Search Results\n' + '\n'.join(
            f'[{i + 1}] {res["title"]}: {res["snippet"]}' for i, res in enumerate(results)
        )
        grounded = f'{ctx}\n\n---\n\nAnswer with citations [1],[2],…: {prompt}'

        from ..services import llm as llm_svc

        async for chunk in llm_svc.stream(
            [{'role': 'user', 'content': grounded}],
            agent_id=agent_id,
            max_tokens=2000,
            inject_steering=False,
        ):
            # BUG FIX: llm_svc.stream() yields fully-formatted SSE lines
            # ('data: {"delta": ..., "done": ...}\n\n'), not raw text
            # chunks -- confirmed by every other correct caller of
            # llm_svc.stream() in this codebase (e.g. bugbot.py, chat.py),
            # which all parse out the `delta` field before re-emitting.
            # This endpoint instead re-wrapped the ENTIRE raw SSE string as
            # {"type": "chunk", "text": chunk}, so the frontend displayed
            # literal `data: {"delta": "...", "done": false}` JSON text
            # instead of the actual answer — reproduced live (grounded
            # streaming showed raw SSE frames verbatim in the UI). Extract
            # the real text delta before re-emitting, same pattern as
            # bugbot.py's _stream().
            delta = ''
            try:
                if chunk.startswith('data:'):
                    delta = json.loads(chunk[5:].strip()).get('delta', '')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
            if delta:
                yield f'data: {json.dumps({"type": "chunk", "text": delta})}\n\n'

        yield f'data: {json.dumps({"type": "done", "citations": citations})}\n\n'

    return StreamingResponse(sse_guard(_stream()),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@router.post('/research')
async def deep_research(req: Request):
    """
    Multi-query deep research: run multiple searches, synthesize.
    Like Perplexity Deep Research or OpenRouter Fusion with web.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    topic = (body.get('topic') or '').strip()
    if not topic:
        return JSONResponse({'ok': False, 'error': 'topic required'}, status_code=400)

    async def _stream():
        yield f'data: {json.dumps({"type": "research_start", "topic": topic})}\n\n'

        from ..services import llm as llm_svc

        # Generate sub-queries
        qgen = await llm_svc.complete(
            [
                {
                    'role': 'user',
                    'content': (
                        'Generate 4 specific web search queries to research this topic thoroughly.\n'
                        f'Topic: {topic}\nReturn a JSON array of query strings only.'
                    ),
                }
            ],
            agent_id='research',
            max_tokens=200,
            temperature=0.5,
            inject_steering=False,
        )

        queries = [topic]
        m = re.search(r'\[.*?\]', qgen.get('text', ''), re.DOTALL)
        if m:
            try:
                queries = json.loads(m.group(0))[:5]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

        yield f'data: {json.dumps({"type": "queries", "queries": queries})}\n\n'

        # Run all searches in parallel
        search_tasks = [_ddg_search(q, 4) for q in queries]
        all_results = await asyncio.gather(*search_tasks)

        all_sources: list[dict] = []
        for batch in all_results:
            all_sources.extend(batch)

        # Deduplicate by URL
        seen: set[str] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            if s['url'] not in seen:
                seen.add(s['url'])
                unique_sources.append(s)

        _record_search(topic, 'research', len(unique_sources))
        yield f'data: {json.dumps({"type": "sources_gathered", "count": len(unique_sources)})}\n\n'

        # Synthesize
        ctx = '\n\n'.join(f'[{i + 1}] {s["title"]}\n{s["snippet"]}' for i, s in enumerate(unique_sources[:15]))
        synth_prompt = (
            f'Research topic: {topic}\n\nSources found:\n{ctx}\n\n'
            'Write a comprehensive research report with:\n'
            '1. Executive Summary\n'
            '2. Key Findings (with citations)\n'
            '3. Different Perspectives\n'
            '4. Gaps & Limitations\n'
            '5. Conclusion\n\n'
            'Use [1], [2], etc. for citations.'
        )

        async for chunk in llm_svc.stream(
            [{'role': 'user', 'content': synth_prompt}],
            agent_id='research',
            max_tokens=3000,
            inject_steering=False,
        ):
            # BUG FIX: same issue as grounded_stream() above -- extract the
            # real text delta from the raw SSE line instead of re-emitting
            # the entire unparsed 'data: {...}\n\n' string as the "text".
            delta = ''
            try:
                if chunk.startswith('data:'):
                    delta = json.loads(chunk[5:].strip()).get('delta', '')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
            if delta:
                yield f'data: {json.dumps({"type": "chunk", "text": delta})}\n\n'

        citations = [{'num': i + 1, 'title': s['title'], 'url': s['url']} for i, s in enumerate(unique_sources[:15])]
        yield f'data: {json.dumps({"type": "done", "citations": citations, "source_count": len(unique_sources)})}\n\n'

    return StreamingResponse(sse_guard(_stream()),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@router.get('/history')
async def get_history(limit: int = 50):
    """Return recent search history."""
    limit = max(1, min(int(limit), 200))
    con = get_conn()
    try:
        rows = con.execute(
            'SELECT id, query, kind, results, ts FROM ws_search_history ORDER BY ts DESC LIMIT ?',
            (limit,),
        ).fetchall()
        items = [dict(r) for r in rows]
    except Exception as ex:
        log.warning('history fetch failed: %s', ex)
        items = []
    finally:
        con.close()

    return {'ok': True, 'items': items, 'count': len(items)}


@router.delete('/history')
async def clear_history():
    """Clear all search history."""
    con = get_conn()
    try:
        con.execute('DELETE FROM ws_search_history')
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'message': 'History cleared'}


@router.delete('/history/{entry_id}')
async def delete_history_entry(entry_id: int):
    """Delete a single history entry."""
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM ws_search_history WHERE id=?', (entry_id,))
        con.commit()
        if cur.rowcount == 0:
            return JSONResponse({'ok': False, 'error': 'not found'}, status_code=404)
    finally:
        con.close()
    return {'ok': True}


@router.get('/suggest')
async def suggest(q: str = '', limit: int = 8):
    """Return autocomplete suggestions from search history."""
    q = q.strip()
    limit = max(1, min(int(limit), 20))

    if not q:
        # Return most recent unique queries
        con = get_conn()
        try:
            rows = con.execute(
                'SELECT DISTINCT query FROM ws_search_history ORDER BY ts DESC LIMIT ?',
                (limit,),
            ).fetchall()
            suggestions = [r['query'] for r in rows]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            suggestions = []
        finally:
            con.close()
        return {'ok': True, 'suggestions': suggestions}

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT DISTINCT query FROM ws_search_history WHERE query LIKE ? ORDER BY ts DESC LIMIT ?',
            (f'{q}%', limit),
        ).fetchall()
        suggestions = [r['query'] for r in rows]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        suggestions = []
    finally:
        con.close()

    return {'ok': True, 'q': q, 'suggestions': suggestions}
