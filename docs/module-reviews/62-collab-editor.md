# 62 — Module review 1: Collaborative Editor (`collabedit`)

**First module of the risk-ranked review.** `scripts/audit/module_risk.py`
scores all 68 panes on five measurable signals; Collab Edit scored **53**, far
ahead of the next (35). It was the only pane with **no test coverage at all**,
at 693 lines and 7 endpoints.

The ranking was right: two real defects, both invisible to the other 22 audits.

---

## Defect 1 — malformed ops silently corrupted the shared document

`_apply_op()` iterates the operation and ignores anything it does not
recognise. Fine for a well-formed list; catastrophic otherwise, because the op
is applied, persisted, broadcast to every peer, and answered `ok: true`.

Measured live against the running server:

| Payload | Result |
|---|---|
| `{"type":"insert","pos":0,"text":"X"}` | content became `"typepostext"` (a dict iterates as its **keys**) |
| `"just a string"` | inserted character by character |
| `[{"nested":1}]` | dropped — **but revision still incremented** |
| `[1.5, true]` | dropped — **but revision still incremented** |

The last two are their own bug: an op that applies nothing still consumes a
revision, so every other peer's revision is stale and their next edit is
transformed against a phantom operation.

This matters more than an ordinary validation gap because the document is
**shared**. A corrupt write is broadcast to everyone in the room and written to
the op log, so the damage is collective and permanent — and `ok: true` means no
client ever learns.

**Fixed** with one validator used by **both** entry points. `bool` is rejected
explicitly because `isinstance(True, int)` is `True` in Python, so `[True]`
would otherwise read as `retain(1)`. An op reading past the end of the document
is rejected rather than silently truncating other people's work.

The HTTP route and the WebSocket are two doors to the same document, and a
guard on one protects nobody — the **"second door"** pattern, now hit 7+ times
in this review. The socket is in fact the door the UI uses.

The HTTP path answers **400**, not 200-with-`ok:false`: the frontend's network
layer reports by status code, so a 200 sails straight through.

## Defect 2 — the entire module was unstyled

All **32** `.ce-*` rules lived in `frontend/styles.css`, which is **not linked**
from index.html. Measured in Chromium:

| | before | after |
|---|---|---|
| `.ce-editor` | **178×32px**, `inline-block` | 936×604 |
| `.ce-layout` | `display:block` | `flex` |
| `.ce-sidebar` | 1176px wide (full width) | 240px |

The textarea that is the entire point of the pane was a 178×32 box. Same class
as the 611px Goals overflow in batch 36: a rule that exists, reads correctly,
and never loads.

## Frontend: refusals are now surfaced

The client had no `error` handler, so a rejected edit would have been dropped
silently — the editor would sit on "syncing" forever while the user's text was
never saved, a *worse* failure than the one being fixed. It now shows the
server's message, sets the indicator to "not saved", and resyncs the revision.

---

## What was verified as already working

Two clients over the real WebSocket protocol: join → `init` → op → `ack` to the
sender, `op` relayed to the peer, correct content on the server. **The OT
engine is sound.** `ceComputeOp()` produces exactly the format `_apply_op()`
consumes.

---

## Mistakes of mine, recorded

**I nearly reported the OT engine as broken.** My first probe sent
`{type,pos,text}` — the intuitive shape, and not the wire format. The real bug
was that the server *accepted* it.

**A stale `.pyc` made a revert-proof lie.** Sabotaging `_apply_op` and re-running
the tests showed them passing; the sabotage was live in the source and the test
run was loading `backend/routers/__pycache__/crdt.cpython-313.pyc`. Clearing
`__pycache__` made the sabotage bite immediately. Any revert-proof in this repo
must clear caches first — otherwise it verifies the previous build.

**Two pre-existing tests pinned the bug.** `tests/system/test_sys_05_platform.py`
and `tests/uat/test_uat_07_docs_onboarding.py` both sent
`[0, "insert", "PREPENDED: "]`, which produced `'insertPREPENDED: ...'` — the
literal word "insert" in the document. Updated in place with the reason.

The system test also asserted `revision >= 0`, true of every possible response.
Strengthened to assert the inserted text is present and the revision advanced.

---

## Cross-module impact

- `backend/routers/collab.py` has its own session/state WebSocket and does
  **not** share this validator — a separate surface, reviewed later.
- `styles.css` remains unlinked and still holds rules for other panes. The
  module-risk sweep should look for more of these.
- The new `error` frame type is additive; existing clients ignore unknown types.

## Verification

| Check | Result |
|---|---|
| 5 malformed payloads over HTTP | 5 × **400** with human-readable messages |
| 5 malformed payloads over the socket | 5 × `error`, **none broadcast to the peer** |
| Valid op, two clients | still collaborates; content `'Hello'`, revision 1 |
| Rejected ops | no longer consume a revision |
| Revert all fixes | **17 of 17** new tests fail |
| Full suite | 3,413 unit (2 skipped) + 655 (10 skipped), 0 failures |
