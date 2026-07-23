"""
Agentic OS — Agent Leaderboard + Governance Dashboard
Track which of your agents performs best, governance policies,
discovery of all running agents, and policy enforcement.

Inspired by:
- Arthur AI's Agent Discovery & Governance (ADG)
- AWS AgentCore observability
- Rubrik Agent Cloud (safe undo, agent management)
"""

from __future__ import annotations

import contextlib

import json
import logging

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/agent-leaderboard', tags=['agent_leaderboard'])
log = logging.getLogger('agentic.leaderboard')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_performance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    task_type   TEXT DEFAULT 'general',
    success     INTEGER DEFAULT 1,
    tokens      INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0,
    latency_ms  INTEGER DEFAULT 0,
    user_rating INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS agent_policies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT DEFAULT '*',
    policy_type TEXT NOT NULL,
    policy_rule TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, policy_type, policy_rule)
);
CREATE INDEX IF NOT EXISTS idx_ap_agent ON agent_performance(agent_id, created_at);
"""

STARTER_POLICIES = [
    ('*', 'rate_limit', 'Max 100 calls per agent per hour'),
    ('*', 'cost_cap', 'Max $1.00 per agent per day'),
    ('*', 'no_secrets', 'Never include API keys or passwords in output'),
    ('*', 'no_pii', 'Do not store or output personal identifying information'),
    ('builder', 'read_write', 'Can read and write preview/ files'),
    ('researcher', 'read_only', 'Read-only access to all resources'),
]


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed starter policies — INSERT OR IGNORE respects UNIQUE constraint
        for agent_id, ptype, rule in STARTER_POLICIES:
            con.execute(
                'INSERT OR IGNORE INTO agent_policies(agent_id,policy_type,policy_rule) VALUES (?,?,?)',
                (agent_id, ptype, rule),
            )
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _safe_int(val, default: int = 0) -> int:
    """Convert possibly-None DB value to int."""
    return int(val) if val is not None else default


def _safe_float(val, default: float = 0.0) -> float:
    """Convert possibly-None DB value to float."""
    return float(val) if val is not None else default


def record_performance(
    agent_id: str,
    task_type: str = 'general',
    success: bool = True,
    tokens: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int = 0,
) -> None:
    """Record a performance event for an agent."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO agent_performance(agent_id,task_type,success,tokens,cost_usd,latency_ms) VALUES (?,?,?,?,?,?)',
            (agent_id, task_type, 1 if success else 0, tokens, cost_usd, latency_ms),
        )
        con.commit()
    finally:
        con.close()


# ── REST endpoints ─────────────────────────────────────────────────────────────


@router.get('')
def leaderboard(limit: int = 20, days: int = 30, task_type: str = ''):
    """Agent leaderboard ranked by success rate, then total calls."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where_task = 'AND ap.task_type=:task_type' if task_type else ''
        rows = con.execute(
            f"""
            SELECT
                ap.agent_id,
                a.name, a.avatar, a.color,
                COUNT(*) as total_calls,
                SUM(ap.success) as successes,
                AVG(ap.latency_ms) as avg_latency,
                SUM(ap.tokens) as total_tokens,
                SUM(ap.cost_usd) as total_cost,
                AVG(CASE WHEN ap.user_rating > 0 THEN ap.user_rating END) as avg_rating,
                ROUND(100.0*SUM(ap.success)/COUNT(*), 1) as success_rate
            FROM agent_performance ap
            LEFT JOIN agents a ON a.id = ap.agent_id
            WHERE ap.created_at >= datetime('now', '-{int(days)} days')
            {where_task}
            GROUP BY ap.agent_id
            ORDER BY success_rate DESC, total_calls DESC
            LIMIT :limit
        """,
            {'task_type': task_type, 'limit': min(limit, 100)},
        ).fetchall()
    except Exception as ex:
        log.warning('leaderboard query error: %s', ex)
        rows = []
    finally:
        con.close()

    results = []
    for r in rows:
        d = dict(r)
        d['successes'] = _safe_int(d.get('successes'))
        d['total_tokens'] = _safe_int(d.get('total_tokens'))
        d['total_cost'] = _safe_float(d.get('total_cost'))
        d['avg_rating'] = round(_safe_float(d.get('avg_rating')), 2)
        d['avg_latency'] = round(_safe_float(d.get('avg_latency')), 1)
        d['success_rate'] = _safe_float(d.get('success_rate'))
        results.append(d)

    return {'leaderboard': results, 'days': days, 'task_type': task_type or 'all'}


@router.post('/record')
async def record_event(req: Request):
    """Record an agent performance event manually."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    agent_id = (body.get('agent_id') or '').strip()
    if not agent_id:
        return {'ok': False, 'error': 'agent_id required'}
    try:
        record_performance(
            agent_id=agent_id,
            task_type=(body.get('task_type') or 'general').strip()[:64],
            success=bool(body.get('success', True)),
            tokens=max(0, int(body.get('tokens', 0))),
            cost_usd=max(0.0, float(body.get('cost_usd', 0))),
            latency_ms=max(0, int(body.get('latency_ms', 0))),
        )
        return {'ok': True}
    except Exception as ex:
        log.error('record_event error: %s', ex)
        return {'ok': False, 'error': str(ex)}


