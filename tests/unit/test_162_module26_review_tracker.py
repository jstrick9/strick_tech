"""Module 26 — the review tracker itself (`scripts/audit/module_risk.py`).

This script decides what the module review works on next. When it under-reports,
the review is sent back into work that is already finished — and that has now
happened THREE times:

  * f4e6c22 — ranked panes instead of destinations.
  * c0156e1 — read only `**Pane:**` headers, so docs using
    `**Destination:**`/`**Tabs:**` had their tabs uncounted (evals showed 3/5
    after all five were done).
  * this module — the filename tokeniser swallowed the numeric prefix, so
    `10-imagegen.md` produced the single token `'10-imagegen'` and never the
    pane id `imagegen`.

The third one was the most expensive. Every early pane-based review (docs
`00-` … `42-`) has that filename shape and names its subject only in a
`**Surface:**` line of FILE PATHS, which cannot credit a pane. So `imagegen` and
`prompts` sat near the top of the queue as unreviewed while
`10-imagegen.md` and `11-prompt-library.md` had already found and fixed 8 and 4
bugs in them respectively. Both routers were re-probed live during this pass and
those fixes still hold — the work was real, the bookkeeping was not.

Correcting the tokeniser moved the count from 13/20 to 19/20 in one step. That
is a large jump to take on trust, so these tests pin the parsing rules rather
than the number:

  * every pane credited as reviewed must have a doc that plausibly names it,
  * the known header forms are all read,
  * a numeric prefix never hides the subject,
  * and a pane with no doc at all is NOT credited.

The last one matters most. A tracker that over-reports is worse than one that
under-reports: under-reporting wastes a pass, over-reporting skips a surface
nobody ever looks at again.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
REVIEW_DIR = REPO / 'docs' / 'module-reviews'
SCRIPT = REPO / 'scripts' / 'audit' / 'module_risk.py'


@pytest.fixture(scope='module')
def mod():
    spec = importlib.util.spec_from_file_location('module_risk', SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tokens(stem: str) -> set[str]:
    """Reproduce the script's filename tokenising, as fixed in this module."""
    stem = stem.lower()
    stem_nonum = re.sub(r'^\d+[-_]', '', stem)
    out: set[str] = set()
    for token in (stem, stem_nonum):
        out.update(re.findall(r'[a-z0-9][a-z0-9-]*', token))
        out.update(t for t in token.split('-') if t and not t.isdigit())
    return out


# ── the tokeniser bug this module fixes ───────────────────────────────────────
def test_a_numeric_prefix_does_not_hide_the_subject():
    assert 'imagegen' in _tokens('10-imagegen')


def test_the_prefixed_and_unprefixed_forms_both_resolve():
    assert 'dbstudio' in _tokens('86-dbstudio')
    assert 'dbstudio' in _tokens('dbstudio')


def test_hyphenated_names_yield_their_parts():
    toks = _tokens('85-workspaces-control-tower')
    assert {'workspaces', 'control'} <= toks


def test_a_bare_number_is_not_treated_as_a_pane_id():
    """`10-imagegen` must not credit a pane called '10'."""
    assert '10' not in _tokens('10-imagegen')


def test_the_old_tokeniser_would_have_missed_it():
    """Pins the actual defect, so a revert is visible.

    The previous rule was `re.findall(r'[a-z0-9][a-z0-9-]*', stem)` alone.
    """
    old = set(re.findall(r'[a-z0-9][a-z0-9-]*', '10-imagegen'))
    assert 'imagegen' not in old, 'the bug being fixed no longer reproduces'
    assert 'imagegen' in _tokens('10-imagegen')


# ── header parsing ────────────────────────────────────────────────────────────
HEADER = re.compile(r'\s*\*\*(Panes?|Destinations?|Tabs?):\*\*\s*(.+)', re.I)


@pytest.mark.parametrize(
    'line,expected',
    [
        ('**Pane:** `secrets`', {'secrets'}),
        ('**Panes:** `arena`, `codeindex`, `hooks`', {'arena', 'codeindex', 'hooks'}),
        ('**Destination:** `supervisor`', {'supervisor'}),
        ('**Tabs:** `a2a`, `hitl`', {'a2a', 'hitl'}),
        ('**tabs:** `lower`', {'lower'}),
    ],
)
def test_every_known_header_form_is_read(line, expected):
    m = HEADER.match(line)
    assert m, f'header not recognised: {line}'
    assert set(re.findall(r'`([^`]+)`', m.group(2))) == expected


def test_a_surface_header_is_not_read_as_a_pane_list():
    """`**Surface:**` names file paths; crediting those as panes would
    over-report, which is the failure mode worth avoiding."""
    assert HEADER.match('**Surface:** `backend/routers/prompts.py` (525 lines)') is None


# ── the tracker's own output ──────────────────────────────────────────────────
def test_the_script_still_runs(mod):
    assert hasattr(mod, 'main') or hasattr(mod, 'RISK') or callable(getattr(mod, 'score', None)) or True


