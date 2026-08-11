# 87 — The review tracker (`scripts/audit/module_risk.py`)

**Subject:** the script that sequences this review
**Backend:** `scripts/audit/module_risk.py`
**Tests:** `tests/unit/test_162_module26_review_tracker.py` (18)
**Status:** reviewed, fixed, verified

Destination count after this pass: **20 of 20**.

---

## What happened

The queue said the next destinations were `imagegen` (score 14) and `prompts`
(14). Both looked untouched. Reading `backend/routers/imagegen.py` and
`backend/routers/prompts.py` told a different story: **8 and 4 `BUG FIX`
comments respectively**, each describing a defect reproduced live and fixed —
oversized uploads buffered before rejection, an HTML payload stored as
`fake.png`, an unescaped `alt=""` writing a live event handler into the user's
HTML, `INSERT OR IGNORE` against a fresh UUID that could never collide so
duplicate-title imports doubled the library every time.

Both had already been reviewed, in `docs/module-reviews/10-imagegen.md` and
`11-prompt-library.md`, during the early pane-based passes. Spot-probed live
before concluding anything, and the fixes still hold:

```
duplicate-title import twice -> imported 0, skipped 1
junk entries ["juststring",42,null] -> 200, 3 skipped, no 500
LIKE wildcard search "%"     -> 2 results, not the whole table
```

**The work was real. The bookkeeping was wrong.** So this pass reviews the
tracker instead.

## The defect

```python
reviewed_panes.update(re.findall(r'[a-z0-9][a-z0-9-]*', stem))
```

`[a-z0-9][a-z0-9-]*` matches hyphens, so `10-imagegen` produces the single token
`'10-imagegen'` — never `imagegen`. Every early review doc (`00-` … `42-`) has
that filename shape, and they name their subject only in a `**Surface:**` line
of *file paths*, which cannot credit a pane either. So an entire generation of
completed reviews was invisible to the tracker.

Correcting the tokeniser moved the count **13 → 19 in one step**. `prompts`
stayed uncredited because its filename (`11-prompt-library`) genuinely does not
contain its pane id; rather than loosen matching until it guessed correctly, its
doc now carries an explicit `**Pane:** \`prompts\`` header — the mechanism that
already exists for exactly this case. That took it to **20/20**.

I checked the jump rather than banking it: every newly-credited pane was
confirmed to have a real review document behind it (`browser` → `09-browser-agent.md`,
`templates` → `03-templates.md`, `websearch` → `08-websearch.md`,
`terminal` → `12-terminal.md`, and so on). No pane was credited without one.

### This is the third time

| Commit | The tracker's failure |
|---|---|
| `f4e6c22` | ranked panes instead of destinations |
| `c0156e1` | read only `**Pane:**`, so `**Destination:**`/`**Tabs:**` docs lost their tab coverage (evals showed 3/5 after all five were done) |
| this pass | the filename tokeniser swallowed the numeric prefix |

Each one sent the review back toward work already finished — the precise failure
the script exists to prevent. It had **no tests**. A tool that decides what gets
attention is load-bearing, and it was the only load-bearing thing here that
nothing verified.

## Revert-proof

**4 of 4 provable breakages caught.** The fifth is documented as unprovable
rather than claimed.

| # | Breakage | Result |
|---|---|---|
| 1 | numeric prefix hides the pane id | CAUGHT (1 test) |
| 1b | hyphen parts not credited | CAUGHT (1 test) |
| 2 | prompts doc loses its explicit header | CAUGHT (2 tests) |
| 3 | `Destination`/`Tabs` headers unread | CAUGHT (1 test) |
| 4 | tracker credits every pane unconditionally | **not observable — see below** |

### Three corrections this pass forced

**My first tests could not fail.** Breakages 3 and 4 went undetected because the
tests read `docs/module-risk.json` **off disk** — a committed artefact. Breaking
the *script* changes nothing that file can see. Running the script is the only
way to test the script; `_live_risk()` now regenerates before asserting.

**My revert-proof harness was itself broken.** It reported `MISSED` while
simultaneously printing the names of the failing tests — self-contradictory
output I should not have accepted. Two attempts to repair it (`RISK_BAK`
ordering, breaker tracing) did not fix it, so I stopped debugging the harness
and wrote a direct one: one subprocess per case, restore between, **exit code as
the authority instead of a regex over stdout**. It immediately gave consistent
results. When a measuring instrument and the thing it measures disagree, and the
instrument contradicts *itself*, replace the instrument.

**A test asserting the wrong pane.** My hyphen-split test asserted on
`workspaces`/`control` — both credited by other means, so it could never detect
the regression. Measuring which pane actually changed when the split was
disabled gave a single answer: **`browser`** (`09-browser-agent.md`,
`27-real-browser-e2e.md` — neither stem equals the pane id). Retargeted, and it
now fails when broken.

### The unprovable one, stated plainly

Forcing `row['reviewed'] = True` for every row fails no test. Measured cause:
all 20 destinations are now legitimately reviewed and each has a doc naming it,
so "credit everything" and "credit what is earned" produce **identical output** —
there is no input today that separates them. The assertion is kept because it
becomes load-bearing the moment a new pane is added, and the test carries that
caveat in its docstring. It is not counted as proven.

## Cross-module impact

- `scripts/audit/module_risk.py` — filename tokenising only; scoring, ranking
  and header parsing are unchanged.
- `docs/module-reviews/11-prompt-library.md` — gained a `**Pane:**` header.
- `docs/module-risk.json` regenerated: **20/20 reviewed**.
- No application code changed in this pass.

## Suite

`4170 unit (2 skipped)` + `664 regression/system/uat (1 skipped)` =
**4,834 passing, 0 failures**. Linters clean.

---

## Where the review stands

All 20 user-facing destinations are reviewed, each with a document and
regression tests. That is a milestone, not a finish line — the honest caveats:

- **Coverage is per-destination, not exhaustive.** Deep behavioural review went
  to the highest-risk surface in each; some sibling tabs got a render-and-
  handler check rather than a full pass.
- **Deferred by prior passes:** gap #4 (name the kernel) and #8 (scoped tool
  loading), both touching the agent runtime; `codesearch`'s `/memory`,
  `/suggestions`, `/review`, `/share`; the command palette's own search; the
  `tauri` pane.
- **Known environmental:** ~11k CSP `style-src` console messages;
  `test_120_audit_ratchet.py` runs ~9 min and is excluded from the fast loop;
  238 pre-existing ruff findings under `tests/` (the repo's lint scope is
  `backend scripts`).
- **Supabase endpoints in Database Studio** carry no audit logging while the
  SQLite paths have 18 audit points — noted in doc 86, not yet addressed.

The natural next step is a **consolidated report** across all 26 module docs —
the recurring defect patterns (confident reporting of unverified things; the
"second door", now 20 occurrences; nullable values crashing their consumers) and
what they suggest structurally.
