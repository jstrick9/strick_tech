"""
Agentic OS — Analytics & Dashboard Router
Real-time metrics: cost, token usage, agent activity, task velocity,
memory growth, swarm wins, skill usage, E2E pass rate.
"""

from __future__ import annotations

import contextlib

import csv
import datetime
import io
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.memory_db import get_conn

router = APIRouter(prefix='/api/analytics', tags=['analytics'])


def _safe_int(val, default: int = 0) -> int:
    return int(val) if val is not None else default


def _safe_float(val, default: float = 0.0) -> float:
    return float(val) if val is not None else default


def _clamp_days(days: int, min_days: int = 1, max_days: int = 365) -> int:
    return max(min_days, min(max_days, int(days)))


# ── Dashboard (full snapshot) ──────────────────────────────────────────────────


@router.get('/dashboard')
def dashboard(days: int = 30):
    """
    Full dashboard snapshot — all metrics in one call.
    Frontend polls this every 30s.
    """
    days = _clamp_days(days)
    con = get_conn()
    try:
        # ── Cost & tokens ──────────────────────────────────────────────
        cost_row = con.execute(
            'SELECT COALESCE(SUM(tokens),0) as total_tokens, COALESCE(SUM(cost),0) as total_cost FROM chat_log'
        ).fetchone()
        cost_by_agent = con.execute(
            """SELECT agent, COALESCE(SUM(tokens),0) as tokens, COALESCE(SUM(cost),0) as cost,
                      COUNT(*) as messages
               FROM chat_log GROUP BY agent ORDER BY cost DESC LIMIT 10"""
        ).fetchall()
        cost_over_time = con.execute(
            f"""SELECT date(created_at) as day, COALESCE(SUM(tokens),0) as tokens,
                       COALESCE(SUM(cost),0) as cost
                FROM chat_log
                WHERE created_at >= date('now', '-{days} days')
                GROUP BY day ORDER BY day""",
        ).fetchall()

        # ── Tasks ──────────────────────────────────────────────────────
        task_counts = con.execute('SELECT status, COUNT(*) as count FROM tasks GROUP BY status').fetchall()
        task_velocity = con.execute(
            f"""SELECT date(updated_at) as day, COUNT(*) as completed
                FROM tasks WHERE status='done' AND updated_at >= date('now', '-{days} days')
                GROUP BY day ORDER BY day""",
        ).fetchall()
        tasks_by_agent = con.execute(
            """SELECT agent, COUNT(*) as total,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done
               FROM tasks GROUP BY agent ORDER BY total DESC LIMIT 8"""
        ).fetchall()

        # ── Memory growth ──────────────────────────────────────────────
        mem_total = con.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        mem_by_source = con.execute(
            'SELECT source, COUNT(*) as count FROM memory GROUP BY source ORDER BY count DESC LIMIT 10'
        ).fetchall()
        mem_growth = con.execute(
            f"""SELECT date(created_at) as day, COUNT(*) as added
                FROM memory WHERE created_at >= date('now', '-{days} days')
                GROUP BY day ORDER BY day""",
        ).fetchall()

        # ── Agents ─────────────────────────────────────────────────────
        agents = con.execute('SELECT id, name, status, avatar, color FROM agents ORDER BY name').fetchall()
        agent_messages = con.execute('SELECT agent, COUNT(*) as messages FROM chat_log GROUP BY agent').fetchall()

        # ── Swarm ──────────────────────────────────────────────────────
        swarm_total = con.execute('SELECT COUNT(*) FROM swarm_history').fetchone()[0]
        swarm_wins = con.execute(
            "SELECT winner, COUNT(*) as wins FROM swarm_history WHERE winner != '' GROUP BY winner ORDER BY wins DESC"
        ).fetchall()

        # ── E2E ────────────────────────────────────────────────────────
        e2e_total = con.execute('SELECT COUNT(DISTINCT run_id) FROM e2e_traces').fetchone()[0]
        e2e_pass = con.execute("SELECT COUNT(DISTINCT run_id) FROM e2e_traces WHERE status='pass'").fetchone()[0]

        # ── Audit ──────────────────────────────────────────────────────
        audit_today = con.execute(
            "SELECT action, COUNT(*) as count FROM audit WHERE date(created_at)=date('now') GROUP BY action ORDER BY count DESC LIMIT 10"
        ).fetchall()
        recent_actions = con.execute(
            "SELECT action, detail, datetime(created_at,'localtime') as ts FROM audit ORDER BY id DESC LIMIT 20"
        ).fetchall()

        # ── Versions ───────────────────────────────────────────────────
        versions_total = con.execute('SELECT COUNT(*) FROM file_versions').fetchone()[0]
        versions_today = con.execute(
            "SELECT COUNT(*) FROM file_versions WHERE date(created_at)=date('now')"
        ).fetchone()[0]

        # ── Sessions ───────────────────────────────────────────────────
        sessions_total = 0
        sessions_today = 0
        try:
            sessions_total = con.execute('SELECT COUNT(*) FROM chat_sessions').fetchone()[0]
            sessions_today = con.execute(
                "SELECT COUNT(*) FROM chat_sessions WHERE date(created_at)=date('now')"
            ).fetchone()[0]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    finally:
        con.close()

    # ── Compute KPIs ───────────────────────────────────────────────
    total_tokens = _safe_int(cost_row['total_tokens'])
    total_cost = round(_safe_float(cost_row['total_cost']), 6)
    saved_vs_saas = round(max(0.0, 350.0 - total_cost * 100), 2)

    task_map = {r['status']: r['count'] for r in task_counts}
    total_tasks = sum(task_map.values())
    done_tasks = task_map.get('done', 0)
    completion_rate = round(done_tasks / total_tasks * 100) if total_tasks else 0

    agent_msg_map = {r['agent']: r['messages'] for r in agent_messages}
    total_messages = sum(r['messages'] for r in agent_messages)

    return {
        'generated_at': datetime.datetime.now().isoformat(),
        'period_days': days,
        'kpis': {
            'total_cost_usd': total_cost,
            'total_tokens': total_tokens,
            'saved_vs_saas_usd': saved_vs_saas,
            'total_messages': total_messages,
            'total_memories': mem_total,
            'total_tasks': total_tasks,
            'done_tasks': done_tasks,
            'completion_rate': completion_rate,
            'swarm_runs': swarm_total,
            'e2e_runs': e2e_total,
            'e2e_pass_rate': round(e2e_pass / e2e_total * 100) if e2e_total else 0,
            'file_versions': versions_total,
            'versions_today': versions_today,
            'sessions_total': sessions_total,
            'sessions_today': sessions_today,
        },
        'cost': {
            'by_agent': [dict(r) for r in cost_by_agent],
            'over_30_days': [dict(r) for r in cost_over_time],  # kept for compat
            'over_period': [dict(r) for r in cost_over_time],
        },
        'tasks': {
            'by_status': dict(task_map),
            'velocity_14d': [dict(r) for r in task_velocity],  # kept for compat
            'velocity': [dict(r) for r in task_velocity],
            'by_agent': [dict(r) for r in tasks_by_agent],
        },
        'memory': {
            'total': mem_total,
            'by_source': [dict(r) for r in mem_by_source],
            'growth_30d': [dict(r) for r in mem_growth],  # kept for compat
            'growth': [dict(r) for r in mem_growth],
        },
        'agents': [{**dict(a), 'messages': agent_msg_map.get(a['id'], 0)} for a in agents],
        'swarm': {
            'total_runs': swarm_total,
            'wins_by_agent': [dict(r) for r in swarm_wins],
        },
        'e2e': {
            'total_runs': e2e_total,
            'pass_count': e2e_pass,
            'pass_rate': round(e2e_pass / e2e_total * 100) if e2e_total else 0,
        },
        'activity': {
            'today': [dict(r) for r in audit_today],
            'recent': [dict(r) for r in recent_actions],
        },
    }


