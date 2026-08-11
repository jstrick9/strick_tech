# 86 — Database Studio (`dbstudio`)

**Destination:** `dbstudio` (single-pane)
**Frontend:** `frontend/js/17-database-studio.js`
**Backend:** `backend/routers/database.py`, `backend/services/db_policy.py`
**Tests:** `tests/unit/test_161_module25_dbstudio.py` (31)
**Status:** reviewed, fixed, verified live

Destination 13 of 20.

> Renumbered from 85/160 on landing: a parallel review session pushed
> `85-workspaces-control-tower.md` and `test_160_module24_workspaces_control.py`
> first. Both sessions independently found and identically fixed the
> `avg_score is None` assertion in `test_sys_10` — theirs is kept (it also
> covers `suite_pass`) with my None-safe `total` guard merged in.

---

## The policy layer is good. It was only half-wired.

`backend/services/db_policy.py` is one of the better pieces of code in this
repository. Its docstring explains why output-side redaction alone is not enough
(`SELECT signing_key AS x` defeats any filter that inspects result-column names)
and it implements **both** directions: refuse statements that *name* a secret,
and redact by column on the way out. Probed directly, it holds up:

```
SELECT signing_key FROM agent_identities             -> refused
SELECT signing_key AS blob FROM agent_identities     -> refused
SELECT substr(signing_key,1,8) FROM agent_identities -> refused
SELECT * FROM agent_identities                       -> signing_key [REDACTED]
CREATE TABLE copy AS SELECT * FROM agent_identities  -> the copy is redacted too
```

I spent a while trying to get a private key out of it and could not. **The
defect is not the policy — it is that the policy was wired into the two READ
paths and into neither WRITE path.**

Four defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. SQL injection via `pk_column` — a full table wipe

The delete endpoint validated the *table* name against an identifier pattern,
then interpolated the caller's *column* name into the same statement unchecked:

```python
cur = con.execute(f'DELETE FROM "{table}" WHERE "{pk}"=?', (value,))
```

A `"` in `pk_column` closes the quoted identifier and the remainder becomes SQL.
Verified live against a planted 3-row table:

```
{"pk_column": "a\" OR 1=1 OR \"a", "pk_value": "nope"}
  -> DELETE FROM "t160_victim" WHERE "a" OR 1=1 OR "a"=?
  -> {"ok": true, "deleted": 3}
```

**Three rows destroyed by a `pk_value` that matched nothing.** The parameterised
`?` sitting right beside it gave the appearance of safety — this is the classic
form of the bug, where the placeholder protects the value and the injection is
in the identifier.

### 2. Database Studio could not *read* the secrets table but could *delete* from it

`db_policy` was consulted at `/sqlite/query` and `/sqlite/table/{table}` and
nowhere else. Verified live: a planted row in `secrets` was removed by

```
DELETE /api/db/sqlite/table/secrets/row  -> {"ok": true, "deleted": 1}
```

while `SELECT * FROM secrets` on the very same table is refused with *"holds
credential material and is not readable through Database Studio."*

Destroying credential material is **strictly worse** than reading it: reading a
vault entry leaks one secret; deleting it locks every agent out of that provider
and the row is gone. Guarding the read and not the write inverts the severity
ordering the policy was written to enforce.

### 3. The insert endpoint had the same gap

No policy check at all, so rows could be written into `secrets`, `auth_users`
and `auth_sessions`.

### 4. Sensitive *columns* of browsable tables were writable

`agent_identities` is deliberately browsable with `signing_key` redacted — but
nothing stopped a write to that column. `signing_key` is the key that signs
audit receipts, so overwriting it forges the ledger just as effectively as
reading it does. `_policy_write_column_refusal()` now covers this, and a test
pins that a *non*-sensitive column of the same table is still writable, so the
column rule cannot quietly become a table rule.

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**9 of 9 real breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | `pk_column` injection | 8 |
| 1b | identifier regex allows anything | 8 |
| 2 | delete ignores the policy | 4 |
| 3 | insert ignores the policy | 4 |
| 4 | sensitive column write allowed | 1 |
| 4b | restricted-table write refusal disabled | 7 |
| 5 | read: secret column name allowed | 3 |
| 5b | read: output redaction disabled | 2 |
| 5c | read: restricted table allowed | 1 |

The read policy is now pinned in all three of its modes (name / alias /
function-wrapped, plus `SELECT *` redaction and derived tables) so a future edit
cannot weaken the part that already worked.

