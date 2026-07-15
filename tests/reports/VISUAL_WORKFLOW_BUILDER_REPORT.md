# Visual Workflow Builder (Drag-and-Drop Canvas) — Full Build & Verification Report
**Date:** 2026-07-15  
**Test Result: ✅ 51/51 tests PASSED (100%)**

---

## What Was Built vs What Already Existed

### Pre-existing (solid foundation)
- 10 node types (trigger, agent, condition, transform, loop, delay, webhook, output, memory, code)
- Drag-and-drop from palette to canvas
- Pan canvas (click-drag)
- Scroll-wheel zoom
- Node drag/move
- Edge drawing (port-to-port)
- Properties panel (basic)
- Node select
- Save workflow (PUT endpoint)
- Run workflow (SSE streaming)
- Zoom to fit
- Clear canvas
- Run log panel
- Keyboard: ⌘S to save, node_start/node_output events during run
- Auto-layout, node templates, edge labels
- 3 starter workflows (seeded on first load)

### New Features Added (frontend)
1. **Copy/Paste nodes** (⌘C / ⌘V) — clipboard state, paste with offset
2. **Duplicate node** (⌘D) — one-click copy in place
3. **Minimap** — 140×88px canvas overview with viewport rectangle; click to center
4. **Live wire** — visual SVG bezier while dragging connection between ports
5. **Edge selection & deletion** — click edge to select; Delete key or right-click to remove
6. **Right-click context menus** — node menu (duplicate/copy/properties/delete), edge menu (delete), canvas menu (add node, paste)
7. **Workflow rename** — click workflow name in toolbar
8. **Workflow duplicate** — sidebar list item action
9. **Export workflow** — download JSON button in toolbar
10. **Import workflow** — upload JSON button in sidebar
11. **Validation badge** — top-right shows ✓ Valid / ✗ N issues / ⚠ N warnings, click for detail
12. **Auto-save on debounce** — 2s after last change
13. **Undo/Redo** (⌘Z/⌘⇧Z) — full history stack with snapshot-based approach
14. **Arrow-key nudge** — move selected node 5px (20px with Shift)
15. **Escape to deselect** — clears selection, closes properties, cancels connection
16. **Snap to grid** — nodes snap to 10px grid on mouse-up
17. **Zoom toward cursor** — scroll zoom centered on mouse position
18. **Node output preview** — small text preview of each node's output shown on the card during run
19. **Palette filter** — live search to filter node chips
20. **Double-click to add** — double-click palette chip adds node at canvas center
21. **Condition node ports** — true port (right-center) + false port (right-70%) with distinct styling
22. **Delete list actions** — ⧉ duplicate / ⬇ export / ✕ delete per workflow in sidebar
23. **Animated edges during run** — active edge gets amber flowing dash animation
24. **Node property config for ALL types** — agent (model+prompt+max_tokens), trigger (event+cron), output (target), condition (expression+labels), delay, webhook (method+url), memory (action), transform (mode), code (JS textarea)

### Bugs Fixed

| # | Bug | Fix |
|---|-----|-----|
| 1 | `wfSave()` used `await` without `async` keyword | Rewritten as proper `async function wfSave()` |
| 2 | Backend `run_workflow` used `con.commit()` after `_con = get_conn()` | Changed to `_con.commit()` and `_con.close()` |
| 3 | No live wire when dragging connection | Added `#wf-live-wire-path` SVG path + mousemove handler |
| 4 | No edge deletion mechanism | Added edge click → select, Delete key, right-click context menu |
| 5 | Zoom didn't center on cursor | Fixed using mouse-relative zoom math |
| 6 | Undo stack existed but wasn't fully wired | `wfPushHistory()` called on every mutation, `wfUpdateUndoButtons()` disables when at limits |
| 7 | Properties panel closed but node stayed selected visually | `wfCloseProps()` doesn't deselect; canvas click does |
| 8 | `_wfConnecting` state not cleared on mouseup with no target | Added cleanup in global mouseup handler |

