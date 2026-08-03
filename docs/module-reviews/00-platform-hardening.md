# Platform hardening — test isolation & duplicate globals

**Commit:** `50cc986` · **Suite:** 2622 passed / 17 skipped / 0 failed · ruff clean

The two structural recommendations I'd been carrying across every module review,
closed together before continuing down the sidebar.

---

## 1. Test database isolation was fictional

`tests/unit/conftest.py` contained this, `autouse` and session-scoped:

```python
@pytest.fixture(scope="session", autouse=True)
def isolated_db(tmp_path_factory):
    """Create a fresh in-memory-style SQLite DB for the test session."""
    db_path = tmp_path_factory.mktemp("memory") / "test.db"
    os.environ["AGENTIC_TEST_DB"] = str(db_path)
```

**Nothing in the backend read that variable.** `grep -rn AGENTIC_TEST_DB backend/`
returned zero hits. Every suite wrote straight into `memory/agentic.db` — and
because the fixture was autouse, it looked protective in every test in the repo.

Proven by watching the production database across a single test file:

```
prompts before: 503
pytest tests/unit/test_08_sessions_prompts.py  →  25 passed
prompts after : 511
```

This is the root cause of an issue I'd flagged in six consecutive reviews, and it
twice degraded a fix while I was writing it:

| Review | Damage |
|---|---|
| Module 1 — Chat | 18 of 19 stored chat memories were error text |
| Module 4 — Memory | Poisoned memories skewed retrieval |
| Module 10 — Image Gen | Gallery state leaked between runs |
| Module 11 — Prompts | 614 prompts, only 212 distinct titles (44× duplicates) |
| Module 11 follow-up | Agents named `' OR '1'='1'; DROP TABLE agents; --` polluted a validation message I had *just added* |

### The fix, and the mistake I made getting there

`memory_db.db_path()` resolves the path **at call time**. That detail is the whole
fix: roughly 40 routers call `_ensure_schema()` at module scope, so a module-level
constant binds before any fixture can possibly run.

My first attempt set the env var in a fixture and produced **307 failures** — mass
HTTP 500 `no such table`. The routers had already created their schema against the
production path during import, so the sandbox was missing ~40 tables. The variable
now gets set at conftest **import** time, before any `backend.*` module loads, and
the fixture's only job is to *assert* isolation is genuinely in effect:

```python
assert resolved() == db_path, "test isolation is not in effect"
assert "memory/agentic.db" not in str(resolved()), "refusing to run against production data"
```

Two routers — `database.py` and `websearch.py` — opened a hardcoded path with their
own `sqlite3.connect()`, bypassing `get_conn()` entirely. Both now route through
`db_path()`.

### Live-server suites

These talk to a **separate process**, so no fixture can redirect them. `/api/health`
now reports `db_path` and `db_is_test_sandbox`, and all five live conftests assert
on it at session start — a warning by default, a hard failure under
`AGENTIC_REQUIRE_TEST_DB` (set for the CI `live-api` job).

### A test that was legitimately broken by this

`test_07_platform_stats_after_runs` asserted `total_evals > 0` unconditionally, and
only ever passed because the shared database already held eval history. Against a
clean database its eval-producing siblings skip (no AI provider), so there is
genuinely nothing to count. **It had been measuring leftover state, not behaviour.**
Exactly the class of false confidence the isolation was meant to expose.

---

## 2. Duplicate-globals CI lint

`frontend/js` has no module system — 63 scripts share one namespace via `window`.
Two files claiming the same name is silent, and *load-order dependent*: reorder a
`<script>` tag and behaviour changes with no code change.

`scripts/lint_globals.py` flags **cross-file collisions only**; same-file
reassignment (`window._chatCurrentPage = 3`) is ordinary mutable state. Deliberate
decorators are allowed via an explicit marker:

```js
// intentional-override: wraps core nav to add focus management
window.nav = function (pane) { origNav.apply(this, arguments); ... };
```

The marker must sit on or within three lines of the assignment, so one stray
comment can't licence an entire file.

### Triage — deliberately not blanket-marked

Seven names collided. Marking them all would have defeated the purpose, so each was
inspected:

| Global | Verdict |
|---|---|
| `nav` (10 files), `toast`, `switchHierarchyTab` | Genuine decorators — every one captures the original before wrapping. Marked with a specific reason each. |
| `S` | Back-compat Proxy re-bound after defaults are seeded. Marked. |
| `_ttsPlaying`, `_activeListenBtn` | Shared cross-file state, not competing definitions — both files write the same sentinel. Marked. |
| **`openCreateSkill`** | **A real bug.** |

### The real bug it found

Two divergent implementations of `openCreateSkill` existed. `25-skills.js` loads
later and silently won, making the `01-app-core.js` copy dead code — and they were
**not equivalent**:

```js
// 25-skills.js (wins)              // 01-app-core.js (dead)
try {                               const r = await fetch(...);
  const r = await fetch(...);       const j = await r.json();   // throws on
  if (!r.ok) { toast(...); return; }                            // a non-JSON
  ...                                                           // error body
} catch (ex) { toast(...); }
```

The dead copy lacked both the `try/catch` and the `response.ok` check. Had the load
order ever changed, the app would have silently regressed to the version that
throws on a server error. Removed.

---

## Tests

`tests/unit/test_62_platform_hardening.py` — **24 contracts**.

Eight of them run the linter against **synthetic frontend directories** rather than
just asserting on its source, proving it actually catches a clobber, allows a marked
override, ignores same-file reassignment and UMD shims, rejects a marker placed too
far away, and doesn't mistake `===` for an assignment.

The isolation tests write a row and then read **both** databases to confirm where it
actually landed — the failure mode here was precisely a check that looked right
without doing anything.

---

## Incidental

Fixed a pre-existing `B905` in `scripts/validate_frontend_api.py` — the `scripts/`
directory had simply never been linted. The `zip()` is provably safe (lengths are
equality-checked immediately above), so `strict=True` is the correct fix rather
than a suppression.

Noted but **not** fixed, as it predates this work and is unrelated:
`validate_frontend_api.py` reports 4 frontend API references absent from the
OpenAPI contract (`/api/chat/search`, `/api/onboarding/quick-setup`,
`/api/workspace/import`, `/api/workspace/stats`). Confirmed identical on a clean
checkout.

---

## Status

Both standing platform-wide recommendations are now closed. Remaining known items
are all module-scoped or environmental (Chromium unavailable in this sandbox; CSP
`'unsafe-inline'`; in-memory rate limiting; `config.yaml` version drift).