# ── KPIs only (fast polling) ───────────────────────────────────────────────────


@router.get('/kpis')
def get_kpis():
    """Return just the KPI numbers — lightweight endpoint for status bars."""
    con = get_conn()
    try:
        cost_row = con.execute(
            'SELECT COALESCE(SUM(tokens),0) as t, COALESCE(SUM(cost),0) as c FROM chat_log'
        ).fetchone()
        task_counts = con.execute('SELECT status, COUNT(*) as count FROM tasks GROUP BY status').fetchall()
        mem_total = con.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        swarm_total = con.execute('SELECT COUNT(*) FROM swarm_history').fetchone()[0]
        e2e_total = con.execute('SELECT COUNT(DISTINCT run_id) FROM e2e_traces').fetchone()[0]
        e2e_pass = con.execute("SELECT COUNT(DISTINCT run_id) FROM e2e_traces WHERE status='pass'").fetchone()[0]
        versions_total = con.execute('SELECT COUNT(*) FROM file_versions').fetchone()[0]
    finally:
        con.close()

    task_map = {r['status']: r['count'] for r in task_counts}
    total_tasks = sum(task_map.values())
    done_tasks = task_map.get('done', 0)

    return {
        'total_cost_usd': round(_safe_float(cost_row['c']), 6),
        'total_tokens': _safe_int(cost_row['t']),
        'total_memories': mem_total,
        'total_tasks': total_tasks,
        'done_tasks': done_tasks,
        'completion_rate': round(done_tasks / total_tasks * 100) if total_tasks else 0,
        'swarm_runs': swarm_total,
        'e2e_runs': e2e_total,
        'e2e_pass_rate': round(e2e_pass / e2e_total * 100) if e2e_total else 0,
        'file_versions': versions_total,
    }


