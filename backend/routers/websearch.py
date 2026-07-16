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

import contextlib

import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/websearch', tags=['websearch'])
log = logging.getLogger('agentic.websearch')

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'memory' / 'agentic.db'


# ── DB helpers ──────────────────────────────────────────────────────────────


def get_conn() -> sqlite3.Connection:
    """Retrieve and return get conn."""
    con = sqlite3.connect(DB)
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


async def _ddg_search(query: str, num_results: int = 5) -> list[dict]:
    """Search DuckDuckGo — free, no API key needed."""
    import urllib.parse

    import httpx

    # clamp / sanitise
    num_results = max(1, min(int(num_results), 10))
    results: list[dict] = []

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f'https://lite.duckduckgo.com/lite/?q={encoded}'

        async with httpx.AsyncClient(timeout=10, headers={'User-Agent': 'Mozilla/5.0 AgenticOS/6.0'}) as client:
            r = await client.get(url)
            if r.status_code == 200:
                text = r.text
                link_pattern = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
                snippet_pattern = re.compile(
                    r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
                    re.IGNORECASE | re.DOTALL,
                )
                links = link_pattern.findall(text)
                snippets = snippet_pattern.findall(text)

                for i, (href, title) in enumerate(links[:num_results]):
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
                    results.append(
                        {
                            'rank': i + 1,
                            'title': title.strip()[:200],
                            'url': href,
                            'snippet': snippet[:400],
                        }
                    )
    except Exception as ex:
        log.warning('DDG search failed: %s', ex)

    # Fallback: instant answers API
    if not results:
        try:
            import urllib.parse

            import httpx

            url = (
                f'https://api.duckduckgo.com/?q={urllib.parse.quote_plus(query)}&format=json&no_html=1&skip_disambig=1'
            )
            async with httpx.AsyncClient(timeout=8) as client:
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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    query = (body.get('query') or '').strip()
    n = max(1, min(int(body.get('num_results', 5) or 5), 10))
    fetch = bool(body.get('fetch_content', False))

    if not query:
        return {'ok': False, 'error': 'query required'}

    results = await _ddg_search(query, n)

    if fetch:
        tasks = [_fetch_page_text(res['url']) for res in results[:3]]
        contents = await asyncio.gather(*tasks)
        for res, content in zip(results, contents):
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
    and cloud metadata endpoints.
    Returns True if the URL should be blocked.
    """
    import ipaddress
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ''
        # Block cloud metadata endpoints by hostname
        blocked_hosts = {
            '169.254.169.254',
            'metadata.google.internal',
            '100.100.100.200',
            'metadata.internal',
        }
        if host in blocked_hosts:
            return True
        # Block by IP range (private/loopback/link-local)
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except ValueError:
            pass  # not an IP — hostname check above already covers known ones
        # Block localhost variants
        if host in ('localhost', '0.0.0.0', '::1', '[::1]'):
            return True
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return True  # block on parse error
    return False


@router.post('/fetch-content')
async def fetch_content(req: Request):
    """Fetch and extract readable text from a given URL."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    url = (body.get('url') or '').strip()
    max_chars = max(500, min(int(body.get('max_chars', 3000) or 3000), 10000))

    if not url:
        return {'ok': False, 'error': 'url required'}
    if not re.match(r'^https?://', url):
        return {'ok': False, 'error': 'url must start with http:// or https://'}
    # SECURITY: Block SSRF — private IPs, cloud metadata endpoints, loopback
    if _is_ssrf_blocked_url(url):
        return {'ok': False, 'error': 'URL not allowed: private/internal addresses are blocked'}

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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    agent_id = (body.get('agent_id') or 'builder').strip() or 'builder'
    num_results = max(1, min(int(body.get('num_results', 5) or 5), 8))
    fetch_full = bool(body.get('fetch_content', False))

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    query = prompt[:200]
    results = await _ddg_search(query, num_results)

    if fetch_full and results:
        tasks = [_fetch_page_text(res['url'], 1500) for res in results[:3]]
        contents = await asyncio.gather(*tasks)
        for res, c in zip(results, contents):
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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    agent_id = (body.get('agent_id') or 'builder').strip() or 'builder'
    num_results = max(1, min(int(body.get('num_results', 4) or 4), 8))

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

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
            yield f'data: {json.dumps({"type": "chunk", "text": chunk})}\n\n'

        yield f'data: {json.dumps({"type": "done", "citations": citations})}\n\n'

    return StreamingResponse(
        _stream(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@router.post('/research')
async def deep_research(req: Request):
    """
    Multi-query deep research: run multiple searches, synthesize.
    Like Perplexity Deep Research or OpenRouter Fusion with web.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    topic = (body.get('topic') or '').strip()
    if not topic:
        return {'ok': False, 'error': 'topic required'}

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
            yield f'data: {json.dumps({"type": "chunk", "text": chunk})}\n\n'

        citations = [{'num': i + 1, 'title': s['title'], 'url': s['url']} for i, s in enumerate(unique_sources[:15])]
        yield f'data: {json.dumps({"type": "done", "citations": citations, "source_count": len(unique_sources)})}\n\n'

    return StreamingResponse(
        _stream(),
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
            return {'ok': False, 'error': 'not found'}
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
