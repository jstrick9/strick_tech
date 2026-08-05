"""Panes that invented data when the server had none.

Three instances of one pattern: the UI fell back to a hardcoded literal
whenever the real value was missing, and presented the invention with the same
confidence as a measurement. In each case the server was telling the truth and
the frontend overrode it.
"""
import pytest

BASE = "http://127.0.0.1:8787"

_BOOT = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""


@pytest.fixture
def app(page):
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(800)
    page.evaluate(_BOOT)
    page.wait_for_timeout(200)
    return page


# ══ Fine-tuning datasets ══════════════════════════════════════════════════════

def test_the_finetune_pane_does_not_invent_datasets(app):
    """It showed two datasets that do not exist, badged READY.

    The list fell back to `ds_chat_v1` (rows: 42) and `ds_evals_v1` (rows: 18)
    whenever the API returned none. Verified against the running server:

        GET  /api/finetune/datasets            -> {"ok":true,"count":0,"datasets":[]}
        POST /api/finetune/jobs/start
             {"dataset_id":"ds_chat_v1"}       -> "Dataset 'ds_chat_v1' not found"

    So a new user saw two datasets that looked ready to train, pressed
    "Train Adapter", and the only possible outcome was an error. The row counts
    were fiction presented as measurements.
    """
    app.evaluate('async () => { await window.renderFinetuneWorkstation(); }')
    app.wait_for_timeout(1200)

    real = app.evaluate("""async () => {
        const r = await fetch('/api/finetune/datasets');
        const j = await r.json();
        return (j.datasets || []).length;
    }""")
    html = app.evaluate("() => document.getElementById('pane-finetune').innerHTML")

    for phantom in ('ds_chat_v1', 'ds_evals_v1', 'default_dataset'):
        assert phantom not in html, (
            f'the fine-tune pane is still rendering the invented dataset id {phantom!r}'
        )

    if real == 0:
        text = app.evaluate("() => document.getElementById('finetune-dataset-list').innerText")
        assert 'No training datasets yet' in text, (
            f'with 0 real datasets the pane should show an empty state, showed:\n{text[:400]}'
        )


def test_a_dataset_shown_as_trainable_can_actually_be_trained(app):
    """Whatever the pane lists must exist server-side.

    This is the assertion that would have caught the original bug even if the
    invented ids had been renamed: every id offered to `finetuneStartJob` is
    checked against the server's own list.
    """
    app.evaluate('async () => { await window.renderFinetuneWorkstation(); }')
    app.wait_for_timeout(1200)

    offered = app.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('#pane-finetune [data-act-click]')) {
            const m = /finetuneStartJob\\((.*)\\)/.exec(el.getAttribute('data-act-click') || '');
            if (m) out.push(m[1].replace(/^['"]|['"]$/g, ''));
        }
        return out;
    }""")
    real = app.evaluate("""async () => {
        const r = await fetch('/api/finetune/datasets');
        const j = await r.json();
        return (j.datasets || []).map(d => d.id);
    }""")

    for dataset_id in offered:
        assert dataset_id in real, (
            f'the UI offers to train dataset {dataset_id!r}, which the server does '
            f'not have. Server reports: {real}'
        )


# ══ PQC vault ═════════════════════════════════════════════════════════════════

def test_the_pqc_pane_shows_the_servers_algorithms_not_a_hardcoded_list(app):
    """It read a field the API has never returned, so the fallback always won.

    The pane read `algos.algorithms`. `GET /api/pqc/algorithms` returns
    `kem_algorithms` and `signature_algorithms`. The lookup was always
    undefined, so the `||` fallback fired every time and the pane displayed
    three invented entries — never once the server's real answer.
    """
    app.evaluate('async () => { await window.renderPQCVault(); }')
    app.wait_for_timeout(1200)

    server = app.evaluate("""async () => {
        const r = await fetch('/api/pqc/algorithms');
        const j = await r.json();
        return {
            names: [...(j.kem_algorithms || []), ...(j.signature_algorithms || [])],
            simulated: j.simulated === true,
        };
    }""")
    text = app.evaluate("() => document.getElementById('pqc-algo-list').innerText")

    assert server['names'], 'the API returned no algorithms; this test needs them'
    for name in server['names']:
        assert name in text, (
            f'the PQC pane does not show the server algorithm {name!r} — '
            'it is still rendering its own hardcoded list'
        )
    assert 'AES-256-GCM-Lattice-Wrapped' not in text, (
        'the invented hardcoded algorithm entry is still being rendered'
    )


def test_simulated_crypto_is_never_labelled_verified(app):
    """The pane badged each algorithm "VERIFIED".

    backend/routers/pqc.py states on its other routes that this is "SIMULATED
    post-quantum cryptography ... SHA3 hashing and XOR masking, NOT
    ML-KEM/Kyber or Dilithium. Provides no confidentiality."

    Telling a user their key exchange is quantum-resistant and VERIFIED when
    the backend says it is a simulation is the most dangerous way this UI could
    be wrong — it is exactly the claim someone would rely on before putting a
    real secret in.
    """
    app.evaluate('async () => { await window.renderPQCVault(); }')
    app.wait_for_timeout(1200)

    simulated = app.evaluate("""async () => {
        const r = await fetch('/api/pqc/algorithms');
        return (await r.json()).simulated === true;
    }""")
    if not simulated:
        pytest.skip('the backend no longer reports this as simulated')

    text = app.evaluate("() => document.getElementById('pqc-algo-list').innerText")
    assert 'VERIFIED' not in text, (
        'simulated cryptography is still badged VERIFIED:\n' + text[:400]
    )
    assert 'SIMULATED' in text, 'the simulated status is not shown to the user at all'


def test_the_algorithms_endpoint_carries_its_own_disclaimer(app):
    """Every other PQC route returns simulated/warning; this one did not.

    It was the worst place to omit it: it is the route the UI renders as a
    capability list, so with no disclaimer in the payload the frontend had
    nothing to display one from.
    """
    resp = app.request.get(f'{BASE}/api/pqc/algorithms')
    body = resp.json()
    assert body.get('simulated') is True, (
        'the algorithms endpoint does not declare itself simulated, so no '
        'caller can tell this is not real cryptography'
    )
    assert 'SIMULATED' in str(body.get('warning', '')).upper()


# ══ OpenRouter key verification ═══════════════════════════════════════════════

def test_the_model_count_is_never_invented(app):
    """`${tj.models_count || 180}+ models ready (Claude 3.5 Sonnet, GPT-4o, …)`.

    When the backend cannot reach the catalogue it returns `models_count: 0`,
    and `0 || 180` is 180 — so the UI invented a count nobody measured and
    named three specific models it had not confirmed the key can reach. The
    backend goes to real trouble here, verifying against `/api/v1/auth/key`
    precisely because the public `/models` endpoint returns 200 for any
    garbage; the frontend was undoing that.
    """
    src = app.evaluate("""async () => {
        const r = await fetch('/static/js/01-app-core.js');
        const t = await r.text();
        // Strip comments so an assertion cannot match the text of its own fix.
        return t.split('\\n').filter(l => !l.trim().startsWith('//')).join('\\n');
    }""")
    assert 'models_count || 180' not in src, (
        'the hardcoded 180-model fallback is back'
    )
