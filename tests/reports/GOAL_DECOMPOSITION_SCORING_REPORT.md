# Goal Decomposition & Outcome Scoring — Full Build & Verification Report
**Date:** 2026-07-14  
**Test Result: ✅ 66/66 tests PASSED (100%)**

---

## What Was Built

### Problem Found
The Goals pane (`pane-goals`) was a **completely blank white div** — `renderGoals()` was called from the nav patch via `renderGoals?.()` but was **never defined anywhere**. All the `goalCreate`, `goalView`, `goalLaunch` helper functions existed, but had no UI container to populate. The goal feature was essentially non-functional.

### Backend: 6 New Endpoints + 3 New DB Tables

#### New Tables (migrations applied)
| Table | Purpose |
|-------|---------|
| `goal_decompositions` | Persisted sub-tasks from AI decomposition (id, goal_id, seq, title, description, agent_hint, depends_on, risk_level, est_tokens, status) |
| `goal_score_history` | Score iteration history (id, goal_id, iteration, score, breakdown JSON, notes, scored_by, run_id, created_at) |
| **New columns on `goals_v2`** | `decomposition TEXT`, `outcome_score REAL`, `score_breakdown TEXT`, `last_scored_at TEXT`, `iteration INTEGER` |

#### New API Endpoints
| Endpoint | Description |
|----------|-------------|
| `POST /api/goals/{id}/decompose` | Brain LLM → task DAG with edges, caching, force-refresh |
| `GET  /api/goals/{id}/decompose` | Return cached decomposition (no LLM call) |
| `POST /api/goals/{id}/score` | Evaluator LLM → 5-dimension score + grade + actions |
| `GET  /api/goals/{id}/score/history` | All scoring iterations for a goal |
| `GET  /api/goals/{id}/score/latest` | Most recent score only |
| `GET  /api/goals/{id}/full` | All-in-one: goal + milestones + checkins + decomposition + score history |

---

### Backend: Decomposition System

**`POST /api/goals/{id}/decompose`**
- Calls Brain LLM with structured system prompt to produce a JSON task DAG
- Tasks have: seq, title, description, agent_hint, depends_on[], risk_level, est_tokens
- Builds dependency edge list from depends_on references
- Caches results in `goal_decompositions` table (subsequent calls return `cached: true`)
- `force: true` in body triggers re-decomposition
- Fallback: if LLM fails or returns empty, creates a sensible 4-task default (research → design → execute → review)
- Updates `goals_v2.decomposition` with a summary JSON

### Backend: Outcome Scoring System

**`POST /api/goals/{id}/score`**
- Gathers all evidence: title, description, criteria, deadline, milestones, check-ins, supervisor run output
- Calls Evaluator LLM to score 5 dimensions (0.0–1.0):
  - `completion` — how much defined work is done
  - `quality` — quality signals from check-ins and outputs
  - `on_schedule` — relative to deadline (1.0 if no deadline)
  - `criteria_met` — success criteria satisfaction
  - `momentum` — trend: improving, stalling, or regressing
- Returns: `overall`, `overall_pct`, `grade` (A+ → F), `dimensions`, `summary`, `strengths`, `gaps`, `next_actions`, `recommended_progress`
- Saves to `goal_score_history` with iteration counter
- Updates `goals_v2.outcome_score`, `score_breakdown`, `iteration`, `progress`
- Adds an `evaluator` check-in with score summary
- Fallback: if LLM fails, computes score from milestone completion % and check-in progress

---

### Frontend: Complete Goals Pane (from scratch)

**Replaced:** Nothing (pane was blank) → Full 2-panel layout

