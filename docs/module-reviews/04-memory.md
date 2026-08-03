# Module Review 04 — Memory workstation

**Reviewed:** 2026-08-03 · **Commit:** `232587a` · **Sidebar position:** Memory (ESSENTIALS)

**Scope:** the consolidated Memory workstation — core Memory (`memory.py`, 16 endpoints)
plus the three tabs folded into it: **RAG** (11), **Knowledge Graph** (10) and
**Obsidian Sync** (13). 50 endpoints total, verified live.

---

## Findings

### 🔴 1. A 10 KB payload broadcast to every client every 8 seconds

`memory_stats()` returned **every distinct ingest source with no limit** — one row per
Obsidian note, per webhook, per test fixture. Measured here: **153 sources, 10,160 bytes**.

That same response is pushed over the WebSocket to every connected client on an 8-second
timer. And neither consumer uses it — the status bar reads `sqlite_memories`, the Galaxy
header reads three counters. The entire source list was pure waste on the hottest path in
the app.

**Fixed:** capped at 15 with `source_count` reporting the true total and
`sources_truncated` signalling the cut; `?source_limit=0` still returns everything. The
WebSocket broadcast was reduced further to counters only.

**10,160 → 674 bytes — a 93% reduction**, every 8 seconds, per client.

### 🔴 2. Obsidian accepted percent-encoded traversal as a literal filename

Note paths were bounds-checked only **after** the filename was accepted, using
`str.startswith()` on the resolved path. Requests are JSON, so the framework never
URL-decodes the value — `..%2f..%2fetc%2fpasswd` was written out verbatim.

Containment did hold (`/etc/passwd` was never touched — I verified), but the vault had
accumulated real files named `..%2f..%2fetc%2fpasswd.md`, `%2e%2e%2fetc%2fpasswd.md`, and
a stray `etc/` directory from absolute-path payloads.

**Fixed:** `validate_note_path()` rejects encoded traversal, absolute paths, backslash
variants and null bytes **up front**, normalises the result, and is backed by
`relative_to()` containment rather than a string prefix (which would treat a sibling
`brain_backup/` as inside `brain/`). Applied to read, write and delete.

Verified across 5 payload families on both read and write, while legitimate nested paths
with spaces still work.

### 🟠 3. 34 endpoints returned HTTP 200 on failure

Core Memory `GET`/`PUT`/`DELETE /{id}` returned 200 with `{"ok": false}` for a missing
row — so any caller branching on `response.ok` treated "not found" as success. `DELETE`
was worse: it reported `{"deleted": <id>}` for a row that never existed.

The same pattern ran through all three tab routers (6 in RAG, 8 in Knowledge Graph, 17 in
Obsidian). Rather than blanket-404 them, I mapped by failure class:

| Failure | Status |
|---|---|
| Validation / bad input | **400** |
| Not found | **404** |
| Path traversal | **403** |
| Extraction failed | **422** |
| Internal error | **500** |

`GET /rag/pipelines/{id}/documents` additionally never verified the pipeline existed — a
typo'd id returned an empty list, indistinguishable from a real pipeline with no documents.

---

## ⚠️ Four tests were passing against broken behaviour

Fixing the status codes surfaced something worth calling out: **four tests only passed
because failures returned 200.**

- `test_22::test_obsidian_create_note` posted `{"title": ...}` when the endpoint requires
  `"path"`. **The note was never created** — the test asserted a 200 on a validation error.
- `test_sys_03`, `test_uat_06` and `test_flow_06` posted `from_entity`/`to_entity` and
  `subject`, when the API takes `from_id`/`to_id` and `subject_id`. **No relation or fact
  was ever created** in any of them.

I confirmed this by stashing my changes and replaying the original request — the endpoint
returned `{"ok": false, "error": "path required"}` with a 200 the whole time.

All four now use the real contract and assert the operation actually succeeded, so they
test what their names claim.

---

## Verified working (no change needed)

- FTS5 search, hybrid search, galaxy graph, add/reindex/bulk-delete/import/export
- FTS index stays consistent — **zero orphaned rows** after delete
- RAG pipeline lifecycle: create → add document → chunk → retrieve → list
- Knowledge Graph entity/relation/fact creation, traversal, stats
- Obsidian vault detection, note listing, backlinks, daily notes

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | Biggest beneficiary — RAG grounding reads this store, and the poisoning fix from Module 1 plus these status codes make retrieval failures visible instead of silent. |
| **All panes (WebSocket)** | Every client gets the 93% smaller stats tick. |
| **Observability** | `source_count` is now available without shipping the whole list. |
| **Any API consumer** | 34 endpoints now return honest status codes — breaking for anything that relied on 200-always, correct for everything else. |

---

## Tests added

`tests/unit/test_53_memory_module_review.py` — **28 contracts**: payload bounding, the
WebSocket slimming, CRUD status codes, per-class status mapping across all three tab
routers, and 6 families of traversal payload against `validate_note_path()`.

**Suite:** 2802 backend passed / 12 skipped / **0 failed** · ruff clean.

---

## Recommended follow-ups

1. **Move the memory-ingest guard into `memory_db.memory_add()`** — still outstanding from
   Module 1, and this review reinforces it: the store is written by Chat, Webhooks,
   Obsidian and RAG independently, and only Chat currently guards against ingesting error
   text. A single choke point would fix all of them.
2. **The vault accumulates test artifacts.** I purged 7 encoded-traversal paths this round
   and 5 last round. `brain/` should be gitignored, or tests should use a temp vault.
3. **Qdrant is optional and currently absent** (`vectors_sqlite: 0`), so "hybrid" search is
   FTS-only. The UI reports the engine honestly, but it's worth surfacing that vector
   search is inactive rather than implying hybrid ranking is happening.
4. **Knowledge Graph has no UI for relations** — entities render, but the relation and fact
   endpoints have no frontend surface. Worth building when I reach that tab in depth.
