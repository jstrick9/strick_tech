# Module 18 — Workspaces

*(consolidated pane: `workspaces`, absorbing `collabedit` and `control`)*

Routers: `backend/routers/workspaces.py`, `collab.py`, `control_tower.py`
Frontend: `30-workspaces.js`, `31-control-tower.js`, `32-collaboration.js`

**Five bugs, all reproduced against a live server before being fixed. Two of
them destroyed user work irrecoverably.**

---

## The headline: two unrecoverable data-loss paths

### 1. Activating the workspace you are already on

`activate_workspace()` guarded the **save** with `current_id != ws_id`. It did
not guard the **rmtree**.

```
echo "UNSAVED WORK" > preview/unsaved_edit.html
POST /api/workspaces/537b5b7d/activate     # already the current workspace
-> {"ok": true}                            # and the file was GONE
```

Switching to a *different* workspace was survivable — the outgoing one is saved
first, so switching back restored everything. I verified that too, and it is
why this bug has probably gone unnoticed: the common path self-heals. **This
path had no recovery. The only copy of the work was the one deleted.**

The save now runs whenever there is a current workspace, and re-activating the
current one is a filesystem no-op returning `already_active: true`. Tearing the
directory down to rebuild it identically only creates a window in which
`preview/` does not exist for the other twenty modules reading it.

> **Correction to my own first draft.** My initial comment claimed the UI
> "invites" this by leaving the active card clickable. It does not — the
> Workspaces pane renders no Switch button on the active card. The endpoint is
> still wrong: it is reachable via the API and via any second caller that
> activates by id without checking which workspace is current. An endpoint that
> destroys unsaved work for one class of caller is a bug regardless of what
> today's UI happens to render. I corrected the comment in the code.

### 2. Concurrent activation

`activate_workspace()` is a read-modify-write over a directory tree: *save →
wipe → repopulate*. Two overlapping calls interleave those phases.

| Run | Result |
|---|---|
| 3 concurrent activations × 3 trials | **LOST, LOST, LOST** |
| identical sequence, run sequentially | **survived every time** |

That contrast is what isolates concurrency as the cause rather than bug 1 —
worth doing, because the two produce identical symptoms and fixing only the
first would have looked like success.

The trigger is mundane: the **Switch button was not disabled during its
await**, so an impatient double-click issues exactly this pair of requests.

Fixed with a `threading.Lock` around activation and manual save. These are
sync (`def`) endpoints, so FastAPI runs them in a threadpool where a real lock
applies and the critical section is filesystem I/O rather than anything
awaitable. **Verified 5/5 with three concurrent activations.** The frontend
also disables the buttons while a switch is in flight.

---

## 3. Cross-module destruction of shared `preview/` artefacts

`preview/` is shared by **20 modules** (`grep "ROOT / 'preview'"`), and a
workspace switch `rmtree`'d all of it. Browser-agent screenshots, generated
images and branch data were collateral damage.

This is the **same cross-module bug first seen in Module 10**, where the image
gallery broke permanently after a workspace switch. Fixing it there addressed
the symptom in one module; this is the cause.

`SHARED_PREVIEW_DIRS` (`browser_screenshots`, `assets/images`, `branches`) are
stashed before the swap and restored after — **including on the failure path**,
since they must never be collateral damage of a copy error. A companion test
asserts project files still swap, so the preservation cannot quietly become a
leak between workspaces.

---

## 4. Control Tower: kill reported success and leaked a permanent flag

```
POST /api/control/runs/nonexistent_run/kill
-> {"ok": true, "run_id": "nonexistent_run", "status": "killed"}
```

Nothing was killed — Module 15's *"reporting success while doing nothing"*
pattern. An operator hitting the kill switch on a runaway agent got the same
green answer whether or not anything stopped, at the moment they most need the
truth.

The second-order bug is worse. `_kill_flags.add(run_id)` ran unconditionally,
but `finish_run()` — the only place that discards the flag — returns
immediately when the run is not active. So an unknown id left a **permanent
tombstone in an unbounded in-memory set**:

```
kill 'run_ghost'                      -> flag set, never cleared
create a real run with that id
record_step('run_ghost', ...)         -> False    # dead on arrival
```

Run ids are `run_<uuid4[:12]>`, so natural collision is remote — but a replayed
or user-supplied id is not, and the set grows without bound from typos and
stale UI retries regardless. The flag is now only set for a genuinely active
run, so it is always paired with the `finish_run()` that clears it.

---

## 5. Export crashed on non-ASCII workspace names — *found by a test*

