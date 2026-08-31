"""Module 1 of the module-by-module review: the collaborative editor.

WHY THIS MODULE FIRST
─────────────────────
`scripts/audit/module_risk.py` ranks all 68 panes by measurable risk. Collab
Edit scored **53**, far ahead of the next module (35): it was the *only* pane
with no test coverage at all, at 693 lines and 7 endpoints.

The ranking was right. Two real defects, both invisible to the other 22
audits.

DEFECT 1 — MALFORMED OPS SILENTLY CORRUPTED THE SHARED DOCUMENT
───────────────────────────────────────────────────────────────
`_apply_op()` iterates the operation and ignores anything it does not
recognise. Fine for a well-formed list; catastrophic otherwise, because the op
is applied, persisted, broadcast to every peer, and answered `ok: true`.

Measured live against the running server:

    {"op": {"type":"insert","pos":0,"text":"X"}}  ->  content "typepostext"
    {"op": "just a string"}                       ->  inserted char by char
    {"op": [{"nested":1}]}                        ->  dropped, revision +1
    {"op": [1.5, true]}                           ->  dropped, revision +1

The last two are their own bug: an op that applies nothing still consumes a
revision, so every other peer's revision is stale and their next edit is
transformed against a phantom operation.

This matters more than an ordinary validation gap because the document is
SHARED. A corrupt write is broadcast to everyone in the room and written to
the op log, so the damage is collective and permanent — and `ok: true` means
no client ever learns.

Fixed with one validator used by **both** entry points. The HTTP route and the
WebSocket are two doors to the same document, and a guard on one protects
nobody — the "second door" pattern, now hit 7+ times in this review. The
socket is in fact the door the UI uses.

DEFECT 2 — THE ENTIRE MODULE WAS UNSTYLED
─────────────────────────────────────────
All 32 `.ce-*` rules lived in `frontend/styles.css`, which is **not linked**
from index.html. Measured in Chromium: every element rendered as an unstyled
`display:block` stack, and `.ce-editor` — the textarea that is the whole point
of the pane — was **178×32px** instead of a full-height surface.

Same class as the 611px Goals overflow in batch 36: a rule that exists, reads
correctly, and never loads. After porting: editor 936×604, sidebar 240px,
proper flex layout.

A PROBE BUG OF MINE, CORRECTED
──────────────────────────────
My first probe sent `{type, pos, text}` and I nearly reported the OT engine as
broken. The frontend and backend agree perfectly on a **list** format
(`[5, "text", -3]`) — `ceComputeOp()` produces exactly what `_apply_op()`
consumes. Two clients over the real WebSocket collaborate correctly.

The bug was that the server *accepted my malformed input at all*.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
CRDT = (REPO / 'backend' / 'routers' / 'crdt.py').read_text(encoding='utf-8')
CE_JS = (REPO / 'frontend' / 'js' / '08-replay-collab.js').read_text(encoding='utf-8')
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
HTML = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')


def _validator():
    """Import the real validator, not a copy of it."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.crdt import OpValidationError, _validate_op
    return _validate_op, OpValidationError


# ──────────────────────────────────────────────────────────────────────
#  Defect 1: op validation
# ──────────────────────────────────────────────────────────────────────
def test_a_dict_op_is_rejected():
    """It stored the dict's KEYS: "typepostext"."""
    validate, err = _validator()
    with pytest.raises(err):
        validate({'type': 'insert', 'pos': 0, 'text': 'X'}, 0)


def test_a_bare_string_op_is_rejected():
    """A str iterates as characters, inserting each one separately."""
    validate, err = _validator()
    with pytest.raises(err):
        validate('just a string', 0)


def test_a_nested_object_component_is_rejected():
    validate, err = _validator()
    with pytest.raises(err):
        validate([{'nested': 1}], 0)


def test_a_float_component_is_rejected():
    validate, err = _validator()
    with pytest.raises(err):
        validate([1.5], 0)


def test_a_boolean_component_is_rejected():
    """`isinstance(True, int)` is True in Python, so [True] would otherwise be
    read as retain(1) — a silent, plausible-looking corruption."""
    validate, err = _validator()
    with pytest.raises(err):
        validate([True], 10)


def test_an_op_reading_past_the_document_is_rejected():
    """Applying it anyway silently truncates other people's work."""
    validate, err = _validator()
    with pytest.raises(err):
        validate([9999], 5)


def test_a_zero_length_component_is_rejected():
    validate, err = _validator()
    with pytest.raises(err):
        validate([0], 10)
    with pytest.raises(err):
        validate([''], 10)


def test_an_empty_op_is_rejected():
    validate, err = _validator()
    with pytest.raises(err):
        validate([], 10)


def test_valid_ops_are_accepted_unchanged():
    """The fix must not break the format the UI actually sends."""
    validate, _ = _validator()
    assert validate(['Hello'], 0) == ['Hello']
    assert validate([5, 'x', -2], 10) == [5, 'x', -2]
    assert validate([3], 10) == [3]