# ── Activity feed ──────────────────────────────────────────────────────────────


@router.get('/activity')
def get_activity(limit: int = 50):
    """Return the recent audit/activity feed."""
    limit = _clamp_days(limit, 1, 200)
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT action, detail, datetime(created_at,'localtime') as ts FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        today = con.execute(
            "SELECT action, COUNT(*) as count FROM audit WHERE date(created_at)=date('now') GROUP BY action ORDER BY count DESC LIMIT 20"
        ).fetchall()
    finally:
        con.close()
    return {
        'recent': [dict(r) for r in rows],
        'today': [dict(r) for r in today],
        'count': len(rows),
    }


# ── Cost detail ────────────────────────────────────────────────────────────────


@router.get('/cost')
def cost_detail(days: int = 30):
    """Cost breakdown by agent and day."""
    days = _clamp_days(days)
    con = get_conn()
    try:
        rows = con.execute(
            f"""SELECT date(created_at) as day, agent,
                       COALESCE(SUM(tokens),0) as tokens,
                       COALESCE(SUM(cost),0)   as cost,
                       COUNT(*) as messages
                FROM chat_log
                WHERE created_at >= date('now', '-{days} days')
                GROUP BY day, agent ORDER BY day DESC, cost DESC""",
        ).fetchall()
        total = con.execute('SELECT COALESCE(SUM(tokens),0) as t, COALESCE(SUM(cost),0) as c FROM chat_log').fetchone()
    finally:
        con.close()

    totals_val = {'tokens': _safe_int(total['t']), 'cost': round(_safe_float(total['c']), 6)}
    return {
        'period_days': days,
        'rows': [dict(r) for r in rows],
        'totals': totals_val,
        'total': totals_val,  # alias for consistent API
    }


# ── Agents summary ─────────────────────────────────────────────────────────────


@router.get('/agents/summary')
def agents_summary():
    """Per-agent detailed statistics."""
    con = get_conn()
    try:
        agents = con.execute('SELECT id, name, status, avatar, color FROM agents ORDER BY name').fetchall()
        msg_data = con.execute(
            """SELECT agent, COUNT(*) as messages,
                      COALESCE(SUM(tokens),0) as tokens,
                      COALESCE(SUM(cost),0) as cost
               FROM chat_log GROUP BY agent"""
        ).fetchall()
        task_data = con.execute(
            """SELECT agent, COUNT(*) as total,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done
               FROM tasks GROUP BY agent"""
        ).fetchall()
    finally:
        con.close()

    msg_map = {r['agent']: dict(r) for r in msg_data}
    task_map = {r['agent']: dict(r) for r in task_data}

    result = []
    for a in agents:
        aid = a['id']
        m = msg_map.get(aid, {'messages': 0, 'tokens': 0, 'cost': 0})
        t = task_map.get(aid, {'total': 0, 'done': 0})
        result.append(
            {
                **dict(a),
                'messages': m.get('messages', 0),
                'tokens': _safe_int(m.get('tokens')),
                'cost': round(_safe_float(m.get('cost')), 6),
                'tasks_total': t.get('total', 0),
                'tasks_done': t.get('done', 0),
            }
        )
    return {'agents': result, 'count': len(result)}


