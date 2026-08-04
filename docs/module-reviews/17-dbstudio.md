# Module 17 — Database Studio

**Commit:** `0a1f53c` · **Suite:** 3143 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/database.py` (514 lines, 13 endpoints) ·
`frontend/js/17-database-studio.js` (412 lines)

DB Studio runs SQL **directly against the platform's own database** — the one
holding secrets, `auth_users`, chat history and every module's state. Its
`allow_write` flag is therefore a security control, not a convenience.

---

## 🔴 The write guard could be walked around

Detection matched a **keyword prefix**. Anything putting another token first
slipped through as a "read", executed anyway, and was reported back as a
`select`. Verified live against a real table with `allow_write=false`:

```
WITH t AS (SELECT 1) DELETE FROM dbstudio_victim
  → {"ok": true, "type": "select", "count": 0}     …and the row was GONE

ATTACH DATABASE '/tmp/evil_attached.db' AS evil
  → reported as a select; the file was created on disk

PRAGMA writable_schema=1
  → reported as a select; sqlite_master protection disabled
```

The `"type": "select"` is what makes this nasty — the tool tells you nothing
happened *while deleting your rows*.

### An earlier fix had already been here

The code carried a detailed comment about a previous bypass
(`/* x */ DROP TABLE`), correctly fixed by stripping *leading* comments. It
worked, for that one input.

**Patching a single instance of a wrong approach leaves the approach wrong.** A
prefix check cannot express "does this statement modify anything" — SQL is not
prefix-structured, and there will always be another token you can put first.

### The fix

`classify_sql()` strips comments from *anywhere* (respecting string literals, so
`'-- not a comment'` survives) and scans for write keywords as whole **words**
across the statement.

Deliberately asymmetric: it may classify a read as a write — costing the user an
`allow_write` flag — but will not classify a write as a read, which costs them
their data.

`ATTACH`/`DETACH` and the schema/durability PRAGMAs are refused **outright**,
with or without `allow_write`. That flag is consent to modify *data*, not to
create files outside the database or corrupt `sqlite_master`. Verified: `ATTACH`
with `allow_write=true` is still 403 and creates no file.

| Payload | Before | After |
|---|---|---|
| `WITH … DELETE` | ran, reported "select" | 403 |
| `(DELETE FROM x)` | syntax error (accidentally safe) | 403 |
| `/* c */ DROP` | 403 *(previously fixed)* | 403 |
| `ATTACH …` | ran, created a file | 403 even with `allow_write` |
| `PRAGMA writable_schema=1` | ran | 403 |
| `SELECT … LIKE '%delete%'` | ran | ran ✓ |
| `INSERT` + `allow_write` | ran | ran ✓ |

---

## 🟡 Status codes

Empty SQL, blocked writes, forbidden statements, syntax errors and invalid table
names all returned HTTP 200. Now 400/403, so a refusal is distinguishable from a
successful empty result.

---

## Verified working (no change needed)

- **Table names *are* validated** before interpolation — `UNION` and
  quote-escape payloads through the `{table}` path param are correctly rejected.
  I expected to find injection here and did not.
- The search parameter is properly parameterised (`LIKE ?`).
- `_connect()` already matches `memory_db.get_conn()`'s WAL + `busy_timeout`,
  and honours the `AGENTIC_TEST_DB` sandbox — both from earlier fixes.
- Secrets are stored encrypted (`value_enc`), so a `SELECT` returns ciphertext
  rather than plaintext keys.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Secrets Vault** | Its table is readable here; encrypted at rest, but see follow-ups |
| **Auth** | `auth_users` / `auth_sessions` are queryable |
| **Every module** | They all share `agentic.db`; a bypassed `DROP` hits all of them |
| **Terminal** | Same "filter guarding a powerful primitive" shape — both now scan rather than prefix-match |

---

## Tests

`tests/unit/test_73_dbstudio_module_review.py` — **51 contracts**, including
end-to-end checks that a blocked statement leaves the row count *unchanged*
rather than merely returning an error.

**Proven to catch the bugs: 42 of 51 fail against the pre-fix code.**

Two self-corrections worth recording:

1. One test asserted a table named `deleted_rows` should trip the keyword scan.
   It doesn't, and shouldn't — word-boundary matching sees `DELETED`, not
   `DELETE`. **Asserting wrong behaviour is worse than not asserting**, so I
   rewrote it to pin what the classifier actually guarantees.
2. `test_forbidden_beats_allow_write` passed alone and failed in the full suite:
   the stashed pre-fix run had left `/tmp/_dbs_never.db` behind. The residue was
   evidence the bug was real, but the test now clears its target first.

---

## Recommended follow-ups

1. **No audit trail for destructive SQL.** `allow_write=true` can `DROP` any
   table in the platform and nothing records it. The platform has `audit_log()`
   and DB Studio is the most obvious caller it doesn't have.
2. **The secrets table should be excluded from the browser.** Values are
   encrypted, but the vault key sits in `memory/.vault_key` — anything that can
   read both has the plaintext. Hiding `secrets`/`auth_users` from the table
   list (with an explicit override) would make the coupling deliberate.
3. **No transaction boundary or undo.** Each statement auto-commits, so a
   mistyped `DELETE` is immediately permanent. A "wrap in a transaction and show
   me the row count before I commit" mode would match how the tool is used.
4. **`/sqlite/ai-schema` generates DDL from a prompt** and the response feeds
   straight into the query box — LLM-authored SQL against the live database is
   worth a confirmation step of its own, like the push dry-run.

---

# Follow-up 1 — Audit trail for destructive SQL (`486239d`)

Recommendation 1 above, implemented.

## The gap, restated precisely

Module 17 hardened **what** Database Studio would execute. It never touched
**whether it was observable**. Those are separate concerns and only the first
had been done.

Reproduced live against a running server before writing any code:

```
POST /api/db/sqlite/query {"sql":"DROP TABLE audit_victim","allow_write":true}
  -> {"ok": true, "rows_affected": -1, "type": "write"}