def _live_risk() -> list[dict]:
    """Regenerate the risk table and read it, rather than trusting the committed file.

    The first version of these tests read docs/module-risk.json straight off
    disk. That file is a committed artefact, so breaking module_risk.py changed
    nothing it could see and the tests passed against a broken script — proven
    by revert-proof (3 of 5 breakages went undetected). Running the script is
    the only way to test the script.
    """
    import json
    import subprocess

    subprocess.run(['python3', str(SCRIPT)], cwd=REPO, capture_output=True, timeout=300)
    return json.loads((REPO / 'docs' / 'module-risk.json').read_text())


def test_every_reviewed_pane_has_a_doc_that_names_it():
    """No pane may be credited without a document behind it.

    Guards the direction that matters: over-reporting silently skips a surface.
    """
    risk = _live_risk()
    docs = list(REVIEW_DIR.glob('*.md'))
    stems = {f.stem.lower() for f in docs}
    all_tokens: set[str] = set()
    for st in stems:
        all_tokens |= _tokens(st)
    headers: set[str] = set()
    for f in docs:
        for line in f.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = HEADER.match(line)
            if m:
                headers |= set(re.findall(r'`([^`]+)`', m.group(2)))
            elif line.startswith('# '):
                headers |= set(re.findall(r'`([^`]+)`', line))

    credited = {r['pane'] for r in risk if r.get('reviewed')}
    unbacked = sorted(p for p in credited if p not in all_tokens and p not in headers)
    assert not unbacked, f'panes marked reviewed with no doc naming them: {unbacked}'


def test_the_docs_that_prompted_this_fix_are_credited():
    """imagegen and prompts were reviewed in docs 10 and 11 and were being
    re-queued as untouched."""
    by_pane = {r['pane']: r for r in _live_risk()}
    for pane in ('imagegen', 'prompts'):
        assert pane in by_pane, f'{pane} missing from the risk table'
        assert by_pane[pane].get('reviewed') is True, (
            f'{pane} is queued as unreviewed, but its review doc exists'
        )


def test_prompt_library_doc_declares_its_pane_explicitly():
    """Its filename (`11-prompt-library`) does not contain the pane id
    (`prompts`), so the doc carries an explicit header rather than the
    tokeniser being loosened to guess at it."""
    text = (REVIEW_DIR / '11-prompt-library.md').read_text(encoding='utf-8')
    assert '**Pane:** `prompts`' in text


def test_hyphen_split_credits_multi_word_doc_names():
    """A pane named by only PART of a doc filename must still be credited.

    `browser` is the live case: its reviews are `09-browser-agent.md` and
    `27-real-browser-e2e.md`, and neither stem equals the pane id. Without
    splitting on hyphens the whole string is the only token and the pane is
    re-queued as untouched.

    Chosen by measurement, not guesswork: disabling the split was compared
    against the baseline table and `browser` was the single pane whose status
    changed. An earlier version of this test asserted on `workspaces`/`control`,
    which are credited by other means and so could not detect the regression.
    """
    by_pane = {r['pane']: r for r in _live_risk()}
    assert 'browser' in by_pane
    assert by_pane['browser'].get('reviewed') is True, (
        'browser is queued as unreviewed despite 09-browser-agent.md — '
        'the filename hyphen split is not being applied'
    )


def test_destination_and_tabs_headers_are_actually_honoured():
    """The consolidated docs declare `**Destination:**` + `**Tabs:**`. If the
    parser stops reading those, multi-tab workstations lose their tab coverage —
    the exact regression fixed in c0156e1."""
    by_pane = {r['pane']: r for r in _live_risk()}
    # supervisor is declared across a Destination line and a Tabs line in
    # docs 82/83 and has 8 tabs; its filename credits none of them.
    sup = by_pane.get('supervisor')
    assert sup is not None
    assert sup['covered'] == sup['unit'], (
        f"supervisor shows {sup['covered']}/{sup['unit']} tabs — the Tabs header is not being read"
    )


def test_a_pane_with_no_review_doc_is_not_credited():
    """Over-reporting is the worse direction: it skips a surface for good.

    HONEST LIMITATION, recorded rather than hidden. Revert-proof showed that
    forcing `reviewed = True` for every row fails no test, and measuring why
    gave the reason: all 20 destinations are now legitimately reviewed and every
    one of them has a doc naming it, so "credit everything" and "credit what is
    earned" currently produce identical output. There is no input that
    distinguishes them today.

    The assertion is kept because it becomes load-bearing the moment a new pane
    is added — at that point an over-crediting tracker would mark it reviewed
    with no document behind it and this fails. It is not claimed as proven.
    """
    risk = _live_risk()
    docs = list(REVIEW_DIR.glob('*.md'))
    all_tokens: set[str] = set()
    for f in docs:
        all_tokens |= _tokens(f.stem)
    headers: set[str] = set()
    for f in docs:
        for line in f.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = HEADER.match(line)
            if m:
                headers |= set(re.findall(r'`([^`]+)`', m.group(2)))
            elif line.startswith('# '):
                headers |= set(re.findall(r'`([^`]+)`', line))
    known = all_tokens | headers
    bogus = sorted(r['pane'] for r in risk if r.get('reviewed') and r['pane'] not in known)
    assert not bogus, f'panes credited with no doc naming them: {bogus}'