```
┌──────────────────────────────────────────────────────────────────┐
│  SIDEBAR (300px)              │  MAIN PANEL                       │
│  ────────────────────────     │  ──────────────────────────────── │
│  Stats (Total/Active/Avg%)    │  Goal title + badges              │
│  Filters (status/priority/    │  Progress bar + actions row       │
│  domain)                      │  ──── TABS ────────────────────── │
│                               │  Overview | Decompose | Score | History │
│  Goal cards (with progress    │  ──── TAB CONTENT ──────────────  │
│  bar + outcome score chip)    │  (varies by tab)                  │
│                               │                                   │
│  [+ New Goal]                 │                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### Overview Tab
- Description + Success Criteria (formatted blocks)
- Milestone list (click to complete, progress auto-recalculates)
- Check-in history with agent avatars + progress %
- Supervisor run link with "View DAG →" button

#### Decompose Tab
- Visual DAG canvas: SVG bezier edges + node cards (200px wide)
- Auto-layout algorithm (wave-based topological BFS → same x per wave, centered y)
- Node cards: seq badge (agent color) + title + agent icon + description preview
- Click node → shows detail panel with full description, dependencies, risk level
- "Re-decompose" button forces LLM refresh
- "Launch Supervisor with this Decomposition" button

#### Score Tab
- Score circle: percentage + letter grade (color-coded by grade)
- 5-dimension bar chart (completion, quality, on_schedule, criteria_met, momentum)
- Strengths list + Gaps list (2-column)
- Recommended Next Actions (numbered)
- "Re-score (Iteration N)" and "View History" buttons
- Empty state with "Score Outcome Now" CTA

#### History Tab
- Sparkline chart (SVG polyline, score trajectory over iterations)
- Score history table: Iteration | Score | Grade | Date | Notes
- Full check-in history with agent badges and timestamps

#### Create Goal Modal (replaces 6 sequential `gmPrompt()` dialogs)
- Single rich form: title, description, success criteria, domain, priority, deadline, tags
- Initial milestones list (add/remove inline)
- "Auto-decompose after creating" checkbox
- Instant keyboard focus on title field

---

## Demo Goals Seeded (5 total)

| Goal | Domain | Priority | Status | Progress | Score |
|------|--------|----------|--------|---------|-------|
| Build Agentic OS Python SDK | Work | Critical | Active | 68% | 72% (B-) |
| Competitive Analysis: Top 5 AI Platforms | Research | High | Done | 100% | 95% (A) |
| Launch Marketing Campaign for Agentic OS v7 | Work | High | Active | 25% | 38% (F) — AT RISK |
| Integrate Salesforce CRM Connector | Work | Medium | Paused | 5% | 5% (F) |
| Master Rust Programming Language | Learning | Low | Active | 35% | 58% (F→) |

Each goal includes: milestones, check-ins, decomposition tasks (3–8), score history (1–4 iterations).

---

## Test Coverage — 66 Tests

| Group | Tests | What's Verified |
|-------|-------|----------------|
| List & Stats | 7 | Array shape, all 3 filters, stats fields, domains list, new columns present |
| CRUD | 8 | Create, get, update, add checkin, add milestone, complete milestone, progress auto-update, 404 |
| Decomposition | 13 | ok=True, required fields, sequential seqs, no-deps first task, edge references, caching, force refresh, GET endpoint, DB update, SDK goal 8 tasks, 404 handling, valid agent hints, valid risk levels |
| Outcome Scoring | 11 | Returns ok, score in [0,1], valid grade letter, 5 dimensions all in [0,1], iteration increments, progress updated, outcome_score column updated, evaluator check-in added, 404 handling, done/at-risk goal scoring |
| Score History | 8 | Array shape, required fields, sequential iterations, latest matches last history, grade valid, unscored=False, demo iterations, trajectory increasing for done goal |
| Full Endpoint | 6 | Returns all 5 sections, decomposition tasks present, score history present, score_breakdown is dict, decomposition is list, 404 |
| Integration | 4 | Full lifecycle (create→decompose→checkin→score×2→verify), supervisor run link, all demo goals scoreable, persistent tasks |
| Frontend Contract | 8 | New columns in list, non-empty titles, next_actions field, recommended_progress is int, history has 5 dims, score_breakdown pre-parsed, depends_on pre-parsed, grade consistent with score |
| Cleanup | 1 | Delete test goal, confirmed gone |

---

*Backend: `/home/user/agentic-os/backend/routers/goal_manager.py` — 6 new endpoints + DB migrations*  
*Frontend: `/home/user/agentic-os/frontend/index.html` — complete `renderGoals()` implementation*  
*Tests: `/home/user/agentic-os/tests/connectors/test_goal_decomposition_scoring.py`*  
*Demo data: 5 goals with decompositions + score history in `memory/agentic.db`*
