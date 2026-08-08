"""What a brand-new user sees on a completely empty account.

WHY THIS DIMENSION HAD NEVER BEEN MEASURED
──────────────────────────────────────────
All eighteen existing audits run against a database with 250 goals, 200 tasks,
agents and specs in it. That was right for measuring volume, truncation and
layout. It also means **every audit in this repo had only ever seen the
application in a state no new user is ever in.**

An empty account is the first thing every single user experiences. It fails
differently from every other state: nothing throws, nothing 500s, and the
screen is simply blank.

THE CRASH: A GUARD THAT CAUSED THE BUG IT WAS GUARDING AGAINST
──────────────────────────────────────────────────────────────
`renderImageGen()` died on every empty account with:

    Couldn't open the image generator. The response from the server was not
    what the app expected. (Cannot read properties of undefined (reading
    'length'))

An earlier defensive fix had normalised the gallery response to a bare
**array** to stop `gallery.map is not a function`. But four call sites below it
read `gallery.images` and `gallery.count` — the OBJECT shape. So the guard
turned a hypothetical crash into a real one:

    gallery = []            ->  gallery.images === undefined
    gallery.images.length   ->  TypeError, pane dead

Invisible against seeded data, fired for **every new user on their first visit
to that pane**. A guard that converts a shape the callers do not accept is not
a guard. It now normalises to `{images, count}`, the shape actually consumed.

THE UX DEFECT: FOUR PANES THAT NEVER SAY WHAT THEY ARE FOR
──────────────────────────────────────────────────────────
`kanban`, `codesearch`, `websearch` and `multitab` each offered a working
control and no explanation. A search box with no context is a prompt to guess.
Each now has a short empty state: what the feature does, and what to try first.

Kanban is deliberately asymmetric — only the FIRST column carries the pitch.
Four columns each repeating it is noise, not help.

THE PROBE OVER-REPORTED 23 FINDINGS AND MOST WERE WRONG
───────────────────────────────────────────────────────
Triage before fixing cut 31 raw findings to 4 real ones:

  * `BROKEN` matched any /error|failed/ anywhere, so a dashboard tile reading
    "ERRORS 0" or "Failed Actions 0" — a product working correctly and saying
    so — was reported as broken. Five of six BROKEN-EMPTY findings were metric
    labels or feature copy.
  * `ACTION` matched only creation verbs in a button label, so panes whose
    entry point is a TEXT BOX (websearch, codesearch, swarm, multitab) were
    declared dead ends. **For a search pane the input is the entry point.**
  * Read-only dashboards (system, health, monitor) have nothing to create and
    are honest when empty.

Had I trusted the first run I would have rewritten a dozen working screens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
AUDIT = REPO / 'scripts' / 'audit'
AUDIT_SRC = (AUDIT / 'first_run.py').read_text(encoding='utf-8')


def _strip_js_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining the fix."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


IMAGEGEN = _strip_js_comments((JS / '15-image-generation.js').read_text(encoding='utf-8'))
KANBAN = _strip_js_comments((JS / '28-kanban.js').read_text(encoding='utf-8'))
CODESEARCH = _strip_js_comments((JS / '14-prompt-library.js').read_text(encoding='utf-8'))
WEBSEARCH = _strip_js_comments((JS / '44-websearch.js').read_text(encoding='utf-8'))
FEATURES_A = _strip_js_comments((JS / '03-features-a.js').read_text(encoding='utf-8'))


# ──────────────────────────────────────────────────────────────────────
#  The crash
# ──────────────────────────────────────────────────────────────────────
def test_gallery_is_normalised_to_the_shape_its_callers_read():
    """The guard produced a bare array while four call sites read
    `.images` / `.count`, so `gallery.images.length` threw on every empty
    account."""
    assert 'const gallery = {' in IMAGEGEN, (
        'gallery must be normalised to an object, not an array')
    block = IMAGEGEN[IMAGEGEN.index('const gallery = {'):]
    block = block[:block.index('};') + 2]
    assert 'images:' in block
    assert 'count:' in block


def test_gallery_images_is_always_an_array():
    """Defends the inner value too: `{images: undefined}` would still throw on
    `.length`, just one line later."""
    block = IMAGEGEN[IMAGEGEN.index('const gallery = {'):]
    block = block[:block.index('};') + 2]
    assert 'Array.isArray' in block


def test_gallery_count_survives_a_missing_count_field():
    """An API that returns images without a count must not render
    "(undefined images)"."""
    block = IMAGEGEN[IMAGEGEN.index('const gallery = {'):]
    block = block[:block.index('};') + 2]
    assert '.length' in block, 'count must fall back to the array length'


def test_the_object_call_sites_still_exist():
    """If someone later rewrites the call sites to use a bare array, the
    normalisation above becomes wrong rather than merely redundant. This test
    exists so that change is a deliberate one."""
    assert 'gallery.images' in IMAGEGEN
    assert 'gallery.count' in IMAGEGEN


# ──────────────────────────────────────────────────────────────────────
#  Empty states that explain the feature
# ──────────────────────────────────────────────────────────────────────
def test_kanban_empty_board_explains_itself():
    assert 'kanban-empty-col--intro' in KANBAN
    assert 'boardIsEmpty' in KANBAN


def test_only_the_first_kanban_column_carries_the_pitch():
    """Four columns each repeating the explanation is noise, not help."""
    assert 'isFirstColumn' in KANBAN
    assert 'isFirstColumn && boardIsEmpty' in KANBAN


def test_kanban_intro_offers_a_working_create_action():
    """An explanation with no way to act on it is still a dead end. The action
    must call a function that exists."""
    intro = KANBAN[KANBAN.index('kanban-empty-col--intro'):]
    intro = intro[:intro.index('`)')]
    assert 'kanbanOpenCreateModal' in intro
    assert 'kanbanOpenCreateModal' in KANBAN.replace(intro, ''), (
        'the create modal function must actually be defined/used elsewhere')


def test_codesearch_explains_what_it_searches():
    assert 'pane-empty-intro' in CODESEARCH
    assert 'Search every file' in CODESEARCH


def test_websearch_explains_how_it_differs_from_chat():
    """The whole point of the pane is that it cites sources; a user cannot
    guess that from an input box."""
    assert 'pane-empty-intro' in WEBSEARCH
    assert 'cit' in WEBSEARCH.lower()


def test_multitab_explains_the_grid():
    assert 'mt-hint' in FEATURES_A
    assert 'Grid' in FEATURES_A


def test_the_shared_empty_state_has_styles():
    """An unstyled block inherits whatever the pane happens to set, which for
    several panes is centred 40px grey — legible by luck."""
    for selector in ('.pane-empty-intro', '.pane-empty-intro__title',
                     '.pane-empty-intro__body', '.mt-hint'):
        assert selector in CSS, f'{selector} is unstyled'


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_the_probe_refuses_to_run_against_seeded_data():
    """An audit pointed at the wrong state reports clean for the wrong
    reason -- the exact failure that made the concurrency audit pass while
    every one of its writes was being rejected."""
    assert '_seeded' in AUDIT_SRC
    assert 'refuses to report a result' in AUDIT_SRC


def test_the_probe_does_not_treat_a_metric_label_as_a_failure():
    """"ERRORS 0" is a product working correctly and saying so. Five of six
    BROKEN-EMPTY findings were metric labels or feature copy."""
    assert '_broken_line' in AUDIT_SRC
    assert 'metric' in AUDIT_SRC.lower()


def test_the_probe_counts_a_text_input_as_an_entry_point():
    """For a search or prompt pane THE TEXT BOX IS the entry point. A
    verb-only button check declared the most usable panes broken."""
    assert 'has_input' in AUDIT_SRC
    assert 'textarea' in AUDIT_SRC


def test_the_probe_allows_read_only_dashboards_to_have_no_create_action():
    assert 'READ_ONLY_OK' in AUDIT_SRC


def test_the_probe_keeps_the_onboarding_modal():
    """Removing first-run UI -- as every other audit here does -- measures a
    state the new user never sees."""
    assert 'onboarding' in AUDIT_SRC
    assert 'the way a user dismisses it' in AUDIT_SRC or 'close.click' in AUDIT_SRC


def test_the_audit_is_registered_and_ratcheted_separately():
    """In the shared parametrize list it would pass on every seeded run
    without measuring anything."""
    assert 'first_run' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'test_first_run_audit_has_not_regressed' in ratchet
    assert "('first_run', 'first-run-experience')" not in ratchet, (
        'must not sit in the shared list; it needs an empty server')
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('first-run-experience') == 0
