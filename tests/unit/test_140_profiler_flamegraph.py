"""Module review 7: `finetune`, `pluginsdk`, `pqc`, `profiler`.

All four render from `frontend/js/03-features-a.js` (3,006 lines, 30
endpoints) and were reviewed as one unit. All score 20.

THE DEFECT: THE SERVER SAID "SYNTHETIC" AND THE UI NEVER LISTENED
─────────────────────────────────────────────────────────────────
`/api/profiler/flamegraph` returns a hand-written call tree:

    main 1000 -> handle_request 850 -> chat_router 400 -> llm.complete() 320
              -> httpx.post() 280 -> ssl_connect() 60 / stream_response() 190

An earlier batch had already fixed the BACKEND, which now reports:

    synthetic: true
    has_real_data: false
    note: "The base tree is illustrative sample data, not a measurement of
           this process..."

`renderFlamegraph()` reads **none of it**. It renders `d.flamegraph[0]` and
stops, so the pane showed an unlabelled fake profile beside genuinely measured
panels — process RSS, DB row counts, agent timings — with nothing to tell them
apart.

Fixing the server and not the client leaves the user exactly where the server
fix was meant to move them. That is the **"second door"** pattern in its
API/UI form, now 9+ occurrences in this review.

A flamegraph is *acted on*: a developer reads "ssl_connect 60ms" and goes
looking for it. Labelling costs one banner.

The convention was already in this repo, one file away: the PQC pane reads
`algos.simulated` and badges itself SIMULATED, with a comment saying that being
honest about it is the point. This follows that rather than inventing a second
treatment.

A CORRECTION TO MY OWN FINDING
──────────────────────────────
I first reported the backend as fabricating data and started patching it. It
had already been fixed — the response carried `synthetic`, `note` and
`has_real_data`, and even merges real endpoint latencies under a
`real_endpoints` subtree when `_endpoint_stats` has data. I reverted that edit.
The gap was only ever on the client.

VERIFIED AS ALREADY CORRECT
───────────────────────────
  * All 13 GET endpoints across the four panes return 200 on an empty account.
  * `/api/pqc/algorithms` reports `simulated: true` and the pane badges it.
  * `/api/finetune/hardware` performs real detection and returns an honest
    notice: "No local training backend is installed... Fine-tuning is
    unavailable on this machine — datasets can still be prepared."
  * All four panes render with zero page errors.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PROFILER = (REPO / 'backend' / 'routers' / 'profiler.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '03-features-a.js').read_text(encoding='utf-8')
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')


def _flamegraph() -> dict:
    """Call the real handler rather than re-describing it."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.profiler import flamegraph_data
    return flamegraph_data()


def _render_block() -> str:
    return JS[JS.index('async function renderFlamegraph'):][:3000]


# ──────────────────────────────────────────────────────────────────────
#  The contract the backend already provides
# ──────────────────────────────────────────────────────────────────────
def test_the_endpoint_declares_the_tree_synthetic():
    out = _flamegraph()
    assert out.get('synthetic') is True


def test_the_endpoint_explains_what_is_and_is_not_measured():
    out = _flamegraph()
    note = out.get('note', '')
    assert 'not a measurement' in note
    assert 'real_endpoints' in note


def test_the_endpoint_reports_whether_real_data_exists():
    """`has_real_data` is what lets the UI distinguish "no requests profiled
    yet" from "observed latency is included below"."""
    assert 'has_real_data' in _flamegraph()


# ──────────────────────────────────────────────────────────────────────
#  The UI must honour it
# ──────────────────────────────────────────────────────────────────────
def test_the_pane_reads_the_synthetic_flag():
    """It rendered d.flamegraph[0] and nothing else, so the flag the server
    went to the trouble of sending was discarded."""
    assert 'd.synthetic' in _render_block()


def test_the_pane_shows_a_sample_data_banner():
    block = _render_block()
    assert 'flame-synthetic' in block
    assert 'SAMPLE DATA' in block


def test_the_banner_is_styled():
    """An unstyled banner inherits whatever the pane sets and reads as body
    text -- which is how it would be missed."""
    assert '.flame-synthetic' in CSS
    assert '.flame-synthetic__badge' in CSS


def test_the_banner_shows_the_servers_own_note():
    """Re-writing the explanation in the client would let the two drift."""
    block = _render_block()
    assert 'd.note' in block


def test_the_banner_distinguishes_no_data_from_real_data():
    """"No requests profiled yet" and "observed latency is included" are
    different states and must not render identically."""
    block = _render_block()
    assert 'd.has_real_data' in block
    assert 'No requests profiled yet' in block


def test_a_measured_flamegraph_would_show_no_banner():
    """The banner must be conditional, or a future real profiler is libelled
    as fake."""
    block = _render_block()
    assert 'synthetic ?' in block or "synthetic\n" in block or 'const synthetic' in block
    assert ": ''" in block, 'the banner must be empty when not synthetic'


# ──────────────────────────────────────────────────────────────────────
#  Guards on the sibling panes
# ──────────────────────────────────────────────────────────────────────
def test_pqc_still_declares_itself_simulated():
    """The convention this fix follows. If PQC ever stops flagging itself the
    precedent is gone and so is the reason this banner looks the way it does.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.pqc import list_pqc_algorithms

    out = list_pqc_algorithms()
    assert out.get('simulated') is True
    assert 'pqcSimulated' in JS


def test_finetune_hardware_is_detected_not_asserted():
    """A "training available" claim on a machine with no backend would be the
    same fabrication class as the Dashboard's $350."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.finetune import get_finetune_hardware

    out = get_finetune_hardware()
    assert 'training_available' in out
    assert isinstance(out['training_available'], bool)
    if not out['training_available']:
        assert out.get('notice'), 'an unavailable feature must say why'
