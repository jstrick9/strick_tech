"""
Agentic OS — Behavior Drift Detection Engine
═════════════════════════════════════════════
Continuously monitors every agent's behavioral fingerprint and detects
when outputs diverge from their established baseline patterns.

Architecture:
  Baseline fingerprint  — rolling 7-day statistical profile per agent
                          (mean, stddev, p50/p90/p99 for latency, tokens, cost, error rate)
  Drift measurement     — compute z-scores for current 1h/6h/24h windows vs baseline
  Composite drift score — weighted combination of all z-scores → 0–100 score
  Severity buckets      — none(<10) / low(10-25) / medium(25-45) / high(45-70) / critical(>70)
  Trend detection       — stable / improving / degrading / volatile
  Auto-alerting         — create drift_alerts for score thresholds; recommend kill for critical
  History               — time-series of drift scores per agent for sparkline charts

Tables used:
  agent_performance       — raw per-task measurements (existing)
  agent_drift_fingerprints — 7-day statistical baseline per agent
  agent_drift_scores      — timestamped composite drift scores
  drift_alerts            — escalated notifications with recommended actions
  anomaly_events          — existing anomaly events (bridged)
"""

from __future__ import annotations

import contextlib

import json
import logging
import math
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/drift', tags=['drift'])
log = logging.getLogger('agentic.drift')

ROOT = Path(__file__).resolve().parents[2]

