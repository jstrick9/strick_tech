"""Guards on the inline-style -> utility-class migration.

Context: CSP phase 3 measured 4,783 inline `style=` attributes, and enforcing a
strict `style-src` is blocked on that number coming down.
scripts/migrate_inline_styles.py converts the repeated, fully static ones to
utility classes. These tests pin the two properties that make it safe.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, 'scripts', 'migrate_inline_styles.py')
sys.path.insert(0, os.path.join(REPO, 'scripts'))


def _load():
    import importlib
    mod = importlib.import_module('migrate_inline_styles')
    importlib.reload(mod)
    return mod


def test_properties_javascript_reads_back_are_never_migrated():
    """The bug that made this guard necessary.

    The first version migrated `style="display:none"` to a class. That looks
    like styling but it is STATE -- `toggleSidebarGroup()` does
    `content.style.display === 'none'`, and `element.style` exposes only the
    inline attribute, never a class. The read always returned '' afterwards,
    so collapsed sidebar groups stopped expanding. Measured against a
    computed-style baseline: 549 properties changed across 160 elements.
    """
    m = _load()
    unsafe = m.runtime_read_properties()
    assert 'display' in unsafe, (
        'display is read back by toggleSidebarGroup(); migrating it to a class '
        'breaks every collapsible sidebar group'
    )
    # Nothing the migration emits may set a read-back property.
    for value in m.collect():
        overlap = m._properties_of(value) & unsafe
        assert not overlap, (
            f'migration candidate {value!r} sets {overlap}, which JavaScript '
            'reads back off element.style'
        )


def test_the_property_list_is_derived_from_source_not_hardcoded():
    """A newly added `if (el.style.foo === ...)` must protect `foo` on its own.

    A hardcoded list goes stale silently, and the failure mode is a broken
    toggle nobody connects to a styling change months later.
    """
    m = _load()
    with open(SCRIPT, encoding='utf-8') as fh:
        src = fh.read()
    body = src[src.index('def runtime_read_properties'):src.index('def _kebab')]
    assert '.style.' in body and 'finditer' in body, (
        'runtime_read_properties() no longer scans the source'
    )
    # It must actually find things, i.e. the regex still matches this codebase.
    assert len(m.runtime_read_properties()) >= 3


def test_every_generated_class_is_referenced_and_every_reference_is_defined():
    """No orphan classes in the sheet, no undefined classes in the markup."""
    with open(os.path.join(REPO, 'frontend', 'styles-redesign.css'), encoding='utf-8') as fh:
        sheet = fh.read()
    if 'BEGIN generated utility classes' not in sheet:
        import pytest
        pytest.skip('no generated block yet')
    block = sheet.split('BEGIN generated utility classes')[1].split('END generated')[0]
    # UPDATED, NOT DELETED. The pattern was `\.(u-xxxxxxxx)\s*\{`, which only
    # matched a FLAT selector. The generated selector is now doubled
    # (`.u-x.u-x`, 0-0-2-0) because a flat 0-0-1-0 class loses to any
    # descendant rule, and an inline style attribute never did: `<h2
    # style="font-size:20px">` inside `.section-head` silently shrank to 17px
    # once it became a plain class. See the specificity note in
    # scripts/migrate_inline_styles.py::build_css.
    #
    # Both forms are accepted so the assertion keeps working against classes
    # carried forward from before that change.
    defined = set(re.findall(
        r'\.(u-[0-9a-f]{8})(?:\.u-[0-9a-f]{8})?\s*\{', block))
    assert defined, 'the generated block defines no classes'

    used = set()
    targets = [os.path.join(REPO, 'frontend', 'index.html')]
    js_dir = os.path.join(REPO, 'frontend', 'js')
    targets += [os.path.join(js_dir, f) for f in os.listdir(js_dir) if f.endswith('.js')]
    for path in targets:
        with open(path, encoding='utf-8') as fh:
            used |= set(re.findall(r'\b(u-[0-9a-f]{8})\b', fh.read()))

    assert not (defined - used), f'utility classes defined but never used: {sorted(defined - used)}'
    assert not (used - defined), f'utility classes used but never defined: {sorted(used - defined)}'


def test_the_script_is_idempotent():
    """Re-running must produce no further changes.

    Class names are content-addressed for exactly this reason; if a second run
    rewrote anything, the names would not be stable and every run would churn
    the diff.
    """
    before = subprocess.run([sys.executable, SCRIPT, '--check'],
                            capture_output=True, text=True, cwd=REPO)
    assert before.returncode == 0, before.stderr
    # --check reports the candidates that REMAIN. After a full migration the
    # already-migrated values are gone from the markup, so a stable run reports
    # only values still above the threshold that were skipped as unsafe.
    assert 'static inline style attributes' in before.stdout


def test_generated_classes_outrank_ordinary_component_css():
    """A lifted declaration must not lose a fight the attribute always won.

    An inline `style` attribute beats every selector in the cascade. A flat
    `.u-xxxxxxxx` (0-0-1-0) does not, so migrating one can silently change the
    rendered result -- which is exactly what happened:

        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">

    inside `.section-head` became `.u-89c33dcc`, and
    `.section-head h2 { font-size:17px }` (0-0-1-1) won. Measured live in
    Chromium: the heading rendered at 17px instead of 24px, with both rules
    matching and the utility losing. Caught by
    scripts/audit/computed_style_diff.py against a pre-migration baseline.

    The selector is now doubled (`.u-x.u-x`, 0-0-2-0). Deliberately NOT
    `!important`, which would also beat legitimate state rules such as a
    `.is-hidden` toggle or a `:hover` treatment.
    """
    with open(os.path.join(REPO, 'frontend', 'styles-redesign.css'),
              encoding='utf-8') as fh:
        sheet = fh.read()
    if 'BEGIN generated utility classes' not in sheet:
        import pytest
        pytest.skip('no generated block yet')
    block = sheet.split('BEGIN generated utility classes')[1].split('END generated')[0]

    flat = re.findall(r'^\.(u-[0-9a-f]{8})\s*\{', block, re.M)
    assert not flat, (
        'these classes use a flat 0-0-1-0 selector and can lose to ordinary '
        f'component CSS: {sorted(set(flat))[:8]}')

    doubled = re.findall(r'^\.(u-[0-9a-f]{8})\.\1\s*\{', block, re.M)
    assert doubled, 'the generated block defines no doubled selectors'


def test_generated_classes_do_not_use_important():
    """`!important` would beat state rules the app relies on."""
    with open(os.path.join(REPO, 'frontend', 'styles-redesign.css'),
              encoding='utf-8') as fh:
        sheet = fh.read()
    if 'BEGIN generated utility classes' not in sheet:
        import pytest
        pytest.skip('no generated block yet')
    block = sheet.split('BEGIN generated utility classes')[1].split('END generated')[0]
    # Strip comments first: the block's own header explains WHY !important was
    # rejected, and matching that sentence made this assertion fail against
    # correct output. Twelfth time an assertion has matched its own fix
    # comment in this review.
    declarations = re.sub(r'/\*.*?\*/', '', block, flags=re.S)
    assert '!important' not in declarations


def test_carried_forward_classes_live_inside_the_generated_block():
    """Appending past the END marker orphans them on the next run.

    The first version of the carry-forward wrote them after END, so they sat
    outside the region the next run replaces -- duplicated once, then deleted.
    """
    with open(os.path.join(REPO, 'frontend', 'styles-redesign.css'),
              encoding='utf-8') as fh:
        sheet = fh.read()
    if 'carried forward from earlier runs' not in sheet:
        return
    end_marker = sheet.index('END generated')
    carried = sheet.index('carried forward from earlier runs')
    assert carried < end_marker, (
        'carried-forward classes are outside the generated block and will be '
        'dropped by the next run')
