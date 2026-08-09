# 63 — Module review 2: Docs & Help (`docs`)

**Risk rank 2 of 68** (score 35): 1,801 lines, 15 endpoints.

---

## Verified as already correct

Most of this module is genuinely good, and that is worth stating rather than
leaving as silence:

| Check | Result |
|---|---|
| All 7 endpoints on an empty account | 200 |
| Panes with a feature doc | **67 of 68** |
| Contextual help resolves to the right doc | **68 of 68**, probed individually |
| Unknown pane id | degrades cleanly, no 500 |

The single coverage gap is `steering` — the deliberately-retired pane that
redirects to `hierarchy` — and it is still answered by an FAQ entry.

---

## The defect: search could not answer a question

Every match was a whole-phrase substring test:

```python
if qlow in doc['title'].lower(): score += 10
```

So a query matched only if it appeared **verbatim**. Measured live:

| Query | Results |
|---|---|
| `agent` | 20 |
| `how do I add an API key` | **0** — and the FAQ answers exactly this |
| `keyboard shortcuts` | **0** — and there is a whole endpoint for them |

A help search that returns nothing for a question asked in words is worse than
no search: the user concludes the product has no answer when it is right
there. This is also the **most likely first interaction** with Docs — people
search help because they are already stuck.

**Fixed** by scoring per *token*, with a bonus when the full phrase also
appears so exact matches still rank first. Stop-words are dropped, so
"how do I add an API key" is scored on `{add, api, key}` rather than being
diluted by `{how, do, i}`. If a query is *only* stop-words the list is ignored
rather than returning nothing — a query that scores zero because we discarded
all of it is indistinguishable from one with no answer.

Deliberately simple: no stemmer, no index, no dependency. The corpus is a few
hundred short strings in memory.

`keyboard shortcuts` needed one extra rule: no individual shortcut
*description* contains the word "shortcut", so token matching alone still
found nothing. The thing the user asked for is the list itself.

**After:** 21 matches, topped by **Secrets Vault** and **"Do I need an
OpenRouter API key?"**. Single-word rankings unchanged; nonsense still 0.

---

## Two UI defects found in the same pass

**Silent truncation.** The API returns `count` (total matched) and `shown`
(capped at 20). The UI printed `results.length` and labelled it "N results", so
a query matching 21 rendered **"20 results"** with nothing saying one was
withheld — recurring pattern #9. This matters *more* after the search fix:
token matching returns far more hits, so the cap is now reachable at all,
whereas before multi-word queries returned zero.

**A one-character query did nothing.** `if (q.length < 2) return;` left the
previous view on screen, indistinguishable from a broken search.

The empty state was also one grey line; it now suggests what to try.

---

## Cross-module impact

- `_search_terms` / `_match_score` are local to `docs_center.py`. The global
  command palette (⌘K) has its own search and did **not** get this fix — a
  candidate when that module comes up the ranking.
- `.docs-search-*` styles went into `styles-redesign.css`, the linked sheet —
  not `styles.css`, which Module 1 proved is dead.

## Verification

| Check | Result |
|---|---|
| `how do I add an API key` | 0 → **21** results, correct top hits |
| `keyboard shortcuts` | 0 → **19** |
| Single-word queries | unchanged |
| Nonsense / empty query | still 0 |
| Truncated result set | now says "Showing the top 20 of 21" |
| One-character query | now explains the minimum |
| Revert all fixes | **9 of 16** tests fail |
| Full suite | 3,429 unit (2 skipped) + 655 (10 skipped), 0 failures |
