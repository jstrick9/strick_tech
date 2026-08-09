# 65 — Module review 4: Dashboard (`dashboard`)

**Risk rank 4 of 68** (score 34). The pane most users land on first.

---

## The defect: a fabricated headline number

```python
saved_vs_saas = round(max(0.0, 350.0 - total_cost * 100), 2)
```

`350.0` is a hardcoded constant with **no input from the account**. Verified in
a real browser on a brand-new install, where every other KPI reads zero:

```
💰 TOTAL COST   $0.0000   Saved $350 vs SaaS
🔤 TOKENS USED  0         0 messages
📋 TASKS        0         0% complete
```

It is a *measurement* presented among measurements — and the largest figure on
the pane. Every other number there is derived from the user's own data, so this
one reads as real too. **A user who has done nothing is told the product has
already saved them $350.**

Recurring pattern **#10**: fabricated data on an empty path, the same class as
the Kanban board rendering six invented tasks during an outage.

### The arithmetic was also backwards

`total_cost * 100` asserts a SaaS product costs exactly 100× whatever the local
run cost — so **heavier use drives the "savings" down**. Spend $3.50 and the
dashboard tells you that you saved nothing at all.

---

## The fix

Derive the comparison from real usage, state the assumption instead of hiding
it, and return **`None`** when there is nothing to compare.

`None`, not `0` — "we have not measured this" and "we measured it and it is
zero" are different claims. The UI renders the first as **"No usage yet"**
rather than "Saved $0 vs SaaS", which would still assert a comparison that was
never made.

The response now carries `saved_vs_saas_basis`, so the pane shows its own
working:

> Saved **$0.19** vs SaaS *(est. $0.02/msg × 10)*

A figure the user can check is a different thing from a figure they must trust.

Verified end to end: seeded 10 messages at $0.001 each → **$0.19**, exactly
`10 × 0.02 − 0.01`. Cleared the seed → back to "No usage yet".

---

## Verified as already correct

| Check | Result |
|---|---|
| `days=0`, `days=-5` | clamped to 1 |
| `days=99999` | clamped to 365 |
| `days=abc` | 422 |
| Load failure | `humanError()` + `httpError()`, "your data is safe", Retry button |
| Other panels when empty | real empty states ("No cost data yet", "Run a swarm to see winners here") |

The module is otherwise well built — 159 lines, proper error copy, auto-refresh
that checks visibility first.

---

## Cross-module impact

- `analytics.py` also backs the **FinOps** pane and `/api/analytics/export`.
  The savings field is dashboard-only, but the shared `_clamp_days` helper and
  cost aggregation are not — FinOps should be checked when it comes up the
  ranking.
- **The risk instrument mis-attributed this module** to `01-app-core.js`; the
  renderer actually lives in `36-dashboard.js` (159 lines, not 1,945). The
  file-attribution heuristic finds the first file defining `window.renderX`,
  and `01-app-core.js` mentions it in a comment. Worth fixing before it
  misdirects a later module.

## Verification

| Check | Result |
|---|---|
| Empty account | `saved_vs_saas_usd: null` → UI shows "No usage yet" |
| 10 messages @ $0.001 | `$0.19`, matching `10 × 0.02 − 0.01` |
| Savings vs usage | now **rises** with usage (was falling) |
| Negative savings | clamped to 0 |
| Revert both fixes | **10 of 13** tests fail |
| Full suite | 3,456 unit (2 skipped) + 655 (10 skipped), 0 failures |