@router.get('/agent/{agent_id}')
def agent_stats(agent_id: str, days: int = 30):
    """Detailed stats for a single agent."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        summary = con.execute(
            f"""
            SELECT COUNT(*) as total,
                   COALESCE(SUM(success), 0) as successes,
                   COALESCE(AVG(latency_ms), 0) as avg_latency,
                   COALESCE(SUM(tokens), 0) as tokens,
                   COALESCE(SUM(cost_usd), 0) as cost,
                   MIN(created_at) as first_call,
                   AVG(CASE WHEN user_rating > 0 THEN user_rating END) as avg_rating
            FROM agent_performance
            WHERE agent_id=? AND created_at >= datetime('now','-{int(days)} days')
        """,
            (agent_id,),
        ).fetchone()

        by_type = con.execute(
            f"""
            SELECT task_type,
                   COUNT(*) as calls,
                   COALESCE(SUM(success), 0) as successes,
                   ROUND(100.0*SUM(success)/COUNT(*), 1) as success_rate
            FROM agent_performance
            WHERE agent_id=? AND created_at >= datetime('now','-{int(days)} days')
            GROUP BY task_type ORDER BY calls DESC
        """,
            (agent_id,),
        ).fetchall()

        recent = con.execute(
            """
            SELECT * FROM agent_performance
            WHERE agent_id=? ORDER BY created_at DESC LIMIT 20
        """,
            (agent_id,),
        ).fetchall()
    finally:
        con.close()

    d = dict(summary) if summary else {}
    total = _safe_int(d.get('total'))
    successes = _safe_int(d.get('successes'))
    d['total'] = total
    d['successes'] = successes
    d['avg_latency'] = round(_safe_float(d.get('avg_latency')), 1)
    d['tokens'] = _safe_int(d.get('tokens'))
    d['cost'] = _safe_float(d.get('cost'))
    d['avg_rating'] = round(_safe_float(d.get('avg_rating')), 2)
    d['success_rate'] = round(100 * successes / max(total, 1), 1)

    return {
        'agent_id': agent_id,
        'summary': d,
        'by_type': [dict(r) for r in by_type],
        'recent': [dict(r) for r in recent],
    }


@router.post('/rate')
async def rate_agent(req: Request):
    """Rate the last agent interaction (1-5 stars)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    agent_id = (body.get('agent_id') or '').strip()
    if not agent_id:
        return {'ok': False, 'error': 'agent_id required'}
    rating = min(5, max(1, int(body.get('rating', 3))))
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """
            UPDATE agent_performance SET user_rating=? WHERE agent_id=? AND id=(
                SELECT id FROM agent_performance WHERE agent_id=? ORDER BY created_at DESC LIMIT 1
            )
        """,
            (rating, agent_id, agent_id),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'rating': rating}


# ── Governance / Policies ──────────────────────────────────────────────────────


