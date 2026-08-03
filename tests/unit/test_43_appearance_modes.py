"""Appearance preferences must be accessible, deterministic, and OS-aware."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
ONBOARDING = (ROOT / 'backend' / 'routers' / 'onboarding.py').read_text(encoding='utf-8')


def test_dark_is_the_product_default():
    # The product default is dark: commit "fix: default theme to dark mode for
    # HTML/localhost version" moved the frontend boot default to dark, but the
    # backend DEFAULT_PREFS and this contract were left asserting light.
    assert "'theme': 'dark'" in ONBOARDING
    assert "localStorage.getItem('agentic_os_theme') || 'dark'" in INDEX


def test_light_dark_and_auto_choices_are_exposed():
    assert "applyTheme('light')" in INDEX
    assert "applyTheme('dark')" in INDEX
    assert "applyTheme('auto')" in INDEX
    assert 'Auto (Device)' in INDEX


def test_auto_resolves_to_os_palette_and_reacts_to_change():
    assert "const followsSystem = preference === 'auto';" in CORE
    assert "prefers-color-scheme: dark" in CORE
    assert "refreshAutoAppearance" in CORE
    assert "data-theme-preference" in CORE
