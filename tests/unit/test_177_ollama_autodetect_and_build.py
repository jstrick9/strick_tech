"""Ollama auto-detection, and the build gate that stops shipping stale JS.

TWO REPORTED BUGS FROM A REAL DESKTOP BUILD.

────────────────────────────────────────────────────────────────────────────
BUG: "The Ollama localhost did not auto connect."

Detection code existed, but only inside POST /api/onboarding/quick-setup,
which the frontend calls from a button in Settings. Nothing ran at launch, so
a local Ollama with models installed stayed invisible until the user went
looking for it. The pre-existing probe also hardcoded 127.0.0.1:11434 and
ignored OLLAMA_BASE_URL, so a non-default host was undetectable however the
app was configured.

────────────────────────────────────────────────────────────────────────────
BUG: "I keep getting a popup for the Pro Features which should be disabled."

The backend is correctly unlocked -- measured live: tier=enterprise,
unlocked=true, AGENTIC_ENFORCE_LICENSE unset. But backend/app.py does not
serve frontend/index.html as written; it REWRITES it to load content-hashed
bundles from frontend/dist. build_macos_desktop.sh never regenerated that
bundle, so a pull that changed JS shipped the OLD JS -- paywall guards
included -- while every source file on disk looked current.

Silent, and maximally confusing, because nothing on disk is wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build_macos_desktop.sh'


# ── model suggestion ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(('installed', 'expected'), [
    ([], ''),
    (['llama3.1:8b'], 'llama3.1:8b'),
    (['mistral:7b', 'llama3.2:3b'], 'llama3.2:3b'),
    (['codellama:7b'], 'codellama:7b'),
])
def test_suggests_a_sensible_default(installed, expected):
    from backend.routers.onboarding import _suggest_local_model

    assert _suggest_local_model(installed) == expected


def test_embedding_only_installs_get_no_default():
    """An embedding model as the chat default fails on the first message.

    Returning nothing is better: the user sees "no model selected", which is
    actionable, instead of an opaque runtime error from the provider.
    """
    from backend.routers.onboarding import _suggest_local_model

    assert _suggest_local_model(['nomic-embed-text:latest']) == ''
    assert _suggest_local_model(['bge-m3', 'all-minilm']) == ''


def test_a_general_model_outranks_code_and_embedding_models():
    from backend.routers.onboarding import _suggest_local_model

    got = _suggest_local_model(['nomic-embed-text', 'codellama:7b', 'llama3.1:8b'])
    assert got == 'llama3.1:8b'


# ── the endpoint ─────────────────────────────────────────────────────────────
class TestDetectEndpoint:
    def test_it_exists(self, client):
        """It did not. That is the whole bug: nothing to call at launch."""
        assert client.get('/api/onboarding/detect-local-models').status_code == 200

    def test_absent_ollama_is_not_an_error(self, client):
        """Most users have no Ollama. That is a normal state, not a failure."""
        body = client.get('/api/onboarding/detect-local-models').json()
        assert body['ok'] is True
        assert 'available' in body
        assert isinstance(body['models'], list)

    def test_it_reports_the_base_url_it_probed(self, client):
        """Otherwise 'not detected' is unactionable -- probed WHERE?"""
        body = client.get('/api/onboarding/detect-local-models').json()
        assert body['base_url'].startswith('http')

    def test_it_honours_OLLAMA_BASE_URL(self, client, monkeypatch):
        """The pre-existing probe hardcoded 127.0.0.1:11434."""
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://example.invalid:9999')
        body = client.get('/api/onboarding/detect-local-models').json()
        assert body['base_url'] == 'http://example.invalid:9999'
        assert body['available'] is False

    def test_an_openai_compatible_url_is_normalised(self, client, monkeypatch):
        """People paste the /v1 form from other tools' docs; /api/tags is not there."""
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1')
        body = client.get('/api/onboarding/detect-local-models').json()
        assert body['base_url'] == 'http://127.0.0.1:11434'

    def test_it_never_raises_on_an_unreachable_host(self, client, monkeypatch):
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://127.0.0.1:1')
        r = client.get('/api/onboarding/detect-local-models')
        assert r.status_code == 200
        assert r.json()['available'] is False


# ── the build gate ───────────────────────────────────────────────────────────
def test_the_build_script_rebuilds_the_frontend_bundle():
    """Without this the packaged app ships whatever dist was lying around.

    Asserts the command is REACHABLE, not merely present. An earlier version
    searched the whole file for the substring, so wrapping the call in
    `if false; then` still passed -- the revert proof caught it.
    """
    src = BUILD.read_text(encoding='utf-8')
    assert re.search(r'if\s*!\s*python3 scripts/build_bundle\.py\s*;\s*then', src), (
        'build_macos_desktop.sh must actually RUN scripts/build_bundle.py; '
        'without it the app serves stale JavaScript -- the cause of the Pro '
        'popup on an unlocked build')


def test_the_bundle_step_runs_before_packaging():
    """A rebuild after `cargo tauri build` packages the old bundle."""
    src = BUILD.read_text(encoding='utf-8')
    bundle_at = src.index('scripts/build_bundle.py')
    tauri_at = src.index('cargo tauri build')
    assert bundle_at < tauri_at, 'the bundle must be rebuilt BEFORE tauri packages it'


def test_a_failed_bundle_build_aborts_the_package():
    """Warning and continuing ships the broken artefact anyway."""
    src = BUILD.read_text(encoding='utf-8')
    block = src[src.index('Rebuilding the frontend bundle'):src.index('cargo tauri build')]
    # Each of the three gates must end in a hard exit. Counting them stops a
    # single `exit 1` elsewhere in the block satisfying the assertion.
    assert block.count('exit 1') >= 3, (
        f'expected 3 hard gates (build, --check, canary), found '
        f'{block.count("exit 1")}')
    assert 'warning' not in block.lower(), 'a bundle failure must abort, not warn'


def test_the_build_verifies_the_bundle_matches_source():
    """Building is not enough: --check catches a build that silently no-ops."""
    src = BUILD.read_text(encoding='utf-8')
    assert '--check' in src


def test_the_build_refuses_a_pre_unlock_checkout():
    """Guards the exact reported symptom on an old clone.

    Asserts the grep is live, not just that the string appears somewhere --
    `if false; then grep ...` would satisfy a substring check.
    """
    src = BUILD.read_text(encoding='utf-8')
    assert re.search(r'if\s*!\s*grep -q "CORE MODULES"', src), (
        'no live canary for a checkout that predates the licence unlock')


def test_the_build_script_is_valid_bash():
    import subprocess

    r = subprocess.run(['bash', '-n', str(BUILD)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:400]


# ── the diagnostic ───────────────────────────────────────────────────────────
def test_the_diagnostic_explains_a_stale_bundle():
    """It must name the cause AND the fix, or it is just more output."""
    src = (ROOT / 'scripts' / 'diagnose_desktop.py').read_text(encoding='utf-8')
    assert 'build_bundle.py' in src
    assert 'stale' in src.lower()


def test_the_diagnostic_distinguishes_unreachable_from_absent():
    """An empty body made every canary read ABSENT, which I misread as stale."""
    src = (ROOT / 'scripts' / 'diagnose_desktop.py').read_text(encoding='utf-8')
    assert re.search(r'if not html', src), (
        'the diagnostic must not report canaries when it got no HTML at all')