@router.get('/policies')
def list_policies(agent_id: str = ''):
    """Retrieve and return list policies."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        if agent_id:
            rows = con.execute(
                "SELECT * FROM agent_policies WHERE agent_id=? OR agent_id='*' ORDER BY agent_id,policy_type",
                (agent_id,),
            ).fetchall()
        else:
            rows = con.execute('SELECT * FROM agent_policies ORDER BY agent_id,policy_type').fetchall()
    finally:
        con.close()
    return {'policies': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/policies')
async def create_policy(req: Request):
    """Create and initialize a new policy."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    agent_id = (body.get('agent_id') or '*').strip()[:64]
    policy_type = (body.get('policy_type') or 'custom').strip()[:64]
    policy_rule = (body.get('policy_rule') or '').strip()[:500]
    if not policy_rule:
        return {'ok': False, 'error': 'policy_rule required'}
    enabled = 1 if body.get('enabled', True) else 0
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT OR IGNORE INTO agent_policies(agent_id,policy_type,policy_rule,enabled) VALUES (?,?,?,?)',
            (agent_id, policy_type, policy_rule, enabled),
        )
        pid = con.execute(
            'SELECT id FROM agent_policies WHERE agent_id=? AND policy_type=? AND policy_rule=?',
            (agent_id, policy_type, policy_rule),
        ).fetchone()
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'id': pid['id'] if pid else None}


@router.put('/policies/{policy_id}')
async def update_policy(policy_id: int, req: Request):
    """Toggle or update a policy."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        sets, vals = [], []
        if 'enabled' in body:
            sets.append('enabled=?')
            vals.append(1 if body['enabled'] else 0)
        if 'policy_rule' in body:
            rule = (body['policy_rule'] or '').strip()[:500]
            if rule:
                sets.append('policy_rule=?')
                vals.append(rule)
        if not sets:
            return {'ok': False, 'error': 'No fields to update'}
        vals.append(policy_id)
        cur = con.execute(f'UPDATE agent_policies SET {",".join(sets)} WHERE id=?', vals)
        con.commit()
        ok = cur.rowcount > 0
    finally:
        con.close()
    return {'ok': ok, 'id': policy_id}


@router.delete('/policies/{policy_id}')
def delete_policy(policy_id: int):
    """Delete or remove specified policy."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        cur = con.execute('DELETE FROM agent_policies WHERE id=?', (policy_id,))
        con.commit()
        deleted = cur.rowcount > 0
    finally:
        con.close()
    return {'ok': deleted, 'id': policy_id}


# ── Agent Discovery (like Arthur AI ADG) ──────────────────────────────────────


