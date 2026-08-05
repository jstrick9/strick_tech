"""
Agentic OS — Visual Workflow Builder Router
n8n-style drag-drop node graph for wiring agents visually.
Nodes: trigger, agent, condition, transform, output, loop, delay, webhook
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix='/api/workflow', tags=['workflow'])
log = logging.getLogger('agentic.workflow')

from backend.config import get_data_dir

from ..services.llm import sse_guard
from ..services.request_body import json_body_or_error

ROOT = get_data_dir()
WF_DIR = ROOT / 'workspaces' / 'workflows'
WF_DIR.mkdir(parents=True, exist_ok=True)

# ── Default starter workflows ──────────────────────────────────────────────────
STARTER_WORKFLOWS = [
    {
        'id': 'wf_chat_pipeline',
        'name': 'Chat → Research → Summarize',
        'description': 'Trigger on chat input, research with one agent, summarize with another',
        'nodes': [
            {'id': 'n1', 'type': 'trigger', 'label': 'Chat Input', 'x': 80, 'y': 200, 'config': {'event': 'chat'}},
            {
                'id': 'n2',
                'type': 'agent',
                'label': 'Researcher',
                'x': 300,
                'y': 200,
                'config': {'agent_id': 'researcher', 'prompt': 'Research: {{input}}'},
            },
            {
                'id': 'n3',
                'type': 'agent',
                'label': 'Summarizer',
                'x': 540,
                'y': 200,
                'config': {'agent_id': 'builder', 'prompt': 'Summarize this research in 3 bullets:\n{{prev_output}}'},
            },
            {'id': 'n4', 'type': 'output', 'label': 'Chat Reply', 'x': 780, 'y': 200, 'config': {'target': 'chat'}},
        ],
        'edges': [
            {'id': 'e1', 'from': 'n1', 'to': 'n2'},
            {'id': 'e2', 'from': 'n2', 'to': 'n3'},
            {'id': 'e3', 'from': 'n3', 'to': 'n4'},
        ],
        'created_at': '2025-01-01T00:00:00Z',
    },
    {
        'id': 'wf_code_review',
        'name': 'Code → Review → Test → Deploy',
        'description': 'Full pipeline from code generation to deployment',
        'nodes': [
            {
                'id': 'n1',
                'type': 'trigger',
                'label': 'Webhook / Schedule',
                'x': 60,
                'y': 180,
                'config': {'event': 'webhook'},
            },
            {
                'id': 'n2',
                'type': 'agent',
                'label': 'Code Gen',
                'x': 280,
                'y': 180,
                'config': {'agent_id': 'builder', 'prompt': 'Generate code for: {{input}}'},
            },
            {
                'id': 'n3',
                'type': 'agent',
                'label': 'Code Review',
                'x': 500,
                'y': 100,
                'config': {'agent_id': 'researcher', 'prompt': 'Review this code:\n{{prev_output}}'},
            },
            {
                'id': 'n4',
                'type': 'agent',
                'label': 'Test Gen',
                'x': 500,
                'y': 260,
                'config': {'agent_id': 'builder', 'prompt': 'Write tests for:\n{{prev_output}}'},
            },
            {
                'id': 'n5',
                'type': 'condition',
                'label': 'Tests Pass?',
                'x': 720,
                'y': 180,
                'config': {'expression': "{{prev_output}} contains 'pass'"},
            },
            {'id': 'n6', 'type': 'output', 'label': 'Deploy', 'x': 940, 'y': 140, 'config': {'target': 'deploy'}},
            {
                'id': 'n7',
                'type': 'output',
                'label': 'Notify Fail',
                'x': 940,
                'y': 260,
                'config': {'target': 'notification'},
            },
        ],
        'edges': [
            {'id': 'e1', 'from': 'n1', 'to': 'n2'},
            {'id': 'e2', 'from': 'n2', 'to': 'n3'},
            {'id': 'e3', 'from': 'n2', 'to': 'n4'},
            {'id': 'e4', 'from': 'n3', 'to': 'n5'},
            {'id': 'e5', 'from': 'n4', 'to': 'n5'},
            {'id': 'e6', 'from': 'n5', 'to': 'n6', 'label': 'yes'},
            {'id': 'e7', 'from': 'n5', 'to': 'n7', 'label': 'no'},
        ],
        'created_at': '2025-01-01T00:00:00Z',
    },
    {
        'id': 'wf_swarm_consensus',
        'name': 'Swarm Consensus Flow',
        'description': 'Fan out to 3 agents, judge output, synthesize',
        'nodes': [
            {'id': 'n1', 'type': 'trigger', 'label': 'Input', 'x': 60, 'y': 200, 'config': {'event': 'manual'}},
            {'id': 'n2', 'type': 'agent', 'label': 'Agent A', 'x': 280, 'y': 80, 'config': {'agent_id': 'researcher'}},
            {'id': 'n3', 'type': 'agent', 'label': 'Agent B', 'x': 280, 'y': 200, 'config': {'agent_id': 'builder'}},
            {
                'id': 'n4',
                'type': 'agent',
                'label': 'Agent C',
                'x': 280,
                'y': 320,
                'config': {'agent_id': 'orchestrator'},
            },
            {
                'id': 'n5',
                'type': 'transform',
                'label': 'Merge & Judge',
                'x': 520,
                'y': 200,
                'config': {'mode': 'merge'},
            },
            {'id': 'n6', 'type': 'output', 'label': 'Final Answer', 'x': 740, 'y': 200, 'config': {'target': 'chat'}},
        ],
        'edges': [
            {'id': 'e1', 'from': 'n1', 'to': 'n2'},
            {'id': 'e2', 'from': 'n1', 'to': 'n3'},
            {'id': 'e3', 'from': 'n1', 'to': 'n4'},
            {'id': 'e4', 'from': 'n2', 'to': 'n5'},
            {'id': 'e5', 'from': 'n3', 'to': 'n5'},
            {'id': 'e6', 'from': 'n4', 'to': 'n5'},
            {'id': 'e7', 'from': 'n5', 'to': 'n6'},
        ],
        'created_at': '2025-01-01T00:00:00Z',
    },
]


def _wf_path(wf_id: str) -> Path:
    """Map an external workflow ID to a safe workspace filename."""
    safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', str(wf_id))[:128]
    return WF_DIR / f'{safe_id}.json'


def _load_all() -> list[dict]:
    wfs = []
    for f in sorted(WF_DIR.iterdir()):
        if f.suffix == '.json':
            try:
                wfs.append(json.loads(f.read_text()))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
    if not wfs:
        # Seed starters
        for w in STARTER_WORKFLOWS:
            _wf_path(w['id']).write_text(json.dumps(w, indent=2))
        wfs = list(STARTER_WORKFLOWS)
    return wfs


def _load_one(wf_id: str) -> dict | None:
    p = _wf_path(wf_id)
    if not p.exists():
        return None
    try:
        value = json.loads(p.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        log.warning('Ignoring corrupt workflow file: %s', p)
        return None


# ── REST CRUD ──────────────────────────────────────────────────────────────────
@router.get('')
def list_workflows():
    # FIX 4: call _load_all() once (was called twice)
    """Retrieve and return list workflows."""
    wfs = _load_all()
    return {'workflows': wfs, 'count': len(wfs)}


@router.post('')
async def create_workflow(req: Request):
    """Create and initialize a new workflow."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    wf = {
        'id': body.get('id') or f'wf_{uuid.uuid4().hex[:8]}',
        'name': (body.get('name') or 'Untitled Workflow')[:120],
        'description': (body.get('description') or '')[:400],
        'nodes': body.get('nodes', []),
        'edges': body.get('edges', []),
        'created_at': body.get('created_at', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    _wf_path(wf['id']).write_text(json.dumps(wf, indent=2))
    return {'ok': True, 'workflow': wf}


@router.get('/{wf_id}')
def get_workflow(wf_id: str):
    """Retrieve and return get workflow."""
    wf = _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    return wf


@router.put('/{wf_id}')
async def update_workflow(wf_id: str, req: Request):
    """Update existing workflow record or state."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    # BUG FIX: `_load_one(wf_id) or {}` meant PUT to a nonexistent id silently
    # CREATED a workflow there instead of 404ing — a typo in the id produced a
    # second, near-invisible workflow while the user believed they had saved
    # the original. Verified live: PUT /api/workflow/nope returned 200.
    existing = _load_one(wf_id)
    if not existing:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    existing.update(
        {
            'id': wf_id,
            'name': (body.get('name') or existing.get('name', 'Workflow'))[:120],
            'description': (body.get('description') or existing.get('description', ''))[:400],
            'nodes': body.get('nodes', existing.get('nodes', [])),
            'edges': body.get('edges', existing.get('edges', [])),
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
    )
    _wf_path(wf_id).write_text(json.dumps(existing, indent=2))
    return {'ok': True, 'workflow': existing}


@router.delete('/{wf_id}')
def delete_workflow(wf_id: str):
    """Delete or remove specified workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    p.unlink()
    return {'ok': True, 'deleted': wf_id}


@router.get('/node-types/list')
def node_types():
    """Execute or process node types operation."""
    return {
        'types': [
            {
                'id': 'trigger',
                'label': '⚡ Trigger',
                'color': '#5b8af8',
                'desc': 'Start the workflow (webhook, schedule, chat, manual)',
                'inputs': 0,
                'outputs': 1,
            },
            {
                'id': 'agent',
                'label': '🤖 Agent',
                'color': '#9d74f5',
                'desc': 'Run an AI agent with a prompt',
                'inputs': 1,
                'outputs': 1,
            },
            {
                'id': 'condition',
                'label': '🔀 Condition',
                'color': '#e8a237',
                'desc': 'Branch based on output content',
                'inputs': 1,
                'outputs': 2,
            },
            {
                'id': 'transform',
                'label': '⚙️ Transform',
                'color': '#38c5d8',
                'desc': 'Merge, filter, or format data',
                'inputs': -1,
                'outputs': 1,
            },
            {
                'id': 'loop',
                'label': '🔁 Loop',
                'color': '#f06080',
                'desc': 'Repeat N times or until condition',
                'inputs': 1,
                'outputs': 1,
            },
            {
                'id': 'delay',
                'label': '⏱️ Delay',
                'color': '#7a8aaa',
                'desc': 'Wait N seconds before next node',
                'inputs': 1,
                'outputs': 1,
            },
            {
                'id': 'webhook',
                'label': '🌐 Webhook',
                'color': '#4cc98a',
                'desc': 'Call an external API',
                'inputs': 1,
                'outputs': 1,
            },
            {
                'id': 'output',
                'label': '📤 Output',
                'color': '#3dba7a',
                'desc': 'Send to chat, deploy, notification, or file',
                'inputs': 1,
                'outputs': 0,
            },
            {
                'id': 'memory',
                'label': '🧠 Memory',
                'color': '#c084fc',
                'desc': 'Read/write to agent memory',
                'inputs': 1,
                'outputs': 1,
            },
            {
                'id': 'code',
                'label': '</> Code',
                'color': '#f08850',
                'desc': 'Run custom JavaScript transform',
                'inputs': 1,
                'outputs': 1,
            },
        ]
    }


# ── Workflow execution (SSE streaming) ────────────────────────────────────────
_CONDITION_OPS = ('contains', 'not_contains', 'equals', 'not_equals',
                  'starts_with', 'ends_with', 'matches', 'is_empty', 'is_not_empty',
                  '>=', '<=', '==', '!=', '>', '<')


def evaluate_condition(expression: str, context: dict) -> tuple[bool, str]:
    """Evaluate a condition-node expression. Returns (result, explanation).

    BUG FIX: the executor computed the expression and THREW IT AWAY —

        cfg.get('expression', '').replace('{{prev_output}}', context['prev_output'])
        passed = any(kw in context['prev_output'].lower()
                     for kw in ['yes', 'pass', 'true', 'success', 'ok'])

    a bare statement with no assignment, followed by a keyword scan that
    ignored it entirely. Whatever the user configured had NO effect on which
    branch ran. Verified live: an expression written to never match still took
    the "yes" branch because the input happened to contain the word "yes".

    Supports a small, deliberately non-executable grammar:
        {{prev_output}} contains 'text'
        {{input}} equals 'text'
        {{prev_output}} matches '^regex$'
        {{prev_output}} is_not_empty
        {{prev_output}} > 5
    Nothing here evals code — a workflow node that ran arbitrary Python would
    be a far worse bug than the one being fixed. An empty expression falls back
    to the old keyword heuristic so existing workflows keep working, but says
    so in the explanation.
    """
    import re as _re

    raw = str(expression or '').strip()
    resolved = (
        raw.replace('{{prev_output}}', str(context.get('prev_output', '')))
        .replace('{{input}}', str(context.get('input', '')))
    )

    if not raw:
        passed = any(
            kw in str(context.get('prev_output', '')).lower()
            for kw in ('yes', 'pass', 'true', 'success', 'ok')
        )
        return passed, 'no expression configured — fell back to keyword heuristic'

    # <lhs> <op> [<rhs>]
    pattern = r'^(.*?)\s+(' + '|'.join(_re.escape(o) for o in _CONDITION_OPS) + r')(?:\s+(.*))?$'
    m = _re.match(pattern, resolved, _re.DOTALL)
    if not m:
        # No recognised operator: treat the whole thing as a substring test,
        # which is what most people mean by a bare expression.
        passed = resolved.lower() in str(context.get('prev_output', '')).lower()
        return passed, f'substring test for {resolved[:60]!r}'

    lhs = (m.group(1) or '').strip()
    op = m.group(2)
    rhs = (m.group(3) or '').strip().strip('\'"')

    def _num(v):
        try:
            return float(str(v).strip())
        except (TypeError, ValueError):
            return None

    try:
        if op == 'contains':
            passed = rhs.lower() in lhs.lower()
        elif op == 'not_contains':
            passed = rhs.lower() not in lhs.lower()
        elif op in ('equals', '=='):
            passed = lhs.strip().strip('\'"').lower() == rhs.lower()
        elif op in ('not_equals', '!='):
            passed = lhs.strip().strip('\'"').lower() != rhs.lower()
        elif op == 'starts_with':
            passed = lhs.lower().startswith(rhs.lower())
        elif op == 'ends_with':
            passed = lhs.lower().endswith(rhs.lower())
        elif op == 'matches':
            passed = bool(_re.search(rhs, lhs, _re.IGNORECASE | _re.DOTALL))
        elif op == 'is_empty':
            passed = not lhs.strip()
        elif op == 'is_not_empty':
            passed = bool(lhs.strip())
        elif op in ('>', '<', '>=', '<='):
            a, b = _num(lhs), _num(rhs)
            if a is None or b is None:
                return False, f'cannot compare {lhs[:30]!r} {op} {rhs[:30]!r} numerically'
            passed = {'>': a > b, '<': a < b, '>=': a >= b, '<=': a <= b}[op]
        else:
            return False, f'unknown operator {op!r}'
    except _re.error as exc:
        return False, f'invalid regex: {exc}'

    return passed, f'{op} -> {passed}'


@router.post('/{wf_id}/run')
async def run_workflow(wf_id: str, req: Request):
    """Execute and run workflow operation."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    wf = _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)

    user_input = body.get('input', '')

    async def _stream():
        nodes = {n['id']: n for n in wf.get('nodes', [])}
        edges = wf.get('edges', [])

        # Build adjacency
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e['from'], []).append(e['to'])

        # Find trigger node(s)
        triggers = [n for n in nodes.values() if n['type'] == 'trigger']
        if not triggers:
            yield f'data: {json.dumps({"type": "error", "msg": "No trigger node found"})}\n\n'
            return

        context = {'input': user_input, 'prev_output': user_input}
        run_id = uuid.uuid4().hex[:8]

        yield f'data: {json.dumps({"type": "start", "run_id": run_id, "workflow": wf["name"]})}\n\n'

        visited: set[str] = set()
        queue = [triggers[0]['id']]
        node_errors: list[dict] = []

        from ..services import llm as llm_svc

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)

            node = nodes.get(nid)
            if not node:
                continue

            yield f'data: {json.dumps({"type": "node_start", "node_id": nid, "node_type": node["type"], "label": node.get("label", "")})}\n\n'
            await asyncio.sleep(0.05)

            cfg = node.get('config', {})

            if node['type'] == 'trigger':
                context['prev_output'] = context['input']

            elif node['type'] == 'agent':
                prompt = cfg.get('prompt', '{{input}}')
                prompt = prompt.replace('{{input}}', context['input']).replace(
                    '{{prev_output}}', context['prev_output']
                )

                try:
                    msgs = [{'role': 'user', 'content': prompt}]
                    result = await llm_svc.complete(
                        msgs, agent_id=cfg.get('agent_id', 'builder'), max_tokens=1024, inject_steering=False
                    )
                    context['prev_output'] = result.get('text', '')
                    yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": context["prev_output"][:300]})}\n\n'
                except Exception as ex:
                    node_errors.append({'node_id': nid, 'error': str(ex)})
                    yield f'data: {json.dumps({"type": "node_error", "node_id": nid, "error": str(ex)})}\n\n'

            elif node['type'] == 'condition':
                passed, why = evaluate_condition(cfg.get('expression', ''), context)
                context['_condition'] = passed
                yield (
                    'data: '
                    + json.dumps({
                        'type': 'node_output',
                        'node_id': nid,
                        'output': f'Condition: {str(passed).lower()} ({why})',
                        'condition': passed,
                    })
                    + '\n\n'
                )

            elif node['type'] == 'transform':
                mode = cfg.get('mode', 'passthrough')
                if mode == 'merge':
                    context['prev_output'] = f'[Merged outputs]\n{context["prev_output"]}'
                yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": "Transformed"})}\n\n'

            elif node['type'] == 'loop':
                # Iterative-refinement loop: re-runs an agent prompt against its own
                # previous output up to `iterations` times, stopping early if
                # `stop_keyword` appears in the output (case-insensitive). This was
                # previously advertised in the node palette ("Repeat N times or
                # until condition") but had NO execution handler at all — placing
                # a Loop node in a workflow silently no-op'd it. True arbitrary
                # cycle-following (jumping backward in the DAG) is intentionally
                # out of scope: the executor is a single-pass BFS with a `visited`
                # guard against infinite loops, so "loop" here means "iterate this
                # node's own agent call", which is what the properties panel now
                # exposes.
                try:
                    iterations = min(10, max(1, int(cfg.get('iterations', 3))))
                except (TypeError, ValueError):
                    iterations = 3
                stop_kw = str(cfg.get('stop_keyword', '') or '').strip().lower()
                loop_prompt_tpl = cfg.get('prompt', '{{prev_output}}')
                agent_id = cfg.get('agent_id', 'builder')
                last_output = context['prev_output']
                for i in range(iterations):
                    loop_prompt = loop_prompt_tpl.replace('{{input}}', context['input']).replace(
                        '{{prev_output}}', last_output
                    )
                    try:
                        result = await llm_svc.complete(
                            [{'role': 'user', 'content': loop_prompt}],
                            agent_id=agent_id, max_tokens=1024, inject_steering=False,
                        )
                        last_output = result.get('text', '')
                    except Exception as ex:
                        node_errors.append({'node_id': nid, 'error': str(ex)})
                        yield f'data: {json.dumps({"type": "node_error", "node_id": nid, "error": str(ex)})}\n\n'
                        break
                    preview = f'[iteration {i + 1}/{iterations}] {last_output[:200]}'
                    yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": preview})}\n\n'
                    if stop_kw and stop_kw in last_output.lower():
                        break
                context['prev_output'] = last_output

            elif node['type'] == 'delay':
                try:
                    secs = min(10, max(0, int(cfg.get('seconds', 1))))
                except (TypeError, ValueError):
                    secs = 1
                await asyncio.sleep(secs)
                yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": f"Waited {secs}s"})}\n\n'

            elif node['type'] == 'webhook':
                url = str(cfg.get('url', ''))[:2000]
                if url:
                    try:
                        from .websearch import _is_ssrf_blocked_url
                        if not url.startswith(('http://', 'https://')) or _is_ssrf_blocked_url(url):
                            raise ValueError('Webhook URL is not allowed')
                        import httpx

                        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                            r = await client.post(url, json=context)
                            context['prev_output'] = r.text[:500]
                    except Exception as ex:
                        node_errors.append({'node_id': nid, 'error': f'webhook: {ex}'})
                        context['prev_output'] = f'Webhook error: {ex}'
                yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": context["prev_output"][:200]})}\n\n'

            elif node['type'] == 'memory':
                from ..services import memory_db as _mdb

                action = cfg.get('action', 'read')
                if action == 'write':
                    con = _mdb.get_conn()
                    try:
                        con.execute(
                            'INSERT INTO memory(source,content,tags) VALUES (?,?,?)',
                            ('workflow', context['prev_output'][:2000], 'workflow'),
                        )
                        con.commit()
                    finally:
                        con.close()
                    yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": "Saved to memory"})}\n\n'
                else:
                    # BUG FIX: the read branch reported "Memory op done" and read
                    # NOTHING — prev_output passed straight through, so a Memory
                    # node wired for retrieval silently contributed no context.
                    query = str(
                        cfg.get('query') or context.get('prev_output') or context.get('input') or ''
                    )[:200]
                    try:
                        limit = min(10, max(1, int(cfg.get('limit', 3))))
                    except (TypeError, ValueError):
                        limit = 3
                    hits = _mdb.memory_search_fts(query, limit=limit) if query.strip() else []
                    if hits:
                        recalled = '\n'.join(f'- {h["content"][:200]}' for h in hits)
                        context['prev_output'] = (
                            f'{context["prev_output"]}\n\n[Recalled from memory]\n{recalled}'
                            if context['prev_output'] else recalled
                        )
                        msg = f'Recalled {len(hits)} memor{"y" if len(hits) == 1 else "ies"}'
                    else:
                        msg = 'No matching memories found'
                    yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": msg})}\n\n'

            elif node['type'] == 'output':
                target = cfg.get('target', 'chat')
                out_msg = f'output to {target}: {context["prev_output"][:200]}'
                yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": out_msg})}\n\n'
                yield f'data: {json.dumps({"type": "final_output", "target": target, "result": context["prev_output"]})}\n\n'

            elif node['type'] == 'code':
                # BUG FIX: this reported "Code transform applied" while doing
                # nothing at all — the output passed through unchanged. Claiming
                # a transform happened is worse than refusing: a user debugging
                # a pipeline sees a green node and looks elsewhere.
                #
                # Executing user code here is deliberately NOT the fix. This
                # runs in the server process with database and vault access; a
                # workflow node that evals arbitrary code would be a far worse
                # bug than the one being repaired. Text transforms that are
                # provably safe are supported; anything else says so plainly.
                op = str(cfg.get('operation') or cfg.get('mode') or '').strip().lower()
                text = context['prev_output']
                _ops = {
                    'uppercase': lambda t: t.upper(),
                    'lowercase': lambda t: t.lower(),
                    'trim': lambda t: t.strip(),
                    'strip_html': lambda t: re.sub(r'<[^>]+>', '', t),
                    'first_line': lambda t: t.splitlines()[0] if t.splitlines() else '',
                    'json_pretty': lambda t: json.dumps(json.loads(t), indent=2),
                }
                if op in _ops:
                    try:
                        context['prev_output'] = _ops[op](text)
                        msg = f'Applied {op}'
                    except (ValueError, TypeError, json.JSONDecodeError) as ex:
                        msg = f'{op} failed: {ex}'
                elif cfg.get('code'):
                    msg = (
                        'This node cannot execute code: it would run inside the server '
                        'process with database and vault access. Use a Code node '
                        f'"operation" instead (one of: {", ".join(sorted(_ops))}), or '
                        'run the script via a Terminal step.'
                    )
                    yield f'data: {json.dumps({"type": "node_error", "node_id": nid, "error": msg})}\n\n'
                    node_errors.append({'node_id': nid, 'error': msg})
                    msg = None
                else:
                    msg = 'No operation configured — output passed through unchanged'
                if msg:
                    yield f'data: {json.dumps({"type": "node_output", "node_id": nid, "output": msg})}\n\n'

            # FIX 11: Queue next nodes — filter by condition label for condition nodes
            for e in edges:
                if e['from'] != nid:
                    continue
                # For condition nodes, only follow the edge matching the result
                if node['type'] == 'condition':
                    edge_label = (e.get('label') or '').lower()
                    if edge_label in ('yes', 'true', 'pass', 'success'):
                        if context.get('_condition'):
                            queue.append(e['to'])
                    elif edge_label in ('no', 'false', 'fail', 'failure'):
                        if not context.get('_condition'):
                            queue.append(e['to'])
                    else:
                        # Unlabelled edge — follow always
                        queue.append(e['to'])
                else:
                    queue.append(e['to'])

        # FIX 6: Persist run to workflow_runs table for Replay pane
        try:
            from ..services.memory_db import get_conn as _get_conn

            _con = _get_conn()
            try:
                _con.execute(
                    """INSERT OR REPLACE INTO workflow_runs
                       (id, workflow_id, workflow_nm, status, input, created_at)
                       VALUES (?,?,?,?,?,datetime('now'))""",
                    # BUG FIX: this was hardcoded to 'success'. A run whose
                    # agent node errored outright was still recorded as a
                    # success, so the Replay pane and any monitoring built on
                    # workflow_runs were systematically wrong. Verified live:
                    # a run that emitted node_error persisted status='success'.
                    (
                        run_id,
                        wf['id'],
                        wf['name'][:100],
                        'failed' if node_errors else 'success',
                        user_input[:1000],
                    ),
                )
                _con.commit()
            finally:
                _con.close()
        except Exception as _e:
            log.warning('Failed to persist workflow run: %s', _e)

        yield (
            'data: '
            + json.dumps({
                'type': 'done',
                'run_id': run_id,
                'status': 'failed' if node_errors else 'success',
                'errors': node_errors,
                'nodes_run': len(visited),
            })
            + '\n\n'
        )

    return StreamingResponse(sse_guard(_stream()), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Additional CRUD endpoints ──────────────────────────────────────────────────
@router.post('/{wf_id}/duplicate')
async def duplicate_workflow(wf_id: str, req: Request):
    """Create a copy of an existing workflow with a new ID."""
    wf = _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    new_wf = dict(wf)
    new_wf['id'] = body.get('id') or f'wf_{uuid.uuid4().hex[:8]}'
    new_wf['name'] = (body.get('name') or f'{wf["name"]} (copy)')[:120]
    new_wf['created_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    new_wf['updated_at'] = new_wf['created_at']
    _wf_path(new_wf['id']).write_text(json.dumps(new_wf, indent=2))
    return {'ok': True, 'workflow': new_wf}


@router.post('/import')
async def import_workflow(req: Request):
    """Import a workflow from JSON. Assigns a new ID if one already exists."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    wf_id = body.get('id', f'wf_{uuid.uuid4().hex[:8]}')
    # If ID already exists, assign a new one
    if _wf_path(wf_id).exists():
        wf_id = f'wf_{uuid.uuid4().hex[:8]}'

    wf = {
        'id': wf_id,
        'name': (body.get('name') or 'Imported Workflow')[:120],
        'description': (body.get('description') or '')[:400],
        'nodes': body.get('nodes', []),
        'edges': body.get('edges', []),
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    _wf_path(wf_id).write_text(json.dumps(wf, indent=2))
    return {'ok': True, 'workflow': wf}


@router.get('/{wf_id}/export')
def export_workflow(wf_id: str):
    """Export a workflow as a downloadable JSON file."""
    wf = _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    content = json.dumps(wf, indent=2)
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in wf.get('name', 'workflow'))
    from fastapi.responses import Response

    return Response(
        content=content,
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{safe_name}.wf.json"'},
    )


@router.delete('/{wf_id}/edges/{edge_id}')
def delete_edge(wf_id: str, edge_id: str):
    """Delete a single edge from a workflow."""
    wf = _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)
    wf['edges'] = [e for e in (wf.get('edges') or []) if e.get('id') != edge_id]
    wf['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    _wf_path(wf_id).write_text(json.dumps(wf, indent=2))
    return {'ok': True, 'deleted_edge': edge_id}


@router.post('/{wf_id}/validate')
async def validate_workflow(wf_id: str, req: Request):
    """
    Validate a workflow for common issues:
    - Has at least one trigger node
    - Has at least one output node
    - No orphaned nodes (not connected to anything)
    - No cycles
    - All edges reference valid nodes
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    # Use provided data or load from disk
    wf = body if body.get('nodes') else _load_one(wf_id)
    if not wf:
        return JSONResponse({'ok': False, 'error': 'Workflow not found'}, status_code=404)

    nodes = {n['id']: n for n in (wf.get('nodes') or [])}
    edges = wf.get('edges') or []

    issues = []
    warnings = []

    # Check for trigger
    triggers = [n for n in nodes.values() if n.get('type') == 'trigger']
    if not triggers:
        issues.append({'code': 'NO_TRIGGER', 'msg': 'Workflow has no trigger node — it cannot start'})

    # Check for output
    outputs = [n for n in nodes.values() if n.get('type') == 'output']
    if not outputs:
        warnings.append({'code': 'NO_OUTPUT', 'msg': 'Workflow has no output node'})

    # Check edge validity
    invalid_edges = [e for e in edges if e.get('from') not in nodes or e.get('to') not in nodes]
    for e in invalid_edges:
        issues.append({'code': 'INVALID_EDGE', 'msg': f'Edge {e.get("id")} references missing node'})

    # Check for orphaned nodes (no edges in or out, and not trigger)
    connected = set()
    for e in edges:
        connected.add(e.get('from'))
        connected.add(e.get('to'))
    for nid, n in nodes.items():
        if nid not in connected and n.get('type') != 'trigger':
            warnings.append({'code': 'ORPHANED', 'msg': f"Node '{n.get('label', nid)}' is not connected to anything"})

    # Cycle detection (DFS)
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.get('from', ''), []).append(e.get('to', ''))
    visited, rec_stack = set(), set()

    def has_cycle(node):
        """Execute or process has cycle operation."""
        visited.add(node)
        rec_stack.add(node)
        for nb in adj.get(node, []):
            if nb not in visited:
                if has_cycle(nb):
                    return True
            elif nb in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for nid in nodes:
        if nid not in visited and has_cycle(nid):
            issues.append({'code': 'CYCLE', 'msg': 'Workflow contains a cycle (infinite loop)'})
            break

    return {
        'ok': len(issues) == 0,
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'node_count': len(nodes),
        'edge_count': len(edges),
    }