def test_the_error_message_is_addressed_to_a_person():
    """This surfaces in the editor, so it must not read as machine output."""
    validate, err = _validator()
    with pytest.raises(err) as caught:
        validate({'type': 'insert'}, 0)
    message = str(caught.value)
    assert 'list of operations' in message
    assert not message.startswith('<')


def test_both_entry_points_validate():
    """THE SECOND DOOR. The HTTP route and the WebSocket are two entrances to
    the same document; a guard on one protects nobody. The socket is the one
    the UI uses."""
    assert CRDT.count('_validate_op(') >= 3, (
        'expected the definition plus a call in each of the HTTP and WS paths')
    ws_block = CRDT[CRDT.index("if mtype == 'op':"):]
    ws_block = ws_block[:1200]
    assert '_validate_op' in ws_block, 'the WebSocket path is unguarded'


def test_a_refused_write_does_not_answer_200():
    """The frontend's network layer reports by status code, so a 200 with
    ok:false sails straight through and the user is told nothing."""
    http_block = CRDT[CRDT.index("async def submit_op"):]
    http_block = http_block[:1600]
    assert 'status_code=400' in http_block


def test_the_socket_reports_the_refusal_to_the_client():
    """Dropping it silently would leave the editor on "syncing" forever while
    the user's text was never saved — worse than the bug being fixed."""
    ws_block = CRDT[CRDT.index("if mtype == 'op':"):][:1200]
    assert "'type': 'error'" in ws_block

    assert "msg.type === 'error'" in CE_JS, 'the client ignores the refusal'
    # 1600, not 900: the handler carries a long explanatory comment and the
    # toast call sits past the shorter window. Slicing too tightly judged a
    # fragment rather than the handler.
    handler = CE_JS[CE_JS.index("msg.type === 'error'"):][:1600]
    assert 'toast(' in handler, 'the user is not told'
    assert 'not saved' in handler, 'the sync indicator must reflect reality'


# ──────────────────────────────────────────────────────────────────────
#  Defect 2: the module was unstyled
# ──────────────────────────────────────────────────────────────────────
def test_collab_styles_live_in_a_linked_stylesheet():
    """All 32 .ce-* rules were in frontend/styles.css, which index.html does
    not link. Measured: .ce-editor was 178x32px."""
    linked = set(re.findall(r'href="/static/(styles[a-z-]*\.css)"', HTML))
    assert 'styles-redesign.css' in linked
    assert 'styles.css' not in linked, (
        'styles.css is deliberately NOT linked; do not fix this by linking it '
        '— it is 228KB of superseded rules'
    )
    for selector in ('.ce-layout', '.ce-sidebar', '.ce-main', '.ce-editor'):
        assert selector in CSS, f'{selector} is still not in a loaded sheet'


def test_the_editor_has_a_layout_rule():
    """The specific failure: an inline-block textarea at 178x32."""
    block = CSS[CSS.index('.ce-editor'):][:400]
    assert 'flex' in block or 'height' in block or 'width' in block


def test_the_refused_edit_state_has_a_style():
    """A className the CSS does not define renders as the default state, so
    the indicator would look 'synced' while the edit was refused."""
    assert '.ce-op-indicator.err' in CSS


def test_the_keyframes_came_across_too():
    """`.ce-op-indicator.syncing` animates; without the keyframes the rule is
    inert and the pulse silently does nothing."""
    assert 'ce-pulse' in CSS
    assert '@keyframes ce-pulse' in CSS

# ── OT transform correctness (property) ─────────────────────────────────────
# _transform must preserve convergence: applying A then B' equals applying B
# then A'. These minimal cases exercise the delete-dropping / retain-delete
# paths, which the earlier shallow test_transform_op (status-code only) never
# checked.


class TestOtTransformConvergence:
    def _conv(self, base, op_a, op_b, side='left'):
        from backend.routers.crdt import _apply_op, _transform
        a2, b2 = _transform(op_a, op_b, side)
        r_ab = _apply_op(_apply_op(base, op_a), b2)
        r_ba = _apply_op(_apply_op(base, op_b), a2)
        return r_ab, r_ba

    def test_insert_wins_vs_full_delete_left(self):
        # base 'ab'; A inserts 'X' after 'a'; B deletes all of 'ab'.
        # Concurrency must converge (B's delete applies either side).
        r_ab, r_ba = self._conv('ab', [1, 'X'], [-2], 'left')
        assert r_ab == r_ba, f'diverge: {r_ab!r} != {r_ba!r}'

    def test_insert_conflicts_with_delete_prefix(self):
        r_ab, r_ba = self._conv('abc', [1, 'XY', 2], [-1, 2], 'left')
        assert r_ab == r_ba, f'diverge: {r_ab!r} != {r_ba!r}'

    def test_two_concurrent_deletes_converge(self):
        r_ab, r_ba = self._conv('abcd', [-2, 2], [1, -1, 2], 'left')
        assert r_ab == r_ba, f'diverge: {r_ab!r} != {r_ba!r}'
