# 90 — Inbox

**Pane:** `inbox`
**Frontend:** `frontend/js/60-inbox.js` (282 ln)
**Backend:** `backend/routers/inbox.py` (134 ln), `backend/services/capture_inbox.py`
**Tests:** `tests/unit/test_190_inbox_routing.py` (10)
**Status:** reviewed, two defects fixed, verified live end-to-end

The second of two destinations with no review document, and the thinnest tested
surface in the app.

---

## The promise, and what actually happened

The pane says: **"Capture anything, the router files it."** Capture worked.
Filing was unreachable for a new user, for two independent reasons — each of
which alone was enough to make the feature inert.

### Defect 1 — a new workspace could never receive anything

`icm_router.parse_routes()` reads trigger phrases from a `## Routes` section of
a workspace's L1 `CONTEXT.md`. **The scaffolder never wrote that section.**

Verified on a freshly created workspace: `# Routing`, a stage table,
`## Conventions` — no `## Routes`. The ICM pane has no UI for adding one, only
a read-only view stating "No routes declared".

Both halves were complete and there was no path between them. The only way to
connect them was to know the exact markdown heading and hand-edit the file.

Scaffolding now emits an empty `## Routes` with a comment saying what belongs
there and what happens without it. **Empty is correct** — inventing routes
would file a user's notes somewhere they never chose, the wrong-folder failure
ICM exists to prevent — but *absent* is not, because absent is invisible.

### Defect 2 — declared routes did not match real sentences

`score_workspace()` required the whole phrase contiguously:

```python
if f' {phrase} ' in hay:
```

A workspace declaring `- vendor renewal quote` scored **0.0** against

> "Follow up with the vendor about the renewal quote"

Every word present, in order, separated by two filler words. The sweep reported
*"no workspace declared a route for this request"* — actively misleading, since
a route was declared and did match in every sense a person would mean.

A route is a human's stated intent, not a search query. A multi-word route now
earns partial credit when a clear majority of its words appear, scaled by the
fraction matched × `W_ROUTE_PARTIAL` (0.75) so an exact phrase always outranks
a near miss.

---

## Verified end to end, through HTTP

```
POST /api/inbox        -> captured
PUT  .../CONTEXT.md    -> "- vendor renewal quote"
POST /api/inbox/sweep  -> filed: vendor-ops / 01-intake
                          reason: route: 'vendor renewal quote' (3/3 words)
GET  /api/inbox/stats  -> inbox 0, filed 1
```

## Two bugs my own fixes caused, both caught by tests

1. **The stub's commented example became real routes.** `parse_routes` reads
   bullets without stripping HTML comments, so every new workspace silently
   declared `weekly client report` and `invoice`. The first workspace a user
   created would have captured traffic it never asked for. Comments are now
   stripped.

2. **Adding the stub broke 26 pre-existing tests.** `icm._section()` returns
   the *first* matching section by design; the older fixtures *append* a second
   `## Routes`. With the stub always present, appended routes became invisible
   — a corner case promoted to the default. `parse_routes` now reads every
   `## Routes` section. Those 26 tests were right; the narrow read was wrong.

## Improvements proposed, NOT implemented — awaiting your call

- **A route editor in the ICM pane.** The section is now discoverable but still
  requires editing markdown. A small "what should arrive here?" field on the
  Routing tab would close the loop properly. This is UI work, so I am asking
  rather than assuming.
- **Suggest routes on workspace creation.** `icm_dialogue.routes_block()`
  already proposes routes from a description and `/describe/create` uses it —
  plain creation does not. Wiring it would make routes work without any editing,
  but it means writing routes a user did not explicitly approve.

## Affected modules

`icm` — both fixes are in ICM services. `parse_routes` and `score_workspace`
are consumed by the Inbox sweep, the ICM Routing tab, and chat context
injection (`test_148`). All three verified green.