### Two hollow tests, found by revert-proofing

**The redaction tests asserted nothing.** Disabling output redaction failed
zero tests. Cause: `/api/db/sqlite/query` is a POST requiring CSRF, my probes
sent none, so the endpoint answered `{"ok": false, "error": "CSRF token
required."}` — and the assertions were wrapped in `if body.get('rows'):`, which
was never true. A guard like that turns a security test into decoration.

Fixed by adding a `_csrf()` helper and asserting `body['ok'] is True` and
`body['rows']` **before** the substantive assertion, so the test fails loudly if
it ever stops reaching the endpoint again. Compounding it, the unit harness
sandboxes the database, so even with CSRF there were no `agent_identities` rows
to redact — a `seeded_identity` fixture now plants one rather than depending on
ambient data.

**A "fix" that fixed nothing.** Removing the insert column-name validation
failed zero tests either. Traced rather than assumed: the placeholder count is
always `len(row)`, so an injected extra column produces
`"1 values for 2 columns"` and the statement never executes. Unlike `pk_column`,
this was **not** exploitable. The check is kept — the delete path shows exactly
what unvalidated identifier interpolation costs, and a future edit to the VALUES
construction would make it live — but the code comment and the test now say
plainly that it is defensive, so nobody goes hunting for an exploit that is not
there.

### Two pre-existing tests updated in place

Both were consequences of *earlier* modules in this review, surfaced here
because a live AI provider became reachable and 8 previously-skipped tests
started running:

- `test_uat_08 :: test_user_can_get_ai_risk_assessment` — module 21 made
  `assess-confidence` return **503** when the judge produces nothing usable, but
  omitted `code: 'llm_unavailable'`. `tests/uat/conftest.py`'s
  `skip_if_no_provider()` keys off exactly that field, so a test that should
  skip in a provider-less environment failed instead. **This was my omission**,
  fixed in `hitl.py` rather than in the test — a client needs that field for the
  same reason the harness does: an unreachable provider and a judge that
  answered uselessly both arrive as 503, and only `code` separates them.
- `test_sys_10 :: test_eval_run_produces_valid_scores` — asserted
  `0 <= done.get("avg_score", 0) <= 1.0`. Module 16 made `avg_score` **`None`**
  when nothing could be scored, and `0 <= None` raises `TypeError`, so the check
  crashed rather than failing. Updated to accept an explicit null and to range-
  check only a real number. Defaulting to `0` would have re-asserted the exact
  behaviour that fix removed. (My first diagnosis blamed `total`; the live probe
  showed `total: 2, avg_score: None` — corrected before changing anything.)

## Live verification

```
pk_column injection      -> 400 "Invalid column name", 3 rows intact
DELETE FROM secrets      -> 403 forbidden, planted row still present
INSERT INTO auth_users   -> 403 forbidden
INSERT signing_key       -> 403 "Column(s) signing_key hold credential material"
ordinary insert + delete -> 200 / 200, row count correct
CREATE TABLE secrets     -> already refused (existing _policy_refusal)
```

## Cross-community impact

- **`_policy_write_refusal()` / `_policy_write_column_refusal()`** are new and
  local to `database.py`; `db_policy.py` itself is **unchanged**.
- **`DELETE /api/db/sqlite/table/{table}/row`** and
  **`POST .../insert`** can now return **400** (bad identifier) and **403**
  (policy). Any tooling that wrote to `secrets`, `auth_users` or
  `auth_sessions` through Database Studio will now be refused — that was the
  bug, but it is a behaviour change.
- The `AGENTIC_DB_ALLOW_SENSITIVE=1` process-level override releases the write
  guards exactly as it already released the read guards, so the escape hatch is
  unchanged and consistent.
- `create_table` needed no change: it already runs `_policy_refusal(sql)`. I
  added a guard there, proved it redundant, and removed it rather than leave
  dead code.
- Supabase endpoints were reviewed and left alone: they target a **remote,
  user-owned** database, where this policy does not apply. Worth a later pass —
  they carry no audit logging while the SQLite paths have 18 audit points.

## Suite

`4124 unit (2 skipped)` + `663 regression/system/uat (2 skipped)` =
**4,787 passing, 0 failures**. Linters clean.

Note the skip count: it dropped from 10 to 2 because an AI provider became
reachable in this environment, so 8 tests that had been skipping now execute.
Two of them failed on first contact — both fixed above. *A skip is not a pass*,
and this is the run that proved it.
