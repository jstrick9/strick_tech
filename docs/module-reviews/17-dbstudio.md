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
