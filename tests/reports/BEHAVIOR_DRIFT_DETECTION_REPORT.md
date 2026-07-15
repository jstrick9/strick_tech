# Behavior Drift Detection — Full Build & Verification Report
**Date:** 2026-07-15  
**Test Result: ✅ 70/70 tests PASSED (100%)**

---

## What Was Built

### New Backend Router: `/api/drift` (12 endpoints)

Complete new FastAPI router at `backend/routers/drift.py` (core engine + API):

| Endpoint | Description |
|----------|-------------|
| `GET  /api/drift/summary`                   | Platform-wide drift overview: agents by severity, alert counts, fingerprint count |
| `GET  /api/drift/leaderboard`               | All agents ranked by current drift score, with color codes |
| `GET  /api/drift/history`                   | Recent drift scores across all agents (last N hours) |
| `POST /api/drift/detect`                    | Run detection for all enabled agents (1h/6h/24h windows) |
| `POST /api/drift/detect/{agent_id}`         | Run detection for one agent, with auto-fingerprint refresh |
| `POST /api/drift/fingerprint`               | Build/refresh baselines for all agents |
| `POST /api/drift/fingerprint/{agent_id}`    | Build baseline for one agent |
| `GET  /api/drift/fingerprint/{agent_id}`    | Retrieve current baseline fingerprint |
| `GET  /api/drift/scores/{agent_id}`         | Drift score time-series for one agent |
| `GET  /api/drift/agent/{agent_id}`          | Full drift profile: fingerprint + latest score + 24h history + active alerts |
| `GET  /api/drift/alerts`                    | List drift alerts with filters (severity, resolved, agent_id) |
| `POST /api/drift/alerts/{id}/acknowledge`   | Acknowledge an alert (seen, not resolved) |
| `POST /api/drift/alerts/{id}/resolve`       | Mark alert as resolved |

### 3 New DB Tables

| Table | Purpose |
|-------|---------|
| `agent_drift_fingerprints` | Rolling statistical baseline per agent: mean, p50, p90, p99, stddev for latency/tokens/cost + error rate + task volume |
| `agent_drift_scores` | Timestamped composite drift scores: per-dimension z-scores, composite 0–100 score, severity, trend, flags, action |
| `drift_alerts` | Escalated notifications: title, description, recommended_action, acknowledged/resolved state |

---

## Detection Engine Architecture

```
agent_performance (raw data)
        │
        ▼
compute_fingerprint()  ──→  agent_drift_fingerprints
  • 7-day rolling window (excludes last 1h)
  • Computes: mean, p50, p90, p99, stddev
  • Metrics: latency, tokens, cost, error_rate, tasks_per_hour
        │
        ▼
compute_drift_score()  ──→  agent_drift_scores + drift_alerts
  • Measures current 1h/6h/24h window vs fingerprint baseline
  • 5 z-scores: latency, tokens, cost, error_rate, volume
  • Composite score = weighted sum of capped z-scores × 20
  • Severity: none(<10) / low(10-25) / medium(25-45) / high(45-70) / critical(>70)
  • Trend: stable/improving/degrading/volatile (from score history comparison)
  • Flags: specific anomalies (latency_spike, cost_explosion, reliability_drop…)
  • Action: none → alerted → kill_recommended
  • Auto-creates drift_alert for high/critical (deduped per 2h)
  • Bridges to existing anomaly_events table for compatibility
```

### Dimension Weights

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Error rate | 35% | Highest — reliability signal |
| Latency | 25% | Performance signal |
| Cost | 20% | Financial signal |
| Tokens | 12% | Behavioral signal |
| Volume | 8% | Activity signal |

---

## Demo Data Seeded

**5 agents × 7 days historical performance:**
- ~1,300 new performance records (baseline data)

**Drift scenarios (realistic):**
| Agent | Scenario | Score | Severity | Trend |
|-------|---------|-------|----------|-------|
| researcher | Critical escalation: latency 3.6x, cost 4.0x, error rate 7.2σ | 88.7 | critical | degrading |
| reviewer | High drift: error rate 6.5σ, latency 1.4x | 55.9 | high | degrading |
| creative | Low drift: minor latency increase, improving | 7.2 | none | improving |
| builder | Stable: all metrics within 0.3σ | 3.8 | none | stable |
| brain | Stable: minimal deviation | 1.5 | none | stable |

