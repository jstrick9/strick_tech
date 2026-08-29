"""The Ollama detect endpoint existed for three commits and NOTHING CALLED IT.

Reported: "The Ollama localhost did not auto connect."

The user's diagnostic showed 17 local models visible to their machine. The
backend route GET /api/onboarding/detect-local-models had shipped days earlier
and worked correctly. But no frontend code ever invoked it: detection ran only
inside POST /api/onboarding/quick-setup, reachable from one button buried in
Settings. So the app launched, selected nothing, and the user reasonably
concluded auto-connect was broken.

This is the "capability present but never triggered" class from
docs/BUG-SWEEP-PLAN.md -- the most expensive kind, because every individual
piece passes its own test.

CONTRACT (chosen by the user: "probe at startup, auto-select if found, silent
if absent"), all three verified in Chromium against a live server:

  absent Ollama   -> nothing. No toast, no console error, no state change.
                     Verified: toasts [], pageerrors [], console noise [].
  present         -> models appended to #ollama-model-optgroup as
                     "ollama:<name>", and if the user has NOT chosen a model,
                     the suggested one is selected and persisted.
                     Verified: currentModel == "ollama:llama3.1:8b".
  user has chosen -> never overridden.
                     Verified: stored "gpt4o" survived a reload with 17 models
                     present.

TWO BUGS IN MY OWN FIRST VERSION, both found by looking at the live DOM rather
than trusting the diff -- neither would have been caught by reading the code:

  1. Auto-select could NEVER fire. I treated a non-empty `sel.value` as "the
     user already chose". But index.html ships <option value="claude"> first,
     so the browser reports value="claude" before anyone touches anything.
     Measured: probe ran, 17 models found, currentModel stayed null. The
     authority for "the user chose" is the persisted preference, not the
     rendered default.

  2. Duplicate options in the wrong format. I appended bare
     <option value="llama3.1:8b"> onto the <select>, outside the
     "Local (Ollama)" optgroup, in a format selectChatModel() does not
     understand -- it strips an "ollama:" prefix that would not have been
     there. Then, after scoping to the right optgroup, one duplicate remained
     because syncOpenWebUIConnections() fills the SAME group from
     /api/agents/models and can land either side of this probe. De-duping now
     considers the whole <select>.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "frontend" / "js" / "01-app-core.js"
INDEX = REPO / "frontend" / "index.html"


def _src() -> str:
    return CORE.read_text(encoding="utf-8")


def _probe_body() -> str:
    s = _src()
    i = s.index("window.autoDetectLocalModels = async function")
    return s[i : s.index("\n};\n", i)]


def test_the_probe_exists_and_is_exported() -> None:
    assert "window.autoDetectLocalModels" in _src(), (
        "no startup probe -- the detect endpoint would again have no caller"
    )


def test_the_probe_is_actually_invoked_at_startup() -> None:
    """THE WHOLE BUG. The endpoint worked; nothing called it. A defined-but-
    uncalled function reproduces the defect exactly."""
    s = _src()
    calls = [
        m for m in re.finditer(r"window\.autoDetectLocalModels\s*\(\s*\)", s)
    ]
    assert calls, (
        "autoDetectLocalModels is defined but never called. This is precisely "
        "the reported bug: the capability exists and never runs."
    )


def test_the_probe_calls_the_detect_endpoint() -> None:
    assert "/api/onboarding/detect-local-models" in _probe_body(), (
        "the probe must use the standalone detect route, not quick-setup"
    )


def test_absent_ollama_produces_no_user_visible_noise() -> None:
    """Someone who has never heard of Ollama must never see a message about
    it. The early return on available !== true is what guarantees that."""
    body = _probe_body()
    assert "available !== true" in body, (
        "the probe must bail out when Ollama is absent, before any UI work"
    )
    bail = body.index("available !== true")
    toast = body.find("toast")
    assert toast > bail, "a toast fires before the absent-Ollama guard"


def test_an_explicit_user_choice_is_never_overridden() -> None:
    body = _probe_body()
    assert "agentic_os_chat_model" in body, "must consult the persisted choice"
    assert re.search(r"if\s*\(\s*stored\s*\|\|\s*S\.currentModel\s*\)\s*return", body), (
        "the probe must return early when the user has already chosen a model"
    )


def test_the_default_dropdown_value_is_not_mistaken_for_a_user_choice() -> None:
    """REGRESSION GUARD for my bug #1.

    index.html renders <option value="claude"> first, so sel.value is a
    non-empty string on a completely fresh launch. Using it as the "has the
    user chosen?" signal makes auto-select dead code."""
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<select[^>]*id="chat-model-select".*?</select>', html, re.S)
    assert m, "chat-model-select not found in index.html"
    first = re.search(r'<option value="([^"]+)"', m.group(0))
    assert first, "the select has no options"
    assert first.group(1) == "claude", (
        "this guard assumes the shipped default; update it if the markup changed"
    )
    body = _probe_body()
    guard = re.search(r"if\s*\(([^)]*)\)\s*return;\s*\n\s*(?:var|const|let)\s+pick", body)
    assert guard, "could not locate the auto-select guard"
    assert "sel.value" not in guard.group(1), (
        "the guard consults sel.value, which is 'claude' on a fresh launch -- "
        "auto-select can never fire. Consult the persisted preference instead."
    )


def test_models_are_added_in_the_format_the_app_understands() -> None:
    """REGRESSION GUARD for my bug #2. selectChatModel() strips an 'ollama:'
    prefix, so options must carry it."""
    body = _probe_body()
    assert "'ollama:' + models[i]" in body or '"ollama:" + models[i]' in body, (
        "options must use the ollama:<name> value format"
    )
    assert "ollama-model-optgroup" in body, (
        "options belong in the Local (Ollama) optgroup, not loose on the select"
    )


def test_deduplication_considers_the_whole_select() -> None:
    """syncOpenWebUIConnections() fills the same optgroup from a different
    endpoint and can land either side of this probe."""
    body = _probe_body()
    seen = re.search(r"new Set\(\s*Array\.from\((\w+)\.options", body)
    assert seen, "no de-duplication set found"
    assert seen.group(1) == "sel", (
        "de-duping against the optgroup alone leaves duplicates when "
        "syncOpenWebUIConnections wins the race; compare against the select"
    )


def test_the_probe_runs_at_most_once() -> None:
    body = _probe_body()
    assert "__localModelProbeDone" in body, (
        "without a guard the probe can double-fire and double-append options"
    )


def test_the_probe_never_throws() -> None:
    """A failed probe must not break startup for everyone else."""
    body = _probe_body()
    assert body.count("try {") >= 1 and "catch" in body


def test_core_js_is_syntactically_valid() -> None:
    """A SyntaxError here takes down the entire application."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node not available")
    proc = subprocess.run([node, "--check", str(CORE)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