GET  /api/audit-log?limit=20
  -> not one row referencing the statement, the table, or Database Studio
```

The most destructive operation the platform exposes was also its least
observable one. Every other privileged subsystem already appends hash-chained
receipts — `mcp_tool_call`, `connector_exec`, `goal_created`, A2A messages —
while the SQL editor, both row endpoints and the table-create endpoint appended
nothing at all.

The information needed for a receipt was already computed: `classify_sql()`
knows a statement is a write. That knowledge was discarded immediately after
the `allow_write` check instead of being carried into a record.

## What was built

`audit_sql()` in `backend/routers/database.py`, appending to `audit_log_chain`
through `routers/audit_log.append_entry()`, wired into all four mutating paths.

| Endpoint | Action type |
|---|---|
| `POST /sqlite/query` (write) | `db_sql_write`, preceded by `db_sql_attempt` when critical |
| `POST /sqlite/query` (refused) | `db_sql_refused` |
| `POST /sqlite/table/{t}/insert` | `db_row_insert` |
| `DELETE /sqlite/table/{t}/row` | `db_row_delete` |
| `POST /sqlite/table/create` | `db_schema_change` / `db_schema_refused` |

Five design decisions worth stating, because each rules out a simpler version
that would have looked equivalent:

1. **Two entries for critical statements, not one.** The chain is append-only —
   an "in flight" row can never be updated with its outcome. Writing a
   `pending` entry *before* execution means a statement that hangs, kills the
   process or corrupts the file still leaves a trace. That is exactly the case
   where the completion entry never lands, and exactly the case you most want
   a record of.
2. **Refusals are recorded.** A rejected `ATTACH` is a security signal. A ledger
   that holds only successes cannot show that someone tried.
3. **Failures are recorded**, not just successes.
4. **Risk by blast radius, not keyword presence.** `DROP`/`TRUNCATE` and
   *unqualified* `DELETE`/`UPDATE` are `critical`; qualified destructive
   statements `high`; `INSERT`/`CREATE` `medium`. The checks are ordered rather
   than iterating the keyword frozenset — set iteration order is not stable, so
   `DROP TABLE a; ALTER TABLE b ...` would have graded `high` on one run and
   `critical` on the next. There is a test that runs the classifier 50 times.
5. **Reads are deliberately not audited.** Auditing every `SELECT` would bury
   the destructive events in noise and make the trail useless in practice.

`audit_sql()` can never raise into the request path — a ledger outage logs at
ERROR but must not swallow the user's query result. There is a test for that.

## A second bug, found while wiring this up

`POST /api/db/sqlite/table/create` executed raw SQL with **no `classify_sql()`
call at all**. The AI Schema Designer posts LLM-authored DDL straight to it, so
the `ATTACH` refusal that Module 17 added to the SQL editor was sidestepped
simply by choosing the other endpoint. Verified live: an `ATTACH` posted to
`/table/create` created a file on disk. It now runs the same guard and returns
403 with a ledger entry.

This is the same shape as the Module 12 terminal finding: a guard applied to
the obvious entrance while a second door stood open beside it. **When a check
is added, enumerate every endpoint that reaches the primitive** — not just the
one where the bug was found.

## Frontend

* New **Audit Trail** tab: the ledger filtered to `db_*` actions, risk and
  outcome colour-coded, with a live chain-integrity badge from
  `/api/audit-log/verify`.
* A confirmation dialog before running a statement that looks destructive, and
  a "Recorded in the audit trail" note on the write result.

`dbSqlLooksDestructive()` mirrors the server rule, and the comment above it says
plainly that it is a UX affordance and **not** a security control. The server
classifies and records independently and trusts nothing the client sends. This
repeats the Module 16 lesson: *the model may suggest; the server decides* — the
same applies to the browser.

## Verification

Live server, before and after:

| Statement | Ledger |
|---|---|
| `DROP TABLE t` | `db_sql_attempt/critical/pending` then `db_sql_write/critical/success` |
| `DELETE FROM t` | `critical` |
| `DELETE FROM t WHERE id=1` | `high` |
| `INSERT INTO t ...` | `medium` |
| `DROP` without `allow_write` | `db_sql_refused/blocked` |
| `ATTACH ...` | `db_sql_refused/high` |
| `ATTACH` via `/table/create` | `db_schema_refused/high`, no file created |

`/api/audit-log/verify` → 884 entries, `broken_at: null`. Database Studio's
entries do not break the hash chain.

## Tests

`tests/unit/test_74_dbstudio_audit_trail.py` — **20 cases**. They assert on the
**contents of the ledger** after each operation, never on the presence of a call
in the source, so they cannot be satisfied by a comment. (The `_executable()`
docstring/comment-stripping helper is used for the one structural guard, per the
lesson from Modules 10, 12, 14, 15 and 16.)

**Proven to catch the bug: with `backend/routers/database.py` stashed, 17 of 20
fail. With the fix, 20/20 pass.**

Full suite: **3163 passed / 17 skipped / 0 failed** (was 3143).

## Remaining Database Studio follow-ups

Recommendations 2–4 are still open:

2. The `secrets` table is still browsable.
3. Still no transaction boundary or undo — every statement auto-commits. The
   audit trail now tells you *what* was destroyed, which makes the absence of an
   undo more conspicuous, not less.
4. `/sqlite/ai-schema` DDL now passes the statement guard and is recorded when
   executed, but there is still no explicit confirmation step comparing the
   LLM's DDL against the current schema before it runs.