# ── Schema (tables created in seeding; ensure they exist) ─────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_drift_fingerprints (
    fingerprint_id  TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    window_hours    INTEGER NOT NULL DEFAULT 168,
    computed_at     TEXT NOT NULL DEFAULT '',
    lat_mean        REAL NOT NULL DEFAULT 0,
    lat_p50         REAL NOT NULL DEFAULT 0,
    lat_p90         REAL NOT NULL DEFAULT 0,
    lat_p99         REAL NOT NULL DEFAULT 0,
    lat_stddev      REAL NOT NULL DEFAULT 0,
    tok_mean        REAL NOT NULL DEFAULT 0,
    tok_p50         REAL NOT NULL DEFAULT 0,
    tok_p90         REAL NOT NULL DEFAULT 0,
    tok_stddev      REAL NOT NULL DEFAULT 0,
    cost_mean       REAL NOT NULL DEFAULT 0,
    cost_p90        REAL NOT NULL DEFAULT 0,
    cost_stddev     REAL NOT NULL DEFAULT 0,
    error_rate_mean REAL NOT NULL DEFAULT 0,
    tasks_per_hour  REAL NOT NULL DEFAULT 0,
    total_samples   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(agent_id, window_hours)
);
CREATE TABLE IF NOT EXISTS agent_drift_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    computed_at     TEXT NOT NULL DEFAULT '',
    window_label    TEXT NOT NULL DEFAULT '1h',
    lat_zscore      REAL NOT NULL DEFAULT 0,
    tok_zscore      REAL NOT NULL DEFAULT 0,
    cost_zscore     REAL NOT NULL DEFAULT 0,
    err_zscore      REAL NOT NULL DEFAULT 0,
    vol_zscore      REAL NOT NULL DEFAULT 0,
    drift_score     REAL NOT NULL DEFAULT 0,
    severity        TEXT NOT NULL DEFAULT 'none',
    trend           TEXT NOT NULL DEFAULT 'stable',
    sample_count    INTEGER NOT NULL DEFAULT 0,
    flags           TEXT NOT NULL DEFAULT '[]',
    action          TEXT NOT NULL DEFAULT 'none',
    detail          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drift_alerts (
    alert_id        TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    score_id        INTEGER NOT NULL DEFAULT 0,
    severity        TEXT NOT NULL DEFAULT 'medium',
    drift_score     REAL NOT NULL DEFAULT 0,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    flags           TEXT NOT NULL DEFAULT '[]',
    recommended_action TEXT NOT NULL DEFAULT 'monitor',
    acknowledged    INTEGER NOT NULL DEFAULT 0,
    resolved        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT '',
    acknowledged_at TEXT NOT NULL DEFAULT '',
    resolved_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_adf_agent ON agent_drift_fingerprints(agent_id);
CREATE INDEX IF NOT EXISTS idx_ads_agent ON agent_drift_scores(agent_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_severity ON agent_drift_scores(severity, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_da_agent ON drift_alerts(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_da_unresolved ON drift_alerts(resolved, severity);
"""


def _get_conn():
    from ..services.memory_db import get_conn

    return get_conn()


def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


# ── Statistical helpers ────────────────────────────────────────────────────────
def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    idx = int(n * p / 100)
    return s[min(idx, n - 1)]


def _zscore(value: float, mean: float, stddev: float) -> float:
    """Compute z-score. Returns 0 if stddev is 0 or mean is 0."""
    if stddev < 1e-9 or mean < 1e-9:
        # If there's no variance in baseline, check absolute change
        if mean > 1e-9:
            return abs(value - mean) / (mean * 0.1)  # treat 10% of mean as 1σ
        return 0.0
    return (value - mean) / stddev


def _drift_severity(score: float) -> str:
    if score < 10:
        return 'none'
    if score < 25:
        return 'low'
    if score < 45:
        return 'medium'
    if score < 70:
        return 'high'
    return 'critical'


def _drift_score_to_color(score: float) -> str:
    if score < 10:
        return '#3dba7a'
    if score < 25:
        return '#5b8af8'
    if score < 45:
        return '#e8a237'
    if score < 70:
        return '#f06080'
    return '#e85252'


# Drift dimension weights (sum = 1.0)
_WEIGHTS = {
    'err': 0.35,  # Error rate deviation — highest weight (most critical)
    'lat': 0.25,  # Latency deviation
    'cost': 0.20,  # Cost deviation
    'tok': 0.12,  # Token deviation
    'vol': 0.08,  # Volume (task rate) deviation
}
# Score scale: each z-score contributes weight * min(z, 5) * 20 → max 100
_SCORE_MULTIPLIER = 20


# ── Core drift computation ─────────────────────────────────────────────────────
def compute_fingerprint(agent_id: str, window_hours: int = 168) -> dict:
    """
    Compute and persist a behavioral fingerprint for agent_id using
    data from the last window_hours (default 7 days = 168h).
    Excludes the last 1 hour (the "current" window).
    Returns the fingerprint dict.
    """
    con = _get_conn()
    try:
        rows = con.execute(
            """
            SELECT latency_ms, cost_usd, tokens, success
            FROM agent_performance
            WHERE agent_id=?
              AND created_at > datetime('now', ?)
              AND created_at < datetime('now', '-1 hour')
        """,
            (agent_id, f'-{window_hours} hours'),
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return {'ok': False, 'error': 'Insufficient baseline data', 'agent_id': agent_id}

    lats = [r['latency_ms'] for r in rows if (r['latency_ms'] or 0) > 0]
    costs = [r['cost_usd'] for r in rows if (r['cost_usd'] or 0) > 0]
    toks = [r['tokens'] for r in rows if (r['tokens'] or 0) > 0]
    errs = [(1 - (r['success'] or 0)) for r in rows]
    n = len(rows)

    def _stats(vals):
        if not vals:
            return 0, 0, 0, 0, 0
        s = sorted(vals)
        m = len(s)
        mean = sum(s) / m
        var = sum((x - mean) ** 2 for x in s) / m if m > 1 else 0
        return mean, _percentile(s, 50), _percentile(s, 90), _percentile(s, 99), math.sqrt(var)

    lm, lp50, lp90, lp99, lstd = _stats(lats)
    tm, tp50, tp90, _, tstd = _stats(toks)
    cm, cp50, cp90, _, cstd = _stats(costs)
    err_mean = sum(errs) / len(errs) if errs else 0.0
    tph = n / max(window_hours, 1)

    fp_id = f'fp_{agent_id}'
    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT OR REPLACE INTO agent_drift_fingerprints
            (fingerprint_id,agent_id,window_hours,computed_at,
             lat_mean,lat_p50,lat_p90,lat_p99,lat_stddev,
             tok_mean,tok_p50,tok_p90,tok_stddev,
             cost_mean,cost_p90,cost_stddev,
             error_rate_mean,tasks_per_hour,total_samples)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                fp_id,
                agent_id,
                window_hours,
                now,
                lm,
                lp50,
                lp90,
                lp99,
                lstd,
                tm,
                tp50,
                tp90,
                tstd,
                cm,
                cp90,
                cstd,
                err_mean,
                tph,
                n,
            ),
        )
        con.commit()
    finally:
        con.close()

    return {
        'ok': True,
        'fingerprint_id': fp_id,
        'agent_id': agent_id,
        'window_hours': window_hours,
        'total_samples': n,
        'computed_at': now,
        'lat_mean': round(lm, 2),
        'lat_p90': round(lp90, 2),
        'lat_stddev': round(lstd, 2),
        'tok_mean': round(tm, 2),
        'cost_mean': round(cm, 6),
        'error_rate_mean': round(err_mean, 4),
        'tasks_per_hour': round(tph, 3),
    }


def compute_drift_score(agent_id: str, window_label: str = '1h') -> dict:
    """
    Measure current behavior vs baseline fingerprint.
    Returns a full drift assessment with per-dimension z-scores,
    composite score (0–100), severity, trend, flags, and recommended action.
    """
    hours = {'1h': 1, '6h': 6, '24h': 24}.get(window_label, 1)

    # Load fingerprint
    con = _get_conn()
    try:
        fp = con.execute(
            'SELECT * FROM agent_drift_fingerprints WHERE agent_id=? AND window_hours=168', (agent_id,)
        ).fetchone()
        if not fp:
            return {'ok': False, 'error': 'No baseline fingerprint. Run /fingerprint first.', 'agent_id': agent_id}
        fp = dict(fp)

        # Current window data
        cur = con.execute(
            """
            SELECT latency_ms, cost_usd, tokens, success
            FROM agent_performance
            WHERE agent_id=? AND created_at > datetime('now', ?)
        """,
            (agent_id, f'-{hours} hours'),
        ).fetchall()

        # Previous same-window data (for trend)
        prev = con.execute(
            """
            SELECT latency_ms, cost_usd, tokens, success
            FROM agent_performance
            WHERE agent_id=?
              AND created_at > datetime('now', ?)
              AND created_at < datetime('now', ?)
        """,
            (agent_id, f'-{hours * 2} hours', f'-{hours} hours'),
        ).fetchall()

        # Previous drift scores for trend detection
        prev_scores = con.execute(
            """
            SELECT drift_score FROM agent_drift_scores
            WHERE agent_id=? AND window_label=?
            ORDER BY computed_at DESC LIMIT 5
        """,
            (agent_id, window_label),
        ).fetchall()
    finally:
        con.close()

    if not cur:
        return {
            'ok': True,
            'agent_id': agent_id,
            'window_label': window_label,
            'drift_score': 0.0,
            'severity': 'none',
            'trend': 'insufficient_data',
            'sample_count': 0,
            'flags': [],
            'message': 'No data in measurement window',
        }

    # Current window metrics
    c_lats = [r['latency_ms'] for r in cur if (r['latency_ms'] or 0) > 0]
    c_costs = [r['cost_usd'] for r in cur if (r['cost_usd'] or 0) > 0]
    c_toks = [r['tokens'] for r in cur if (r['tokens'] or 0) > 0]
    c_errs = [(1 - (r['success'] or 0)) for r in cur]

    c_lat_mean = sum(c_lats) / len(c_lats) if c_lats else 0
    c_cost_mean = sum(c_costs) / len(c_costs) if c_costs else 0
    c_tok_mean = sum(c_toks) / len(c_toks) if c_toks else 0
    c_err_rate = sum(c_errs) / len(c_errs) if c_errs else 0
    c_tph = len(cur) / max(hours, 1)

    # Compute z-scores vs baseline
    lat_z = abs(_zscore(c_lat_mean, fp['lat_mean'], fp['lat_stddev']))
    tok_z = abs(_zscore(c_tok_mean, fp['tok_mean'], fp['tok_stddev']))
    cost_z = abs(_zscore(c_cost_mean, fp['cost_mean'], fp['cost_stddev']))
    err_z = abs(_zscore(c_err_rate, fp['error_rate_mean'], max(fp['error_rate_mean'] * 0.5, 0.01)))
    vol_z = abs(_zscore(c_tph, fp['tasks_per_hour'], max(fp['tasks_per_hour'] * 0.3, 0.1)))

    # Composite drift score (0–100)
    composite = min(
        100.0,
        (
            _WEIGHTS['lat'] * min(lat_z, 8)
            + _WEIGHTS['tok'] * min(tok_z, 8)
            + _WEIGHTS['cost'] * min(cost_z, 8)
            + _WEIGHTS['err'] * min(err_z, 8)
            + _WEIGHTS['vol'] * min(vol_z, 8)
        )
        * _SCORE_MULTIPLIER,
    )

    severity = _drift_severity(composite)

    # Flag specific dimensions that are elevated
    flags = []
    if lat_z > 2.0:
        flags.append('latency_spike')
    if lat_z > 4.0:
        flags.append('severe_latency')
    if tok_z > 2.0:
        flags.append('token_spike')
    if tok_z > 4.0:
        flags.append('token_explosion')
    if cost_z > 2.0:
        flags.append('cost_spike')
    if cost_z > 5.0:
        flags.append('cost_explosion')
    if err_z > 2.0:
        flags.append('error_rate')
    if err_z > 5.0:
        flags.append('reliability_drop')
    if vol_z > 3.0:
        flags.append('volume_anomaly')
    if c_err_rate > 0.5:
        flags.append('high_failure_rate')

    # Trend: compare current score vs recent history
    recent_scores = [r['drift_score'] for r in prev_scores]
    if len(recent_scores) >= 2:
        delta = composite - recent_scores[0]  # vs last score
        variance = statistics.stdev(recent_scores) if len(recent_scores) > 1 else 0
        if variance > 20:
            trend = 'volatile'
        elif delta > 5:
            trend = 'degrading'
        elif delta < -5:
            trend = 'improving'
        else:
            trend = 'stable'
    elif len(recent_scores) == 1:
        delta = composite - recent_scores[0]
        trend = 'degrading' if delta > 5 else ('improving' if delta < -5 else 'stable')
    else:
        trend = 'stable' if composite < 15 else 'degrading'

    # Recommended action
    action = 'none'
    if severity == 'critical':
        action = 'kill_recommended'
    elif severity == 'high' and trend == 'degrading' or severity in ('medium', 'high'):
        action = 'alerted'

    # Build detail string
    detail_parts = []
    if lat_z > 1.5:
        detail_parts.append(f'latency {c_lat_mean:.0f}ms ({lat_z:.1f}σ above baseline {fp["lat_mean"]:.0f}ms)')
    if err_z > 1.5:
        detail_parts.append(f'error rate {c_err_rate:.1%} ({err_z:.1f}σ above baseline {fp["error_rate_mean"]:.1%})')
    if cost_z > 1.5:
        detail_parts.append(f'cost ${c_cost_mean:.5f}/task ({cost_z:.1f}σ above baseline)')
    if tok_z > 1.5:
        detail_parts.append(f'tokens {c_tok_mean:.0f}/task ({tok_z:.1f}σ above baseline)')
    detail = '; '.join(detail_parts) if detail_parts else f'score {composite:.1f} — {trend}'

    # Persist the score
    now = _now()
    con = _get_conn()
    try:
        cur_result = con.execute(
            """
            INSERT INTO agent_drift_scores
            (agent_id,computed_at,window_label,lat_zscore,tok_zscore,cost_zscore,
             err_zscore,vol_zscore,drift_score,severity,trend,sample_count,flags,action,detail)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                agent_id,
                now,
                window_label,
                round(lat_z, 3),
                round(tok_z, 3),
                round(cost_z, 3),
                round(err_z, 3),
                round(vol_z, 3),
                round(composite, 2),
                severity,
                trend,
                len(cur),
                json.dumps(flags),
                action,
                detail[:500],
            ),
        )
        score_id = cur_result.lastrowid

        # Create drift alert if threshold crossed
        alert_created = False
        if severity in ('high', 'critical'):
            existing = con.execute(
                """
                SELECT alert_id FROM drift_alerts
                WHERE agent_id=? AND resolved=0 AND severity=?
                  AND created_at > datetime('now', '-2 hours')
            """,
                (agent_id, severity),
            ).fetchone()
            if not existing:
                alert_id = f'da_{uuid.uuid4().hex[:10]}'
                rec_action = 'kill_agent' if severity == 'critical' else 'restart_agent'
                title = f'{"Critical" if severity == "critical" else "High"} Behavior Drift: {agent_id}'
                desc = f'Agent {agent_id} drift score {composite:.1f}/100 ({severity}). {detail}'
                con.execute(
                    """
                    INSERT INTO drift_alerts
                    (alert_id,agent_id,score_id,severity,drift_score,title,description,
                     flags,recommended_action,acknowledged,resolved,created_at,acknowledged_at,resolved_at)
                    VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?,?)
                """,
                    (
                        alert_id,
                        agent_id,
                        score_id,
                        severity,
                        composite,
                        title,
                        desc,
                        json.dumps(flags),
                        rec_action,
                        now,
                        '',
                        '',
                    ),
                )
                alert_created = True

                # Also write to anomaly_events for compatibility
                try:
                    con.execute(
                        """
                        INSERT INTO anomaly_events
                        (agent_id,event_type,severity,detail,metric_name,metric_val,baseline,created_at)
                        VALUES (?,?,?,?,?,?,?,?)
                    """,
                        (
                            agent_id,
                            'behavior_drift',
                            severity,
                            f'Drift score {composite:.1f} — {",".join(flags)}',
                            'drift_score',
                            composite,
                            0.0,
                            now,
                        ),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
                    pass

        con.commit()
    finally:
        con.close()

    log.info('Drift[%s] score=%.1f sev=%s trend=%s flags=%s', agent_id, composite, severity, trend, flags)

    return {
        'ok': True,
        'agent_id': agent_id,
        'window_label': window_label,
        'computed_at': now,
        'score_id': score_id,
        'drift_score': round(composite, 2),
        'severity': severity,
        'trend': trend,
        'sample_count': len(cur),
        'flags': flags,
        'action': action,
        'alert_created': alert_created,
        'detail': detail,
        'dimensions': {
            'latency': {
                'zscore': round(lat_z, 3),
                'current': round(c_lat_mean, 2),
                'baseline': round(fp['lat_mean'], 2),
                'baseline_stddev': round(fp['lat_stddev'], 2),
            },
            'tokens': {
                'zscore': round(tok_z, 3),
                'current': round(c_tok_mean, 2),
                'baseline': round(fp['tok_mean'], 2),
                'baseline_stddev': round(fp['tok_stddev'], 2),
            },
            'cost': {
                'zscore': round(cost_z, 3),
                'current': round(c_cost_mean, 6),
                'baseline': round(fp['cost_mean'], 6),
                'baseline_stddev': round(fp['cost_stddev'], 6),
            },
            'error_rate': {
                'zscore': round(err_z, 3),
                'current': round(c_err_rate, 4),
                'baseline': round(fp['error_rate_mean'], 4),
                'baseline_stddev': 0,
            },
            'volume': {
                'zscore': round(vol_z, 3),
                'current': round(c_tph, 3),
                'baseline': round(fp['tasks_per_hour'], 3),
                'baseline_stddev': 0,
            },
        },
    }


def run_all_agents_drift(window_label: str = '1h') -> list[dict]:
    """Run drift detection for all enabled agents."""
    con = _get_conn()
    try:
        agents = con.execute('SELECT id FROM agents WHERE enabled=1').fetchall()
    finally:
        con.close()
    results = []
    for a in agents:
        aid = a['id']
        # Build fingerprint if it doesn't exist
        con = _get_conn()
        try:
            fp = con.execute('SELECT fingerprint_id FROM agent_drift_fingerprints WHERE agent_id=?', (aid,)).fetchone()
        finally:
            con.close()
        if not fp:
            compute_fingerprint(aid)
        result = compute_drift_score(aid, window_label)
        if result.get('ok'):
            results.append(result)
    return results


# ── API Routes ─────────────────────────────────────────────────────────────────


@router.get('/summary')
def drift_summary():
    """
    Platform-wide drift summary: headline numbers for the dashboard.
    Returns current drift state for all agents + alert counts.
    """
    con = _get_conn()
    try:
        # Latest score per agent
        latest = con.execute("""
            SELECT a.agent_id, a.drift_score, a.severity, a.trend, a.computed_at, a.flags, a.action
            FROM agent_drift_scores a
            INNER JOIN (
                SELECT agent_id, MAX(computed_at) max_at
                FROM agent_drift_scores GROUP BY agent_id
            ) b ON a.agent_id=b.agent_id AND a.computed_at=b.max_at
        """).fetchall()

        alerts_unresolved = con.execute('SELECT COUNT(*) FROM drift_alerts WHERE resolved=0').fetchone()[0]
        alerts_critical = con.execute(
            "SELECT COUNT(*) FROM drift_alerts WHERE resolved=0 AND severity='critical'"
        ).fetchone()[0]
        alerts_high = con.execute("SELECT COUNT(*) FROM drift_alerts WHERE resolved=0 AND severity='high'").fetchone()[
            0
        ]

        fingerprint_count = con.execute('SELECT COUNT(*) FROM agent_drift_fingerprints').fetchone()[0]

        score_count = con.execute('SELECT COUNT(*) FROM agent_drift_scores').fetchone()[0]
    finally:
        con.close()

    agents_by_severity = {'none': 0, 'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
    agent_summaries = []
    for row in latest:
        r = dict(row)
        sev = r.get('severity', 'none')
        agents_by_severity[sev] = agents_by_severity.get(sev, 0) + 1
        try:
            r['flags'] = json.loads(r.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            r['flags'] = []
        agent_summaries.append(r)

    return {
        'agents': agent_summaries,
        'agents_by_severity': agents_by_severity,
        'total_agents_tracked': len(agent_summaries),
        'alerts_unresolved': alerts_unresolved,
        'alerts_critical': alerts_critical,
        'alerts_high': alerts_high,
        'fingerprints': fingerprint_count,
        'total_scores': score_count,
    }


@router.post('/detect')
async def detect_all(req: Request):
    """
    Run drift detection for all enabled agents (1h window).
    Computes/updates fingerprints if needed, then measures current drift.
    Returns per-agent results sorted by drift score descending.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    window = body.get('window', '1h')
    if window not in ('1h', '6h', '24h'):
        window = '1h'

    results = run_all_agents_drift(window)
    results.sort(key=lambda r: r.get('drift_score', 0), reverse=True)

    total_flagged = sum(1 for r in results if r.get('severity', 'none') != 'none')
    return {
        'ok': True,
        'window': window,
        'agents_checked': len(results),
        'agents_flagged': total_flagged,
        'results': results,
    }


@router.post('/detect/{agent_id}')
async def detect_agent(agent_id: str, req: Request):
    """
    Run drift detection for a single agent.
    Also computes/refreshes fingerprint if stale (>2h old).
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    window = body.get('window', '1h')
    if window not in ('1h', '6h', '24h'):
        window = '1h'

    # Refresh fingerprint if older than 2h
    con = _get_conn()
    try:
        fp = con.execute(
            'SELECT computed_at FROM agent_drift_fingerprints WHERE agent_id=? AND window_hours=168', (agent_id,)
        ).fetchone()
    finally:
        con.close()

    fp_refreshed = False
    if not fp:
        compute_fingerprint(agent_id)
        fp_refreshed = True
    else:
        try:
            computed = datetime.fromisoformat(fp['computed_at'])
            age_hours = (datetime.now(timezone.utc) - computed).total_seconds() / 3600
            if age_hours > 2:
                compute_fingerprint(agent_id)
                fp_refreshed = True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            pass

    result = compute_drift_score(agent_id, window)
    result['fingerprint_refreshed'] = fp_refreshed
    return result


@router.post('/fingerprint')
async def build_fingerprints(req: Request):
    """
    Recompute behavioral fingerprints for all (or specified) agents.
    This establishes the baseline that drift is measured against.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    agent_ids = body.get('agent_ids') or []
    window = int(body.get('window_hours', 168))

    if not agent_ids:
        con = _get_conn()
        try:
            agents = con.execute('SELECT id FROM agents WHERE enabled=1').fetchall()
        finally:
            con.close()
        agent_ids = [a['id'] for a in agents]

    results = []
    for aid in agent_ids:
        r = compute_fingerprint(aid, window)
        results.append(r)

    return {
        'ok': True,
        'computed': len([r for r in results if r.get('ok')]),
        'failed': len([r for r in results if not r.get('ok')]),
        'results': results,
    }


@router.post('/fingerprint/{agent_id}')
async def build_fingerprint_single(agent_id: str, req: Request):
    """Recompute fingerprint for a single agent."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    window = int(body.get('window_hours', 168))
    return compute_fingerprint(agent_id, window)


@router.get('/fingerprint/{agent_id}')
def get_fingerprint(agent_id: str):
    """Get the current baseline fingerprint for an agent."""
    con = _get_conn()
    try:
        fp = con.execute(
            'SELECT * FROM agent_drift_fingerprints WHERE agent_id=? AND window_hours=168', (agent_id,)
        ).fetchone()
    finally:
        con.close()
    if not fp:
        return JSONResponse({'ok': False, 'error': 'No fingerprint computed yet'}, status_code=404)
    return {'ok': True, 'fingerprint': dict(fp)}


@router.get('/scores/{agent_id}')
def get_agent_scores(agent_id: str, window_label: str = '', limit: int = 100):
    """Get drift score history for an agent (for sparkline charts)."""
    con = _get_conn()
    try:
        if window_label:
            rows = con.execute(
                """
                SELECT * FROM agent_drift_scores
                WHERE agent_id=? AND window_label=?
                ORDER BY computed_at DESC LIMIT ?
            """,
                (agent_id, window_label, min(limit, 500)),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT * FROM agent_drift_scores
                WHERE agent_id=?
                ORDER BY computed_at DESC LIMIT ?
            """,
                (agent_id, min(limit, 500)),
            ).fetchall()
    finally:
        con.close()

    scores = []
    for r in rows:
        d = dict(r)
        try:
            d['flags'] = json.loads(d.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            d['flags'] = []
        scores.append(d)
    return {'agent_id': agent_id, 'scores': scores, 'count': len(scores)}


@router.get('/alerts')
def list_alerts(
    severity: str = '',
    resolved: bool = False,
    agent_id: str = '',
    limit: int = 50,
):
    """List drift alerts with filters."""
    where, params = ['resolved=?'], [1 if resolved else 0]
    if severity:
        where.append('severity=?')
        params.append(severity)
    if agent_id:
        where.append('agent_id=?')
        params.append(agent_id)
    params.append(min(limit, 200))

    con = _get_conn()
    try:
        rows = con.execute(
            f'SELECT * FROM drift_alerts WHERE {" AND ".join(where)} ORDER BY created_at DESC LIMIT ?', params
        ).fetchall()
    finally:
        con.close()

    alerts = []
    for r in rows:
        d = dict(r)
        try:
            d['flags'] = json.loads(d.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            d['flags'] = []
        alerts.append(d)
    return {'alerts': alerts, 'count': len(alerts)}


@router.post('/alerts/{alert_id}/acknowledge')
def acknowledge_alert(alert_id: str):
    """Acknowledge a drift alert (mark as seen, not resolved)."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM drift_alerts WHERE alert_id=?', (alert_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Alert not found'}, status_code=404)
        con.execute('UPDATE drift_alerts SET acknowledged=1, acknowledged_at=? WHERE alert_id=?', (_now(), alert_id))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'alert_id': alert_id, 'acknowledged': True}


@router.post('/alerts/{alert_id}/resolve')
def resolve_alert(alert_id: str):
    """Mark a drift alert as resolved."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM drift_alerts WHERE alert_id=?', (alert_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Alert not found'}, status_code=404)
        con.execute('UPDATE drift_alerts SET resolved=1, resolved_at=? WHERE alert_id=?', (_now(), alert_id))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'alert_id': alert_id, 'resolved': True}


@router.get('/agent/{agent_id}')
def get_agent_drift_detail(agent_id: str):
    """
    Full drift profile for one agent:
    fingerprint + latest score + score history (last 24h) + active alerts.
    """
    con = _get_conn()
    try:
        fp = con.execute(
            'SELECT * FROM agent_drift_fingerprints WHERE agent_id=? AND window_hours=168', (agent_id,)
        ).fetchone()
        latest_score = con.execute(
            """
            SELECT * FROM agent_drift_scores
            WHERE agent_id=? ORDER BY computed_at DESC LIMIT 1
        """,
            (agent_id,),
        ).fetchone()
        scores_24h = con.execute(
            """
            SELECT id,computed_at,window_label,drift_score,severity,trend,flags,sample_count,action
            FROM agent_drift_scores
            WHERE agent_id=? AND computed_at > datetime('now', '-24 hours')
            ORDER BY computed_at ASC
        """,
            (agent_id,),
        ).fetchall()
        alerts = con.execute(
            """
            SELECT * FROM drift_alerts WHERE agent_id=? AND resolved=0
            ORDER BY created_at DESC LIMIT 10
        """,
            (agent_id,),
        ).fetchall()
    finally:
        con.close()

    def parse_flags(d):
        """Execute or process parse flags operation."""
        try:
            d['flags'] = json.loads(d.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            d['flags'] = []
        return d

    return {
        'ok': True,
        'agent_id': agent_id,
        'fingerprint': dict(fp) if fp else None,
        'latest_score': parse_flags(dict(latest_score)) if latest_score else None,
        'scores_24h': [parse_flags(dict(r)) for r in scores_24h],
        'active_alerts': [parse_flags(dict(r)) for r in alerts],
    }


@router.get('/history')
def drift_history(hours: int = 24, limit: int = 200):
    """All drift scores across all agents for the given period, sorted by score desc."""
    con = _get_conn()
    try:
        rows = con.execute(
            """
            SELECT agent_id, computed_at, window_label, drift_score, severity, trend, flags, action
            FROM agent_drift_scores
            WHERE computed_at > datetime('now', ?)
            ORDER BY drift_score DESC, computed_at DESC LIMIT ?
        """,
            (f'-{hours} hours', min(limit, 1000)),
        ).fetchall()
    finally:
        con.close()

    results = []
    for r in rows:
        d = dict(r)
        try:
            d['flags'] = json.loads(d.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            d['flags'] = []
        results.append(d)
    return {'history': results, 'count': len(results), 'hours': hours}


@router.get('/leaderboard')
def drift_leaderboard():
    """
    Returns all agents ranked by their current drift score (highest first).
    Includes trend direction and severity for the heatmap.
    """
    con = _get_conn()
    try:
        rows = con.execute("""
            SELECT a.agent_id, a.drift_score, a.severity, a.trend, a.flags,
                   a.lat_zscore, a.tok_zscore, a.cost_zscore, a.err_zscore, a.vol_zscore,
                   a.computed_at, a.action, a.sample_count
            FROM agent_drift_scores a
            INNER JOIN (
                SELECT agent_id, MAX(computed_at) max_at
                FROM agent_drift_scores GROUP BY agent_id
            ) b ON a.agent_id=b.agent_id AND a.computed_at=b.max_at
            ORDER BY a.drift_score DESC
        """).fetchall()
    finally:
        con.close()

    entries = []
    for r in rows:
        d = dict(r)
        try:
            d['flags'] = json.loads(d.get('flags', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            d['flags'] = []
        d['color'] = _drift_score_to_color(d.get('drift_score', 0))
        entries.append(d)

    return {'leaderboard': entries, 'count': len(entries)}
