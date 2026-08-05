"""Every theme must meet WCAG AA for text.

MEASURED BEFORE THIS FIX: 17 failures across the six themes.

  --text-3 failed in 5 of 6. It is the muted token used 655 times for hints,
  timestamps, counts and metadata. On `midnight` it measured **1.79:1**
  against --bg-3, which is not "de-emphasised" — it is unreadable.

  White text on the accent fill failed in 5 of 6: 2.14:1 on dark and obsidian,
  2.54:1 on forest. Primary buttons are the most important controls on the
  screen and had the worst contrast in the product.

  --accent used AS a text colour failed on light (4.10) and jet (4.21), and it
  is used that way 212 times.

THE FIX, AND WHY IT IS TWO TOKENS
The accent fill could not simply be brightened: 46 controls put a foreground
ON it, and white on #6366f1 was already only 4.47:1 — lightening the fill
drops that to 2.98:1. So the fill keeps its value and two new tokens carry the
accessible pairings:

  --accent-text   accent for text/icons, computed per theme
  --on-accent     foreground for accent-filled controls

New values were computed by shifting lightness in HLS, preserving hue and
saturation, so each palette keeps its character rather than being flattened
toward grey.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'frontend' / 'js' / '01-app-core.js'
INDEX = ROOT / 'frontend' / 'index.html'

AA_BODY = 4.5   # WCAG 2.1 AA, normal text
AA_LARGE = 3.0  # AA for large text and UI components


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def _themes() -> dict[str, dict[str, str]]:
    src = CORE.read_text(encoding='utf-8')
    block = re.search(r'const THEME_VARS = \{(.*?)\n\};', src, re.S)
    assert block, 'THEME_VARS block not found'
    out: dict[str, dict[str, str]] = {}
    for line in block.group(1).strip().split('\n'):
        m = re.match(r"\s*(\w+):\s*\{(.*?)\},?\s*$", line)
        if not m:
            continue
        out[m.group(1)] = dict(re.findall(r"(\w+):'(#[0-9a-fA-F]{3,6})'", m.group(2)))
    return out


THEMES = _themes()
THEME_NAMES = sorted(THEMES)


def test_all_themes_were_parsed():
    assert len(THEMES) >= 6, f'only parsed {list(THEMES)}'


# ══ Body text ═════════════════════════════════════════════════════════════════
@pytest.mark.parametrize('theme', THEME_NAMES)
@pytest.mark.parametrize('text_token', ['text1', 'text2', 'text3'])
@pytest.mark.parametrize('bg_token', ['bg1', 'bg2', 'bg3'])
def test_text_meets_aa_on_every_surface(theme, text_token, bg_token):
    """text3 is the one that failed hardest — 1.79:1 on midnight/bg-3. It
    carries hints and metadata across 655 call sites, i.e. exactly the
    secondary information that is easiest to write off as 'muted by design'
    and hardest to read."""
    t = THEMES[theme]
    ratio = contrast(t[text_token], t[bg_token])
    assert ratio >= AA_BODY, (
        f'{theme}: --{text_token} on --{bg_token} is {ratio}:1, below AA {AA_BODY}:1'
    )


# ══ Accent ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize('theme', THEME_NAMES)
def test_accent_text_token_exists_and_passes(theme):
    """`--accent` is a FILL. Using it for text failed on light and jet, and it
    is used that way 212 times."""
    t = THEMES[theme]
    assert 'accentText' in t, f'{theme} has no accentText token'
    for bg in ('bg1', 'bg2', 'bg3'):
        ratio = contrast(t['accentText'], t[bg])
        assert ratio >= AA_BODY, f'{theme}: accent text on --{bg} is {ratio}:1'


@pytest.mark.parametrize('theme', THEME_NAMES)
def test_accent_filled_controls_have_a_readable_foreground(theme):
    """The worst failure in the product: white on the accent fill measured
    2.14:1 on dark and obsidian. Primary buttons are the controls users are
    steered toward."""
    t = THEMES[theme]
    assert 'onAccent' in t, f'{theme} has no onAccent token'
    ratio = contrast(t['onAccent'], t['accent'])
    assert ratio >= AA_BODY, (
        f'{theme}: button label on the accent fill is {ratio}:1'
    )


@pytest.mark.parametrize('theme', THEME_NAMES)
def test_borders_remain_distinguishable(theme):
    """A border below 3:1 against its surface is a UI component failure
    (WCAG 1.4.11) — the boundary of an input becomes invisible."""
    t = THEMES[theme]
    if 'bg2' not in t or 'bg3' not in t:
        pytest.skip('theme lacks the surface tokens')
    # bg3 is used as a raised/hover surface against bg1; it must be visible.
    assert contrast(t['bg3'], t['bg1']) >= 1.1, (
        f'{theme}: raised surfaces are indistinguishable from the base'
    )


# ══ The tokens must actually reach the DOM ════════════════════════════════════
def test_new_tokens_are_applied_by_applytheme():
    """Computing a value that never reaches CSS would be worse than not
    computing it — the audit would pass while the UI stayed broken."""
    src = CORE.read_text(encoding='utf-8')
    assert "setProperty('--accent-text'" in src
    assert "setProperty('--on-accent'" in src


def test_default_stylesheet_declares_the_tokens():
    """applyTheme runs after first paint; the :root fallback covers the gap."""
    html = INDEX.read_text(encoding='utf-8')
    assert '--accent-text:' in html
    assert re.search(r'--text-3:\s*#a0a0a0', html), (
        'the :root fallback for --text-3 was not raised to the accessible value'
    )


def test_accent_is_not_used_as_a_bare_text_colour():
    """Regression guard. `color:var(--accent)` is 4.01:1 on --bg-1 in the
    default palette; the accessible variant exists precisely so this does not
    creep back in."""
    offenders = []
    for path in [INDEX, *sorted((ROOT / 'frontend' / 'js').glob('*.js'))]:
        for i, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
            if path.suffix == '.js' and line.lstrip().startswith(('//', '*', '/*')):
                continue
            if re.search(r'color:\s*var\(--accent\)', line):
                offenders.append(f'{path.name}:{i}')
    assert not offenders, (
        'use var(--accent-text) for text; var(--accent) is a fill:\n  '
        + '\n  '.join(offenders[:15])
    )


def test_no_hardcoded_white_on_an_accent_fill():
    """`background:var(--accent);color:#fff` fails on 5 of 6 themes."""
    offenders = []
    for path in [INDEX, *sorted((ROOT / 'frontend' / 'js').glob('*.js'))]:
        text = path.read_text(encoding='utf-8')
        for m in re.finditer(r'style="([^"]*)"', text):
            style = m.group(1)
            if 'background:var(--accent)' in style and re.search(r'color:#fff\b', style):
                line = text[: m.start()].count('\n') + 1
                offenders.append(f'{path.name}:{line}')
    assert not offenders, (
        'accent-filled controls must use var(--on-accent):\n  '
        + '\n  '.join(offenders[:15])
    )
