"""Sensitive-data policy for Database Studio.

WHY THIS EXISTS
───────────────
Module 17's follow-up list said "the secrets table should be excluded from the
browser". Verified live, the actual exposure was considerably worse than that
one table:

    POST /api/db/sqlite/query
      {"sql": "SELECT agent_id, signing_key FROM agent_identities LIMIT 2"}
    -> {"ok": true, "rows": [{"agent_id": "orchestrator",
                              "signing_key": "-----BEGIN PRIVATE KEY-----\\n..."}]}

`agent_identities.signing_key` holds the PRIVATE KEYS used by
`audit_log._issue_receipt()` to sign audit receipts. Reading them lets an
attacker forge receipts for the very ledger added in the previous commit
(486239d) — the tamper-evidence control and the material that defeats it were
sitting in the same browsable table.

That this is a real control and not a theoretical one is settled by the code
itself: `agent_identity.get_agent_identity()` sets
`d['signing_key'] = '[REDACTED]'` with the comment "without signing_key for
security". The application already decided this field must never be returned
over HTTP. Database Studio was a second door into the same row that never got
the memo.

The same shape applies to `auth_users.password_hash` / `api_key` (api_key is a
live credential accepted by `auth.require_api_key()`), `auth_sessions.token`,
`webhooks.secret`, connector and MCP `auth_config` blobs, and the `secrets`
table originally flagged.

DESIGN
──────
Two mechanisms, because one is not enough:

1. **Refuse statements that NAME a sensitive column or restricted table.**
   Output-side redaction alone is trivially defeated:

       SELECT signing_key AS x FROM agent_identities
       SELECT substr(signing_key, 1, 40) FROM agent_identities
       SELECT group_concat(signing_key) FROM agent_identities

   None of those produce a result column called `signing_key`. Any filter that
   inspects only result-column names loses to a four-character alias. This is
   the same lesson as the prefix-matching bugs found in Modules 12 and 17: the
   check has to match the structure of the thing being checked.

2. **Redact by column name on the way out.** `SELECT * FROM agent_identities`
   never mentions the column, so rule 1 cannot see it, but the result set is
   labelled `signing_key` and gets masked.

Neither is sufficient alone; together they cover both directions.

Redaction is a fixed placeholder, never a truncation. Returning the first eight
characters of a key or hash is a meaningful head start on recovering it and
tells the operator nothing they actually needed.

The override is deliberately awkward: a process-level environment variable, not
a request parameter, so a stray checkbox in the UI (or an agent posting JSON)
can never turn it off. Every use is recorded in the audit chain at critical
risk.
"""

from __future__ import annotations

import os
import re

REDACTED = '[REDACTED]'

# Tables whose every row is credential material. Browsing them has no
# legitimate debugging purpose that redaction wouldn't already serve.
RESTRICTED_TABLES: frozenset[str] = frozenset({
    'secrets',
    'auth_users',
    'auth_sessions',
})

# Column-level secrets in tables that are otherwise useful to browse.
# Keyed by lowercase table name -> lowercase column names.
SENSITIVE_COLUMNS: dict[str, frozenset[str]] = {
    'agent_identities': frozenset({'signing_key'}),
    'agent_jit_tokens': frozenset({'token_id'}),
    'webhooks': frozenset({'secret'}),
    'connector_registry': frozenset({'credentials', 'auth_config'}),
    'mcp_servers': frozenset({'auth_config'}),
    'a2a_agents': frozenset({'auth_config'}),
    'audit_receipts': frozenset({'signature'}),
}

# Column names that are secret wherever they appear. New tables get protection
# by default instead of having to be remembered — the failure mode of an
# explicit allow-list is that the next table to store a token is missed, and
# nobody notices until it leaks.
SENSITIVE_COLUMN_NAMES: frozenset[str] = frozenset({
    'signing_key',
    'private_key',
    'secret_key',
    'password',
    'password_hash',
    'api_key',
    'apikey',
    'access_token',
    'refresh_token',
    'value_enc',
    'client_secret',
    'session_token',
})


def sensitive_override_enabled() -> bool:
    """True when the operator has explicitly opted in at process level.

    Intentionally NOT a request parameter. A per-request flag can be flipped by
    anything that can reach the endpoint, including an agent composing JSON,
    which makes it a switch the attacker controls rather than the operator.
    """
    return os.getenv('AGENTIC_DB_ALLOW_SENSITIVE', '').strip().lower() in ('1', 'true', 'yes')


def is_sensitive_column(table: str, column: str) -> bool:
    """True if `column` should be masked, considering both table-specific and global rules."""
    col = (column or '').strip().strip('"`[]').lower()
    tbl = (table or '').strip().strip('"`[]').lower()
    if col in SENSITIVE_COLUMN_NAMES:
        return True
    return col in SENSITIVE_COLUMNS.get(tbl, frozenset())


def is_restricted_table(table: str) -> bool:
    return (table or '').strip().strip('"`[]').lower() in RESTRICTED_TABLES


def _all_sensitive_names() -> set[str]:
    names = set(SENSITIVE_COLUMN_NAMES)
    for cols in SENSITIVE_COLUMNS.values():
        names |= set(cols)
    return names


def check_statement(sql: str) -> str:
    """Return a refusal reason if `sql` names a restricted table or secret column.

    Word-boundary scan of the whole statement, deliberately conservative in the
    same direction as classify_sql(): it may refuse a query that merely mentions
    the word in a harmless position, which the operator can rephrase, but it
    will not let an aliased or wrapped secret through.
    """
    if sensitive_override_enabled():
        return ''

    # Strings are masked so a literal value can't trip the scan, and comments
    # are already removed by the caller's strip_sql_comments().
    upper = re.sub(r"'[^']*'", "''", (sql or '').upper())

    for tbl in sorted(RESTRICTED_TABLES):
        if re.search(rf'\b{tbl.upper()}\b', upper):
            return (
                f'Table "{tbl}" holds credential material and is not readable through '
                f'Database Studio. Set AGENTIC_DB_ALLOW_SENSITIVE=1 on the server to override.'
            )

    for col in sorted(_all_sensitive_names()):
        if re.search(rf'\b{col.upper()}\b', upper):
            return (
                f'Column "{col}" holds credential material and cannot be selected, aliased, '
                f'or passed through a function. Set AGENTIC_DB_ALLOW_SENSITIVE=1 on the server '
                f'to override.'
            )
    return ''


def redact_rows(rows: list[dict], columns: list[str], table: str = '') -> tuple[list[dict], list[str]]:
    """Mask sensitive values in result rows. Returns (rows, list_of_redacted_columns).

    Catches `SELECT *`, which never names the column and so cannot be caught by
    check_statement().
    """
    if sensitive_override_enabled():
        return rows, []

    hits = [c for c in columns if is_sensitive_column(table, c)]
    if not hits:
        return rows, []

    masked = []
    for row in rows:
        r = dict(row)
        for c in hits:
            if r.get(c) not in (None, ''):
                r[c] = REDACTED
        masked.append(r)
    return masked, hits
