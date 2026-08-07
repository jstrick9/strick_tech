"""Error copy explains; touch targets are reachable.

TWO FINDINGS, BOTH MEASURED IN A REAL BROWSER
─────────────────────────────────────────────

**1. Panes showed internals where an explanation belongs.** Forcing every
`/api/` call to return HTTP 500 and walking all 68 panes, twelve of them
rendered developer text into the pane body:

    templates   Failed to load templates: Templates API: HTTP 500
    galaxy      Load failed — HTTP 500
    obsidian    Error loading Obsidian status: HTTP 500
    control     runs.filter is not a function
    testgen     files.filter is not a function
    profiler    DB size: undefined KB

"HTTP 500" tells a developer where to look and everyone else nothing.
`runs.filter is not a function` is not a message, it is a stack frame. And two
of these were real crashes, not just wording: the pane parsed an error body as
if it were a list.

**2. The batch-32 touch fix was weaker than reported.** It used an allow-list
of class names, so it only covered controls visible on the landing pane.
Auditing all 68 panes at 390px found **41 distinct undersized control types**
it missed, including `#chat-send` (36x36, the primary action of the product)
and 4x4 toggles in Hooks and Steering.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
INDEX = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')


def _strip_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining it."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


COPY = _strip_comments((JS / '00-error-copy.js').read_text(encoding='utf-8'))
CSS_CODE = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)


# ──────────────────────────────────────────────────────────────────────
#  1. Two real crashes, not wording problems
# ──────────────────────────────────────────────────────────────────────
def test_control_tower_survives_a_non_list_response():
    """`runs.filter is not a function` was rendered into the pane.

    A failed request returns an error OBJECT; calling an array method on it
    throws, and the raw TypeError became the user's explanation.
    """
    code = _strip_comments((JS / '31-control-tower.js').read_text(encoding='utf-8'))
    assert 'Array.isArray(runs)' in code, (
        'the response must be coerced to an array before .filter()')
    assert re.search(r'if\s*\(\s*!sr\.ok', code), (
        'a failed request should be detected rather than parsed as data')


def test_test_generator_survives_a_non_list_response():
    code = _strip_comments((JS / '34-test-generator.js').read_text(encoding='utf-8'))
    assert 'Array.isArray(files)' in code
    assert re.search(r'if\s*\(\s*!fr\.ok', code)


def test_profiler_does_not_print_undefined():
    """"DB size: undefined KB" is worse than saying nothing."""
    code = _strip_comments((JS / '03-features-a.js').read_text(encoding='utf-8'))
    assert 'DB size: ${db.db_size_kb} KB' not in code
    assert 'Number.isFinite(Number(db.db_size_kb))' in code


# ──────────────────────────────────────────────────────────────────────
#  2. The error-copy helper
# ──────────────────────────────────────────────────────────────────────
def test_helper_is_loaded_before_the_modules_that_use_it():
    assert '00-error-copy.js' in INDEX
    assert INDEX.index('00-error-copy.js') < INDEX.index('01-app-core.js')


def test_status_codes_are_translated_to_consequences():
    """A status code is a protocol detail; the user needs the consequence."""
    for code in ('401', '403', '404', '429', '500', '503'):
        assert code in COPY, f'HTTP {code} has no human translation'
    assert 'sign in again' in COPY
    assert 'do not have permission' in COPY
    assert 'wait a moment and try again' in COPY


def test_runtime_noise_is_not_shown_as_an_explanation():
    """`is not a function` should never be the sentence a user reads."""
    assert 'RUNTIME_NOISE' in COPY
    assert 'is not a function' in COPY, 'the pattern must be recognised'
    assert 'not what the app expected' in COPY, (
        'runtime noise needs a human replacement, not just suppression')


def test_technical_detail_is_preserved_but_demoted():
    """Support still needs the detail; the user should not lead with it."""
    assert "opts.detail !== false" in COPY, 'detail must be retained by default'
    assert "' (' + shown + ')'" in COPY, (
        'technical detail belongs in parentheses at the end, not the headline')


def test_a_bare_status_is_not_repeated_after_being_explained():
    """"The server ran into a problem. (500)" is redundant and noisy."""
    assert re.search(r"\^\(HTTP\\s\*\)\?\\d\{3\}\$", COPY), (
        'a detail string that is only a status code should be dropped')


def test_reassurance_is_available_for_data_loading_failures():
    """The question a user actually has is "did I lose my work?"."""
    assert 'Nothing was lost.' in COPY
    assert 'dataSafe' in COPY


def test_panes_that_showed_jargon_now_use_the_helper():
    """Pin the specific panes the live probe caught."""
    cases = {
        '21-template-gallery.js': 'load your templates',
        '27-galaxy.js': 'load the memory graph',
        '20-obsidian.js': 'check your Obsidian vault',
        '36-dashboard.js': 'load your analytics',
        '14-prompt-library.js': 'load your prompts',
        '08-replay-collab.js': 'load your runs',
        '15-image-generation.js': 'open the image generator',
        '03-features-b.js': 'load your specs',
    }
    for filename, action in cases.items():
        code = _strip_comments((JS / filename).read_text(encoding='utf-8'))
        assert 'humanError(' in code, f'{filename} still writes its own copy'
        assert action in code, f'{filename}: expected the action phrase {action!r}'


def test_no_pane_leads_with_a_raw_http_status():
    """The headline sentence must not be a status code.

    Detail in trailing parentheses is fine and deliberate; `HTTP 500` as the
    message itself is not.
    """
    offenders = []
    for path in sorted(JS.glob('*.js')):
        code = _strip_comments(path.read_text(encoding='utf-8'))
        # "...: HTTP ${r.status}" or "(HTTP ' + r.status + ')" used as the
        # whole user-visible message, i.e. not routed through humanError.
        for m in re.finditer(r'(Failed to load|Error loading|Load failed)[^\n]{0,60}HTTP', code):
            offenders.append(f'{path.name}: {m.group(0)[:60]}')
    assert not offenders, f'panes leading with a status code: {offenders}'


# ──────────────────────────────────────────────────────────────────────
#  3. Touch targets, structurally
# ──────────────────────────────────────────────────────────────────────
def test_touch_sizing_is_structural_not_an_allow_list():
    """The batch-32 rule listed class names and missed 41 control types.

    An allow-list also guarantees the next control added is undersized again.
    """
    block = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
    # The element selectors must be present, not just class names.
    for selector in ('button,', 'a[href],', '[role="button"],', 'select,'):
        assert selector in block, f'missing structural selector {selector!r}'


def test_both_dimensions_are_covered():
    """A first pass set only min-height, leaving 20 types too NARROW.

    A 12px-wide "+" button that is 44px tall is still unhittable.
    """
    block = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
    assert 'min-height: 44px' in block
    assert 'min-width: 44px' in block


def test_inline_links_are_excluded_from_block_sizing():
    """A 44px min on a link inside a sentence would break paragraph flow."""
    block = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
    assert 'p a[href]' in block
    assert 'display: inline' in block


def test_there_is_a_documented_escape_hatch():
    """Structural rules need an opt-out, or someone reverts the whole rule."""
    block = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
    assert '.tight-target' in block
    assert 'min-height: 0' in block


def test_desktop_is_untouched():
    """The density was deliberately tuned for a mouse.

    Everything must sit inside the coarse-pointer query -- verified live:
    `matchMedia('(pointer: coarse)')` is false at 1440px and the notification
    bell is still 32x32 there.
    """
    block = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
    depth, end = 0, None
    for i, ch in enumerate(block):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end is not None, 'unbalanced media query'
    assert 'min-height: 44px' not in block[end:], (
        'touch sizing leaked outside the pointer:coarse query')