```
GET /api/workspaces/<id>/export     (workspace named "日本語")
-> UnicodeEncodeError -> HTTP 500
```

`str.isalnum()` is `True` for CJK, so those characters passed the filename
filter and reached a `Content-Disposition` header, which Starlette encodes as
latin-1. **Any user with a non-Latin workspace name simply could not export
their project.**

I did not find this by reading the code. I wrote a test for the adjacent
empty-filename case, it returned 500 instead of the 200 I expected, and I
reproduced it live before believing it. Now restricted to ASCII alphanumerics
with an id-based fallback, so a name reducing to nothing yields
`workspace_<id>.zip` rather than `".zip"` — which browsers save as a hidden,
extensionless file.

---

## Phantom success

| Endpoint | Was | Now |
|---|---|---|
| `PATCH /workspaces/{id}` (unknown) | `200 {"ok": true}` | `404` |
| `GET /{id}/export` (unknown) | `200` + zip + **stray dir created** | `404` |
| `POST /{id}/save` (unknown) | `200 {"ok": false}` | `404` |
| `DELETE /{id}` (active) | `200 {"ok": false}` | `409` |
| `DELETE /collab/sessions/{id}` (unknown) | `200 {"ok": true}` | `404` |
| `POST /control/runs/{id}/kill` (unknown) | `200 "killed"` | `404` |

`UPDATE ... WHERE id=?` on a missing row affects zero rows and raises nothing,
so a rename that succeeded against nothing was indistinguishable from one that
worked. The export case was the most damaging: it fell through to
`_ws_preview_dir()`, which **creates** the directory — so exporting a typo'd id
left a stray directory *and* returned a valid-looking zip containing only a
placeholder. **A download that looks like a successful backup but contains none
of the user's work is worse than an error.** (A `workspaces/ghost_*/` directory
left behind by my own pre-fix test run is what confirmed this.)

---

## Path containment

`delete_workspace()` passed `ws_id` straight to `shutil.rmtree()` with no
validation. Proven at function level with the data dir redirected to `/tmp`:

```
delete_workspace('../precious')   ->  /tmp/wsdata/precious  DELETED
```

**Honest scope:** I could not reach this over HTTP — ASGI path normalisation
rejects or rewrites every encoding I tried (`..`, `%2e%2e`, `a/../..`,
`....//`). That is a property of the server in front of the code, not of the
code. An internal caller, a future CLI, or a different ASGI server is not
protected by it, so the guard belongs in the function. Ids are now validated
against `^[A-Za-z0-9_-]{1,64}$` and re-checked through
`safe_paths.safe_path()`.

---

## Tests

`tests/unit/test_76_workspaces_module_review.py` — **34 cases**.
**Proven to catch the bugs: with the three routers stashed, 28 of 34 fail.**

Two of my own defects surfaced while running them: I called `safe_path()` with
the wrong signature (positional rather than `base=`), and the non-ASCII export
fix was initially placed too late to matter. Both were caught by the tests
before commit, which is the argument for writing them against behaviour rather
than against the diff.

I also had to update `tests/unit/test_58_builder_workspace_deploy_boundaries.py`,
whose test **name** said `save_missing_workspace_is_rejected` while its
assertion pinned `HTTP 200` — codifying the very "200 on failure" pattern this
review has been removing platform-wide. A test asserting the bug is worse than
no test, because it makes the fix look like the regression.

Full suite: **3227 passed / 18 skipped / 0 failed** (was 3193).

---

## Recommended follow-ups

1. **`workspaces/` test residue — 130+ directories.** The live workspace list
   shows 25 workspaces named `ActivateWS_*`, `SysWS_*`, `Regress WS Activate`.
   The user's real projects are buried in test output. This is the known
   "`workspaces/` escapes the test-DB sandbox" gap, now visibly degrading the
   UI, and it is the top platform-wide follow-up outstanding.
2. **Collab sessions are in-memory only** (`_sessions: dict`) with no
   persistence — every session dies on restart, and `collab.py` contains zero
   `get_conn()` calls. The pane presents itself as collaborative editing but
   cannot survive a deploy.
3. **Control Tower runs are not durable either** (`_active_runs` is a dict), so
   a restart mid-run orphans it as permanently "running" in `agent_traces`.
4. **No quota or size limit on workspace storage.** Each switch copies the full
   tree twice; a large project makes activation slow and unbounded.
5. **`_save_preview_to_workspace()` copies the entire tree on every switch.**
   An rsync-style diff, or leaving files in place and swapping a symlink, would
   remove most of the window this module's locking now has to protect.