**3 drift fingerprints** (7-day baselines for each agent)  
**15 drift score history entries** (3 per agent showing trajectory)  
**3 drift alerts** (critical, high, low severity)

---

## Frontend: Complete 5-Tab Behavior Drift Detection Center

**Replaced:** Simple agent card grid (renderAgentMonitor)  
**Built:** Full 5-tab Drift Detection Center

```
┌──────────────────────────────────────────────────────────────────┐
│  SIDEBAR (220px)           │  MAIN PANEL                         │
│  ─────────────────────     │  ──────────────────────────────── │
│  📊 Dashboard              │  Tab content                        │
│  🤖 Agent Scores           │                                     │
│  ⚠️ Alerts (badge)         │                                     │
│  📈 History                │                                     │
│  ─────────────────────     │                                     │
│  📡 Live Monitor           │                                     │
│  ─────────────────────     │                                     │
│  [🔍 Run Detection]        │                                     │
└──────────────────────────────────────────────────────────────────┘
```

### 📊 Dashboard Tab
- Severity distribution bar (color-coded 5-segment bar)
- 6-metric stats grid (total, critical, high, medium, alerts, avg score)
- Critical agents banner with one-click Kill / Details buttons
- Full leaderboard: score bar chart, severity badge, trend icon (↗/↘/→/↕), flags, action badge
- Click any agent → jump to detail view

### 🤖 Agent Scores Tab
- All agents as cards with circular score gauges (color-coded)
- Click → full detail view per agent:
  - **Score header**: gauge, trend, computed time, detail text, action buttons
  - **Active alerts panel** for this agent
  - **5-dimension z-score bars**: current vs baseline for each metric
  - **Baseline fingerprint panel**: lat mean/p90/stddev, tokens, cost, error rate, tasks/hr, sample count
  - **24h sparkline chart**: SVG polyline with colored dots per severity, severity reference lines

### ⚠️ Alerts Tab
- Alert cards with severity color border, icon, title, description
- Metadata: score value, recommended action (monitor/restart/kill), timestamp
- Action buttons: 👁 Acknowledge / 🔍 Inspect / ✓ Resolve
- Kill button shown for kill_agent recommended actions
- Resolved alerts section below

### 📈 History Tab
- Sortable table: timestamp, agent, window, score, severity badge, trend, flags, action
- Click row → navigate to agent detail
- Covers last 24 hours by default

### 📡 Live Monitor Tab
- Preserved from original agent monitor (live status, session costs, kill/revive buttons)
- Kill button now links to drift-aware kill function

### 15-second background poll
- Auto-refreshes alert badge count without full re-render
- Stops when pane is not active

---

## Test Coverage — 70 Tests

| Group | Tests | What's Verified |
|-------|-------|----------------|
| Summary | 6 | All fields, agent count, alerts count, by_severity structure, agent fields, critical agent |
| Leaderboard | 6 | Array shape, sorted desc, required fields, researcher=highest, relative ordering, color codes |
| History | 5 | Array shape, required fields, sorted by score, all agents covered, critical entries |
| Fingerprint | 6 | Get researcher, all stat fields, percentile ordering, single build, all-agents build, 404 |
| Detection | 11 | Returns ok, score range, 5 dimensions, flags, auto-stores, fingerprint_refresh, all-agents, sort, 6h window, action field |
| Agent Profile | 7 | All 4 sections, fingerprint match, latest score, scores_24h array, chronological order, active alerts, stable agent |
| Score History | 4 | Array shape, required fields, window filter, sorted most-recent-first |
| Alerts | 8 | Array shape, required fields, critical exists, severity filter, agent filter, acknowledge, resolve, 404 |
| Statistical Correctness | 5 | Critical > stable, score-severity correlation, stddev positive, valid trend values, builder stable |
| Frontend Contract | 12 | Color field, ASC order for sparkline, flags as lists, 5 dimensions, ok field, valid actions, count match, score_id int, window echo, trend strings, [0–100] range, full E2E cycle |

---

*Backend: `/home/user/agentic-os/backend/routers/drift.py` (new, complete engine)*  
*App: `/home/user/agentic-os/backend/app.py` — drift router registered*  
*Frontend: `/home/user/agentic-os/frontend/index.html` — complete 5-tab Drift Detection Center*  
*Tests: `/home/user/agentic-os/tests/connectors/test_drift_detection.py`*  
*DB: 3 new tables, ~1,300 seeded performance records, 5 fingerprints, 15 score entries, 3 alerts*