# ── Tasks velocity ─────────────────────────────────────────────────────────────


@router.get('/tasks/velocity')
def task_velocity(days: int = 14):
    """Task completion velocity over time."""
    days = _clamp_days(days)
    con = get_conn()
    try:
        rows = con.execute(
            f"""SELECT date(updated_at) as day, status, COUNT(*) as count
                FROM tasks WHERE updated_at >= date('now', '-{days} days')
                GROUP BY day, status ORDER BY day""",
        ).fetchall()
    finally:
        con.close()
    return {'period_days': days, 'data': [dict(r) for r in rows]}


# ── Memory growth ──────────────────────────────────────────────────────────────


@router.get('/memory/growth')
def memory_growth(days: int = 30):
    """Memory addition rate over time."""
    days = _clamp_days(days)
    con = get_conn()
    try:
        rows = con.execute(
            f"""SELECT date(created_at) as day, source, COUNT(*) as added
                FROM memory WHERE created_at >= date('now', '-{days} days')
                GROUP BY day, source ORDER BY day""",
        ).fetchall()
    finally:
        con.close()
    return {'period_days': days, 'data': [dict(r) for r in rows]}


# ── Swarm history ──────────────────────────────────────────────────────────────


@router.get('/swarm/runs')
def swarm_runs(limit: int = 20):
    """Recent swarm run history."""
    limit = _clamp_days(limit, 1, 100)
    con = get_conn()
    try:
        rows = con.execute(
            """SELECT id, run_id, prompt, agents, strategy, winner,
                      judge_reason, total_latency_ms, total_tokens,
                      datetime(created_at,'localtime') as created_at
               FROM swarm_history ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    return {'runs': [dict(r) for r in rows], 'count': len(rows)}


# ── Session stats ──────────────────────────────────────────────────────────────


@router.get('/sessions')
def sessions_stats():
    """Chat session statistics."""
    con = get_conn()
    try:
        try:
            total = con.execute('SELECT COUNT(*) FROM chat_sessions').fetchone()[0]
            today = con.execute("SELECT COUNT(*) FROM chat_sessions WHERE date(created_at)=date('now')").fetchone()[0]
            by_agent = con.execute(
                'SELECT agent_id, COUNT(*) as count FROM chat_sessions GROUP BY agent_id ORDER BY count DESC'
            ).fetchall()
            recent = con.execute(
                """SELECT id, name, agent_id, message_count,
                          datetime(updated_at,'localtime') as updated_at
                   FROM chat_sessions ORDER BY updated_at DESC LIMIT 10"""
            ).fetchall()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            return {'ok': False, 'error': 'chat_sessions table not available', 'total': 0}
    finally:
        con.close()

    return {
        'ok': True,
        'total': total,
        'today': today,
        'by_agent': [dict(r) for r in by_agent],
        'recent': [dict(r) for r in recent],
    }


# ── Export ─────────────────────────────────────────────────────────────────────


@router.get('/export')
def export_dashboard(fmt: str = 'csv', days: int = 30):
    """Export dashboard data as CSV or JSON."""
    days = _clamp_days(days)
    con = get_conn()
    try:
        cost_rows = con.execute(
            f"""SELECT date(created_at) as day, agent,
                       COALESCE(SUM(tokens),0) as tokens,
                       COALESCE(SUM(cost),0) as cost,
                       COUNT(*) as messages
                FROM chat_log WHERE created_at >= date('now', '-{days} days')
                GROUP BY day, agent ORDER BY day DESC""",
        ).fetchall()
    finally:
        con.close()

    if fmt == 'json':
        return {'period_days': days, 'cost_by_day_agent': [dict(r) for r in cost_rows]}

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['day', 'agent', 'tokens', 'cost_usd', 'messages'])
    for r in cost_rows:
        writer.writerow([r['day'], r['agent'], r['tokens'], round(_safe_float(r['cost']), 6), r['messages']])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=analytics-{days}d.csv'},
    )