@router.get('/discover')
def discover_agents():
    """Discover all agents, their status, recent activity, and policy compliance."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        agents = con.execute('SELECT * FROM agents ORDER BY status DESC, name').fetchall()

        # Recent performance per agent
        activity = {}
        for r in con.execute("""
            SELECT agent_id, COUNT(*) as calls, MAX(created_at) as last_call,
                   ROUND(100.0*SUM(success)/COUNT(*), 1) as success_rate
            FROM agent_performance GROUP BY agent_id
        """).fetchall():
            activity[r['agent_id']] = dict(r)

        # Check active loops (graceful — table may not exist)
        loops: dict = {}
        try:
            for r in con.execute('SELECT agent_id FROM loops WHERE enabled=1').fetchall():
                if r.get('agent_id'):
                    loops[r['agent_id']] = True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass  # loops table doesn't exist yet

        # Count policies per agent
        policy_counts: dict = {}
        try:
            for r in con.execute(
                'SELECT agent_id, COUNT(*) as cnt FROM agent_policies WHERE enabled=1 GROUP BY agent_id'
            ).fetchall():
                policy_counts[r['agent_id']] = r['cnt']
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    except Exception as ex:
        log.warning('discover_agents error: %s', ex)
        agents = []
        activity = {}
        loops = {}
        policy_counts = {}
    finally:
        con.close()

    discovered = []
    for a in agents:
        d = dict(a)
        act = activity.get(a['id'], {})
        d['total_calls'] = _safe_int(act.get('calls'))
        d['last_active'] = act.get('last_call') or 'never'
        d['success_rate'] = _safe_float(act.get('success_rate'))
        d['has_loop'] = bool(loops.get(a['id'], False))
        d['policy_count'] = _safe_int(policy_counts.get(a['id'])) + _safe_int(policy_counts.get('*'))
        d['risk_level'] = 'high' if d['has_loop'] else ('medium' if d['total_calls'] > 100 else 'low')
        discovered.append(d)

    return {
        'agents': discovered,
        'total': len(discovered),
        'active': sum(1 for d in discovered if d.get('status') == 'active'),
        'has_loops': sum(1 for d in discovered if d.get('has_loop')),
    }


@router.get('/governance/summary')
def governance_summary():
    """High-level governance health."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total_agents = con.execute('SELECT COUNT(*) FROM agents WHERE enabled=1').fetchone()[0]
        total_policies = con.execute('SELECT COUNT(*) FROM agent_policies WHERE enabled=1').fetchone()[0]
        recent_calls = con.execute(
            "SELECT COUNT(*) FROM agent_performance WHERE created_at > datetime('now','-1 day')"
        ).fetchone()[0]
        error_row = con.execute(
            "SELECT AVG(CASE WHEN success=0 THEN 1.0 ELSE 0 END) FROM agent_performance WHERE created_at > datetime('now','-7 days')"
        ).fetchone()
        error_rate = _safe_float(error_row[0] if error_row else None)

        # HITL pending — graceful
        hitl_pending = 0
        with contextlib.suppress(Exception):
            hitl_pending = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='pending'").fetchone()[0]
    except Exception as ex:
        log.warning('governance_summary error: %s', ex)
        total_agents = total_policies = hitl_pending = recent_calls = 0
        error_rate = 0.0
    finally:
        con.close()

    health = 'good'
    if error_rate > 0.15 or hitl_pending > 10:
        health = 'attention_needed'
    elif error_rate > 0.05 or hitl_pending > 2:
        health = 'warning'

    return {
        'active_agents': total_agents,
        'active_policies': total_policies,
        'pending_approvals': hitl_pending,
        'calls_24h': recent_calls,
        'error_rate_7d': round(error_rate * 100, 1),
        'health': health,
    }


@router.delete('/performance/{agent_id}')
def clear_agent_performance(agent_id: str):
    """Clear all performance records for an agent (admin use)."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        cur = con.execute('DELETE FROM agent_performance WHERE agent_id=?', (agent_id,))
        con.commit()
        deleted = cur.rowcount
    finally:
        con.close()
    return {'ok': True, 'deleted': deleted, 'agent_id': agent_id}


@router.get('/stats/overview')
def stats_overview(days: int = 30):
    """Overall performance stats across all agents."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute(f"""
            SELECT COUNT(*) as total_calls,
                   COUNT(DISTINCT agent_id) as active_agents,
                   COALESCE(SUM(success), 0) as total_successes,
                   COALESCE(SUM(tokens), 0) as total_tokens,
                   COALESCE(SUM(cost_usd), 0) as total_cost,
                   COALESCE(AVG(latency_ms), 0) as avg_latency
            FROM agent_performance
            WHERE created_at >= datetime('now', '-{int(days)} days')
        """).fetchone()
        task_dist = con.execute(f"""
            SELECT task_type, COUNT(*) as calls
            FROM agent_performance
            WHERE created_at >= datetime('now', '-{int(days)} days')
            GROUP BY task_type ORDER BY calls DESC
        """).fetchall()
    finally:
        con.close()

    d = dict(row) if row else {}
    total = _safe_int(d.get('total_calls'))
    succ = _safe_int(d.get('total_successes'))
    return {
        'days': days,
        'total_calls': total,
        'active_agents': _safe_int(d.get('active_agents')),
        'total_successes': succ,
        'success_rate': round(100 * succ / max(total, 1), 1),
        'total_tokens': _safe_int(d.get('total_tokens')),
        'total_cost': round(_safe_float(d.get('total_cost')), 6),
        'avg_latency': round(_safe_float(d.get('avg_latency')), 1),
        'task_distribution': [dict(r) for r in task_dist],
    }