### New Backend Endpoints (6)

| Endpoint | Description |
|----------|-------------|
| `POST /api/workflow/{id}/duplicate` | Create copy with new ID; optional `name` in body |
| `POST /api/workflow/import` | Import workflow JSON; assigns new ID if conflict |
| `GET  /api/workflow/{id}/export` | Download as `{name}.wf.json` attachment |
| `DELETE /api/workflow/{id}/edges/{edge_id}` | Remove single edge (idempotent) |
| `POST /api/workflow/{id}/validate` | Check for issues: NO_TRIGGER, INVALID_EDGE, ORPHANED, CYCLE |

---

## Feature Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Drag node from palette to canvas | ✅ | HTML5 drag/drop API |
| Double-click palette to add at center | ✅ NEW | |
| Move nodes by dragging | ✅ | 10px grid snap on release |
| Connect nodes via ports | ✅ | mousedown output → mouseup input |
| Live wire during connection | ✅ NEW | SVG bezier preview |
| Select node (click) | ✅ | Visual highlight + properties panel |
| Select edge (click) | ✅ NEW | SVG path click |
| Delete node (Del key, context menu) | ✅ | Removes connected edges too |
| Delete edge (Del key, context menu) | ✅ NEW | |
| Properties panel (all 10 node types) | ✅ | Full config per type |
| Copy/Paste node (⌘C/⌘V) | ✅ NEW | |
| Duplicate node (⌘D) | ✅ NEW | |
| Undo/Redo (⌘Z/⌘⇧Z) | ✅ | Snapshot-based, full history |
| Arrow key nudge | ✅ NEW | 5px normal, 20px with Shift |
| Pan canvas | ✅ | Click-drag background |
| Scroll zoom (cursor-centered) | ✅ | Math: zoom toward mouse |
| Zoom to fit | ✅ | Auto-scales all nodes |
| Minimap | ✅ NEW | Click to navigate |
| Palette filter | ✅ NEW | Live search |
| Right-click context menus | ✅ NEW | Node / edge / canvas |
| Workflow rename | ✅ NEW | Click toolbar name |
| Workflow duplicate | ✅ NEW | Sidebar + API |
| Workflow export JSON | ✅ NEW | Download attachment |
| Workflow import JSON | ✅ NEW | File picker |
| Validation badge | ✅ NEW | Real-time issues/warnings |
| Auto-save (2s debounce) | ✅ NEW | |
| Run with SSE streaming | ✅ | node_start → node_output → done |
| Node output preview on card | ✅ NEW | Shows during run |
| Animated edges during run | ✅ NEW | Amber flowing dash |
| Condition node dual ports | ✅ | true port + false port |

---

## Test Coverage — 51 Tests

| Group | Tests | What's Verified |
|-------|-------|----------------|
| Node Types | 5 | 10 types, required fields, trigger/output port counts |
| CRUD | 7 | List, create, get, update, timestamps, appears in list |
| Validate | 6 | Valid workflow, inline data, NO_TRIGGER, ORPHANED, INVALID_EDGE, ok field |
| Duplicate | 4 | Creates new ID, default name, in list, fresh timestamps |
| Export/Import | 6 | Export content-type, filename, import ID assignment, conflict handling, in list |
| Edge Deletion | 2 | Delete edge, idempotent missing edge |
| Workflow Run | 4 | Simple workflow, nonexistent, node events, agent node |
| Starter Workflows | 5 | chat_pipeline (4n,3e), code_review (7n,7e), swarm (6n), validate all, run |
| Frontend Contract | 11 | Required fields, positions, edge fields, colors, API response shapes |
| Cleanup | 1 | Delete all test workflows |

---

*Backend: `/home/user/agentic-os/backend/routers/workflow.py` — 6 new endpoints + bug fixes*  
*Frontend: `/home/user/agentic-os/frontend/index.html` — complete workflow section rewritten (69KB)*  
*Tests: `/home/user/agentic-os/tests/connectors/test_workflow_builder.py`*
