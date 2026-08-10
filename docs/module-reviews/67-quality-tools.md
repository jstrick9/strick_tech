# 67 — Module review 6: quality tools (`ambient`, `bugbot`, `gitai`, `health`)

All four render from `frontend/js/07-quality-tools.js` (780 lines, 16
endpoints) and were reviewed as one unit. All score **20**.

---

## The defect: a confident grade for a codebase never analysed

Two of the five health dimensions substituted an invented number when there was
nothing to measure:

```python
if total_syms > 0:  complexity_score = ...real calculation...
else:               complexity_score = 70      # invented

if total_fns  > 0:  doc_pct = int(with_docs / total_fns * 100)
else:               doc_pct = 50               # invented
```

Those placeholders were weighted into the overall score and rendered as a
letter grade. Measured live with an empty code index:

```
overall 87, grade B
complexity 70   "0 total symbols"
docs       50   "0/0 functions have docstrings (50%)"
```

**`0/0 ... (50%)` is the tell** — a percentage printed beside the division that
could not have produced it.

Recurring pattern **#10** (fabricated data on an empty path) and **#3** (a
module reporting success while doing nothing). Worse here than on the
Dashboard, because a **health grade is the one number a user acts on**: *"B,
good enough"* is a decision, and it was never measured.

---

## The fix

An unmeasurable dimension scores `None` and is **excluded** from the weighted
average; the remaining weights are **renormalised**.

Renormalising matters as much as excluding. With complexity and docs unknown
the remaining weight is 0.65 — multiplying by that would cap the score at 65
and grade a healthy project **D** for not being indexed. Same wrong answer,
opposite direction.

If nothing at all is measurable, `overall` and `grade` are `None`.

---

## The overstatement the fix created — and its fix

Removing the placeholders left `100 / A` rendered from **65%** of the
weighting. Honest arithmetic, still misleading: two fifths of the assessment
never ran.

The pane now states its coverage, with the route to complete it:

> Based on **65%** of the assessment — complexity and docs not measured yet.
> **[Run Code Index]**

A null overall also rendered as `0 / ?` via `||0`, reading as a *failing* grade
rather than "not analysed". Not-measured and measured-and-bad must not look
alike — the same distinction made for the Dashboard's savings figure.

`_health_tip()` also had to change: `min(scores, key=...)` raised
`TypeError` once a dimension scored `None`, turning an honest "not measured"
into a **500**. It now picks from measured dimensions only — suggesting work on
a dimension never assessed would be wrong even if it did not crash.

---

## Verified as already correct

| Endpoint | Result |
|---|---|
| `/api/ambient/tasks`, `/api/bugbot/stats`, `/api/gitai/status` | 200, real empty states |
| `/api/gitai/changelog`, `/api/gitai/security/scan` | 405 on GET — POST-only by design |
| `/api/gitai/deps/audit` | 503 with the honest no-provider message |

All four panes render with **zero page errors**.

---

## Cross-module impact

- `ambient.py` also writes `health_snapshots`; the snapshot row keeps
  `overall_score`, which is now nullable — worth noting for any trend chart
  built on it later.
- The coverage banner links to `codeindex`, which populates `code_symbols`.
  That pane has not been reviewed yet, and the health grade depends on it.

## Verification

| Check | Result |
|---|---|
| Empty index | `87 / B` → `unmeasured: [complexity, docs]`, coverage stated |
| `docs` detail | `0/0 ... (50%)` → "Not measured — no functions indexed yet" |
| Tip with `None` scores | TypeError → returns advice for a measured dimension |
| Revert all fixes | **15 of 15** tests fail |
| Full suite | 3,483 unit (2 skipped) + 655 (10 skipped), 0 failures |