---

# Follow-up 1 — Test isolation: the filesystem half (`1b07a0f`)

The top platform-wide follow-up, outstanding since Module 15 and made
impossible to ignore by Module 18: the user's real workspace list was buried in
test output.

## Root cause

`50cc986` sandboxed the test **database** via `AGENTIC_TEST_DB`. It did nothing
for the **filesystem**. `get_data_dir()` returns the repo root unless
`AGENTIC_OS_DATA_DIR` is set, and ~20 routers derive write paths from it.
**Nothing ever set it.**

Half the problem was fixed and the other half went unnoticed for months,
because the symptom looks like clutter rather than like a bug.

Measured, not estimated:

| | Count |
|---|---|
| `workspaces/` directories on disk | **1158** |
| Files tracked by git | **3135** |
| Rows in the `workspaces` table | **618** |
| Genuine user projects among them | **1** |

The other 617 were `UnitWS_*`, `ActivateWS_*`, `SysWS_*`, `Regress WS
Activate` — and injection payloads. Workspaces literally named `' OR '1'='1';
DROP TABLE agents; --` and `<script>alert(document.cookie)</script>` were
rendering in the user's UI.

## Why the sandbox has an unusual shape

An empty temp dir would not work: the app legitimately **reads** repo content
from the same root — `frontend/js/*.js`, `backend/`, `requirements.txt`,
`templates/`. That is presumably why this was never done.

So the sandbox **symlinks read-only repo paths** back to the real thing and
provides **real empty directories** for everything written to. Reads resolve to
live files; writes land in the temp tree and are discarded.

`templates/` and `docs/` are **copied**, not symlinked. `safe_path()` resolves
symlinks *before* its containment check — correctly, since that is exactly how
a symlink is used to escape a sandbox — so a symlinked `templates/` resolves
outside the root, fails `relative_to()`, and `safe_path()` returns `None`.
`github.py`'s allowlist started rejecting `templates` and `docs` as invalid.

**That was the sandbox being wrong, not the security control.** Worth stating
plainly: the instinct when a security check starts failing is to loosen it. The
check was right.

## The live-server half

`_assert_server_db_is_sandboxed()` checked only the database, so a
correctly-DB-sandboxed server still wrote every workspace, preview file and
export into the repo. `/api/health` now reports `data_dir` and
`data_dir_is_test_sandbox`, and the guard in all five live conftests asserts on
both halves.

## A test that depended on the leak

`test_flow_07`'s `test_02_terminal_runs_a_python_script` imported `PREVIEW_DIR`
from `backend.routers.terminal` **inside the test process** to place a script
for the **server** to execute. Two processes, two different resolutions of the
same constant:

```
test process : /home/user/repo/preview
server       : /tmp/agentic-test-data/preview
```

It only ever passed because both were writing into the real repo — **the test
depended on the very leak being fixed.** It now asks the server where its data
dir is via `/api/health`.

This is the argument for verifying a sandbox by *running the suite* rather than
by reading the diff. I initially dismissed this failure twice as "stale
server", and it was real both times.

## Clearing the backlog

`scripts/clean_test_residue.py`. Deletion is **opt-in** (`--apply`; default is
a dry run), anything not confidently identified as test output is **kept**, the
active workspace is never deleted, and containment is verified before every
`rmtree` rather than trusted from the DB. The asymmetry is deliberate: leaving
a stray test workspace is cosmetic; deleting a real project is not.

Applied: **617 DB rows and 1156 directories** removed, **2689 files
untracked**. `.gitignore` gains `workspaces/*/preview/` as a last line of
defence.

## Verification

The measurement that matters, before and after a **full suite run**:

| | Before | After |
|---|---|---|
| `workspaces` DB rows | 2 | **2** |
| `workspaces/` directories | 8 | **8** |

The UI now lists exactly one workspace — *My Project*, 8 files intact,
switching and exporting verified working.

`tests/unit/test_77_test_isolation_guard.py` — 8 cases asserting the sandbox is
**in effect**, not merely configured. That distinction is the whole lesson of
`50cc986`, where the docstring promised isolation while nothing read the
variable. Disabling the env var fails all 8.

Full suite: **3235 passed / 18 skipped / 0 failed** (was 3227).

## Status

Follow-up 1 of Module 18 is closed, and with it the longest-standing
platform-wide gap in this review. Follow-ups 2–5 (collab/Control Tower
durability, workspace quotas, copy-on-switch cost) remain open.
