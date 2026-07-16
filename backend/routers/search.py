"""
Agentic OS — Global Search Router (/api/search)
Provides fast unified search across navigation panes, agents, memory, prompts, and marketplace skills.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix='/api/search', tags=['search'])

# Static list of all navigation panes and core features for instant search
_NAV_PANES = [
    {
        'id': 'chat',
        'title': 'Multi-Agent Chat',
        'category': 'Navigation',
        'description': 'Stream conversations with multi-agent orchestration and voice',
        'icon': '💬',
        'action': 'pane:chat',
    },
    {
        'id': 'studio',
        'title': 'App Studio Builder',
        'category': 'Navigation',
        'description': 'Live HTML/JS/Py app builder with Monaco code editor and instant preview',
        'icon': '🛠️',
        'action': 'pane:studio',
    },
    {
        'id': 'templates',
        'title': 'App Templates Library',
        'category': 'Navigation',
        'description': 'Browse and clone ready-to-use application templates',
        'icon': '📋',
        'action': 'pane:templates',
    },
    {
        'id': 'swarm',
        'title': 'Multi-Agent Swarm',
        'category': 'Navigation',
        'description': 'Fan-out queries across specialized agents with judge synthesis',
        'icon': '🐝',
        'action': 'pane:swarm',
    },
    {
        'id': 'memory',
        'title': 'Memory Galaxy 3D',
        'category': 'Navigation',
        'description': '3D knowledge graph, semantic search, and FTS5 memory store',
        'icon': '🌌',
        'action': 'pane:memory',
    },
    {
        'id': 'kanban',
        'title': 'Task Kanban Board',
        'category': 'Navigation',
        'description': 'Drag-and-drop task workflow management across states',
        'icon': '📑',
        'action': 'pane:kanban',
    },
    {
        'id': 'agents',
        'title': 'Agent Fleet Management',
        'category': 'Navigation',
        'description': 'Configure, create, test, and tune specialized agents',
        'icon': '🤖',
        'action': 'pane:agents',
    },
    {
        'id': 'prompts',
        'title': 'Prompt Library & Templates',
        'category': 'Navigation',
        'description': 'Manage system prompts, few-shot examples, and templates',
        'icon': '💡',
        'action': 'pane:prompts',
    },
    {
        'id': 'marketplace',
        'title': 'Plugin Marketplace',
        'category': 'Navigation',
        'description': 'Install curated skill packs and specialized connectors',
        'icon': '📦',
        'action': 'pane:marketplace',
    },
    {
        'id': 'specs',
        'title': 'Spec-Driven Workflow (SDW)',
        'category': 'Navigation',
        'description': 'Structured requirements, technical specs, and verification',
        'icon': '📐',
        'action': 'pane:specs',
    },
    {
        'id': 'replay',
        'title': 'Time-Travel Replay & CRDT',
        'category': 'Navigation',
        'description': 'Replay execution traces and collaborate in real time',
        'icon': '⏪',
        'action': 'pane:replay',
    },
    {
        'id': 'evals',
        'title': 'Eval Framework & Benchmarks',
        'category': 'Navigation',
        'description': 'Automated evaluation suites, test cases, and quality scoring',
        'icon': '🎯',
        'action': 'pane:evals',
    },
    {
        'id': 'observability',
        'title': 'Observability & Tracing',
        'category': 'Navigation',
        'description': 'Real-time execution traces, token breakdown, and latency charts',
        'icon': '📈',
        'action': 'pane:observability',
    },
    {
        'id': 'finops',
        'title': 'FinOps Cost Monitor',
        'category': 'Navigation',
        'description': 'Budget tracking, token cost attribution, and anomaly alerts',
        'icon': '💰',
        'action': 'pane:finops',
    },
    {
        'id': 'control_tower',
        'title': 'Governance Control Tower',
        'category': 'Navigation',
        'description': 'Audit trails, HITL approval gates, and compliance monitoring',
        'icon': '🗼',
        'action': 'pane:control_tower',
    },
    {
        'id': 'secrets',
        'title': 'Encrypted Secrets Vault',
        'category': 'Navigation',
        'description': 'Manage API keys, OAuth tokens, and environment variables securely',
        'icon': '🔐',
        'action': 'pane:secrets',
    },
    {
        'id': 'settings',
        'title': 'System Settings & Preferences',
        'category': 'Navigation',
        'description': 'Configure models, voice TTS preferences, and power modes',
        'icon': '⚙️',
        'action': 'pane:settings',
    },
]


@router.get('/global')
def global_search(q: str = Query('', description='Query string to search across all features')) -> dict[str, Any]:
    """Perform a comprehensive global search across panes, agents, memory, prompts, and skills."""
    t0 = time.time()
    query = q.strip().lower()
    results: list[dict[str, Any]] = []

    if not query:
        # Return top core navigation panes if query is empty
        return {
            'ok': True,
            'query': q,
            'count': len(_NAV_PANES[:8]),
            'results': _NAV_PANES[:8],
            'took_ms': round((time.time() - t0) * 1000, 2),
        }

    # 1. Search Navigation Panes
    for pane in _NAV_PANES:
        if query in pane['title'].lower() or query in pane['description'].lower() or query in pane['id'].lower():
            results.append(pane)

    # 2. Search Agents from database if available
    try:
        from ..services.memory_db import get_conn

        con = get_conn()
        cur = con.cursor()
        cur.execute(
            'SELECT id, name, description, capabilities FROM agents WHERE lower(name) LIKE ? OR lower(description) LIKE ? OR lower(capabilities) LIKE ? LIMIT 5',
            (f'%{query}%', f'%{query}%', f'%{query}%'),
        )
        for row in cur.fetchall():
            results.append(
                {
                    'id': f'agent-{row["id"]}',
                    'title': f'Agent: {row["name"]}',
                    'category': 'Agents',
                    'description': row['description'] or 'Specialized AI Agent',
                    'icon': '🤖',
                    'action': f'agent:{row["id"]}',
                }
            )
        con.close()
    except Exception:
        pass

    # 3. Search Prompts from database if available
    try:
        from ..services.memory_db import get_conn

        con = get_conn()
        cur = con.cursor()
        cur.execute(
            'SELECT id, title, prompt_text, category FROM prompts WHERE lower(title) LIKE ? OR lower(prompt_text) LIKE ? LIMIT 5',
            (f'%{query}%', f'%{query}%'),
        )
        for row in cur.fetchall():
            results.append(
                {
                    'id': f'prompt-{row["id"]}',
                    'title': f'Prompt: {row["title"]}',
                    'category': 'Prompts',
                    'description': (row['prompt_text'] or '')[:100] + '...',
                    'icon': '💡',
                    'action': f'prompt:{row["id"]}',
                }
            )
        con.close()
    except Exception:
        pass

    # 4. Search Marketplace Skills from built-in registry
    try:
        from .marketplace import CURATED_PACKS

        for pack in CURATED_PACKS:
            pack_id = pack['id']
            if query in pack['name'].lower() or query in pack['description'].lower() or query in pack['tags'].lower():
                results.append(
                    {
                        'id': f'pack-{pack_id}',
                        'title': f'Skill Pack: {pack["name"]}',
                        'category': 'Marketplace',
                        'description': pack['description'],
                        'icon': pack.get('icon', '📦'),
                        'action': f'marketplace:{pack_id}',
                    }
                )
            for skill in pack.get('skills', []):
                if (
                    query in skill['name'].lower()
                    or query in skill.get('description', '').lower()
                    or query in skill.get('prompt', '').lower()
                ):
                    results.append(
                        {
                            'id': f'skill-{skill["id"]}',
                            'title': f'Skill: {skill["name"]}',
                            'category': 'Marketplace Skills',
                            'description': skill.get('description', skill.get('prompt', '')[:100]),
                            'icon': skill.get('icon', '⚡'),
                            'action': f'skill:{skill["id"]}',
                        }
                    )
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        pass

    # 5. Search Autonomous Loops
    with contextlib.suppress(Exception):
        from ..services import scheduler as sched_svc
        for loop in sched_svc.list_loops():
            jid = str(loop.get('job_id', ''))
            l_prompt = str(loop.get('prompt', ''))
            if query in jid.lower() or query in l_prompt.lower():
                results.append({
                    'id': f'loop-{jid}',
                    'title': f'Loop: {jid}',
                    'category': 'Autonomous Loops',
                    'description': l_prompt[:100],
                    'icon': '♾️',
                    'action': f'loop-run:{jid}',
                })

    # 6. Search MCP Tools
    with contextlib.suppress(Exception):
        from .mcp import TOOLS
        for tname, tmeta in TOOLS.items():
            desc = str(tmeta.get('desc', ''))
            if query in tname.lower() or query in desc.lower():
                results.append({
                    'id': f'mcp-{tname}',
                    'title': f'MCP Tool: {tname}',
                    'category': 'MCP Tools',
                    'description': desc,
                    'icon': '🔧',
                    'action': f'mcp-tool:{tname}',
                })

    # 7. Search Memory Galaxy
    with contextlib.suppress(Exception):
        from ..services.memory_db import hybrid_search
        for mem in hybrid_search(query, limit=3):
            content = str(mem.get('content', ''))
            if content:
                results.append({
                    'id': f'mem-{mem.get("id", uuid.uuid4().hex[:6])}',
                    'title': f'Memory: {content[:40]}...',
                    'category': 'Memory Galaxy',
                    'description': content[:120],
                    'icon': '🌌',
                    'action': f'memory-insert:{content[:200]}',
                })

    return {
        'ok': True,
        'query': q,
        'count': len(results),
        'results': results[:30],
        'took_ms': round((time.time() - t0) * 1000, 2),
    }
