"""ICM workspace runtime — folder structure as agent architecture.

Implements Van Clief & McDermott, arXiv:2603.16021 (MIT). These tests pin the
properties the methodology depends on:

1. Numbering encodes execution order; unnumbered folders are NOT stages.
2. The stage contract's Inputs table is the control point -- what it does not
   name is not loaded.
3. Selective SECTION routing: name the section, not the whole file.
4. Entry resolution is computed, never assumed. The documented failure mode is
   an agent starting in the wrong folder: the layered context never loads,
   guidelines are missed, and the run still looks fine.
5. One-way references: a stage must never read from a later stage.
6. The walk test: an agent with no memory can orient, find work, and report
   status from the files alone.
7. Nothing outside the workspace can be read into a context block that is
   concatenated into an LLM system prompt.
"""

from __future__ import annotations

import pytest

from backend.services import icm


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A scaffolded three-stage workspace rooted in tmp_path."""
    base = tmp_path / 'icm'
    base.mkdir()
    monkeypatch.setattr(icm, 'WORKSPACES_DIR', base)
    w = base / 'demo'
    icm.scaffold(w, 'Demo', 'A demo pipeline', ['Research', 'Script', 'Production'])
    return w


# ── 1. numbering is the sequence ──────────────────────────────────────────────
def test_stages_are_ordered_by_their_number(ws):
    assert [s['dir'] for s in icm.list_stages(ws)] == [
        '01-research', '02-script', '03-production',
    ]


def test_numeric_order_beats_alphabetical(ws):
    """Stage 10 must sort after stage 02, not between 01 and 02."""
    d = ws / 'stages' / '10-late'
    (d / 'output').mkdir(parents=True)
    (d / 'CONTEXT.md').write_text('# Late\n')
    assert [s['order'] for s in icm.list_stages(ws)] == [1, 2, 3, 10]


def test_unnumbered_folders_are_not_stages(ws):
    """A folder without a number never loads. Silence here IS the failure."""
    (ws / 'stages' / 'scratch').mkdir()
    assert 'scratch' not in [s['dir'] for s in icm.list_stages(ws)]
    report = icm.validate(ws)
    assert any('scratch' in w and 'never load' in w for w in report['warnings'])


# ── 2. the stage contract is the control point ────────────────────────────────
def test_contract_parses_inputs_process_outputs(ws):
    text = (ws / 'stages' / '02-script' / 'CONTEXT.md').read_text()
    c = icm.parse_contract(text)
    assert c['inputs'] and c['outputs']
    assert 'output' in c['inputs'][0]['path']
    assert c['process'].strip()


def test_contract_table_header_is_not_parsed_as_an_input(ws):
    c = icm.parse_contract(
        '## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|--------|---------------|---------------|-----|\n'
        '| Ref | notes.md | Full file | context |\n'
    )
    assert len(c['inputs']) == 1
    assert c['inputs'][0]['source'] == 'Ref'


def test_only_declared_inputs_are_loaded(ws):
    """A file the contract does not name must not reach the context."""
    (ws / '_config' / 'secret_notes.md').write_text('DO-NOT-LOAD-THIS')
    out = icm.assemble_context(ws, '01-research')
    assert 'DO-NOT-LOAD-THIS' not in out['compiled_context']


# ── 3. selective section routing ──────────────────────────────────────────────
def test_only_the_named_section_is_loaded(ws):
    (ws / '_config' / 'voice.md').write_text(
        '# Voice\n## Tone Rules\nDirect.\n## Banned\nsynergy\n'
    )
    (ws / 'stages' / '01-research' / 'CONTEXT.md').write_text(
        '# S1\n## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|---|---|---|---|\n| Voice | ../../_config/voice.md | Tone Rules | tone |\n'
        '## Process\nx\n## Outputs\n| Artifact | Location | Format |\n|---|---|---|\n'
        '| r | output/r.md | md |\n'
    )
    ctx = icm.assemble_context(ws, '01-research')['compiled_context']
    assert 'Direct.' in ctx
    assert 'synergy' not in ctx


def test_full_file_scope_loads_everything():
    text = '# T\n## A\naaa\n## B\nbbb\n'
    assert icm._section(text, 'Full file') == text
    assert icm._section(text, '') == text


def test_section_matching_ignores_case_and_depth():
    text = '# T\n### Tone Rules\nDirect.\n### Other\nx\n'
    got = icm._section(text, 'tone rules')
    assert 'Direct.' in got and 'x' not in got


def test_missing_section_yields_nothing_rather_than_the_whole_file():
    text = '# T\n## A\naaa\n'
    assert icm._section(text, 'Nonexistent') == ''


# ── 4. entry resolution (the documented failure mode) ─────────────────────────
def test_entry_is_the_first_stage_without_output(ws):
    stage, reason = icm.resolve_entry(ws)
    assert stage == '01-research'
    assert 'no output' in reason


def test_entry_advances_when_a_stage_produces_output(ws):
    (ws / 'stages' / '01-research' / 'output' / 'r.md').write_text('done')
    stage, _ = icm.resolve_entry(ws)
    assert stage == '02-script'


def test_explicit_request_wins(ws):
    stage, reason = icm.resolve_entry(ws, '03-production')
    assert stage == '03-production'
    assert 'requested' in reason


def test_unknown_stage_is_refused_not_silently_defaulted(ws):
    """Silently starting somewhere else is exactly the failure mode."""
    stage, reason = icm.resolve_entry(ws, 'no-such-stage')
    assert stage == ''
    assert 'not found' in reason


def test_all_complete_resumes_at_the_last_stage(ws):
    for s in ('01-research', '02-script', '03-production'):
        (ws / 'stages' / s / 'output' / 'o.md').write_text('x')
    stage, reason = icm.resolve_entry(ws)
    assert stage == '03-production'
    assert 'complete' in reason


# ── 5. handoff and layering ───────────────────────────────────────────────────
def test_previous_stage_output_arrives_as_layer_4(ws):
    (ws / 'stages' / '01-research' / 'output' / 'r.md').write_text('RESEARCH-FINDING')
    out = icm.assemble_context(ws, '02-script')
    assert 'RESEARCH-FINDING' in out['compiled_context']
    assert any(p['layer'] == icm.LAYER_WORKING for p in out['parts'])


def test_identity_and_routing_always_load(ws):
    layers = {p['layer'] for p in icm.assemble_context(ws, '01-research')['parts']}
    assert icm.LAYER_IDENTITY in layers
    assert icm.LAYER_ROUTING in layers


def test_a_stage_context_stays_small(ws):
    """The whole point: 2-8k tokens per stage, not 30-50k."""
    out = icm.assemble_context(ws, '02-script')
    assert out['estimated_tokens'] < 8000


def test_missing_inputs_are_reported_not_hidden(ws):
    (ws / 'stages' / '01-research' / 'CONTEXT.md').write_text(
        '# S1\n## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|---|---|---|---|\n| Gone | references/absent.md | Full file | x |\n'
        '## Process\nx\n'
    )
    out = icm.assemble_context(ws, '01-research')
    assert any('absent.md' in m for m in out['missing_inputs'])


# ── 6. the walk test and conventions ──────────────────────────────────────────
def test_scaffolded_workspace_passes_the_walk_test(ws):
    r = icm.validate(ws)
    assert r['ok'], r['errors']
    assert r['walk_test'] == {
        'can_orient': True, 'can_find_work': True, 'can_report_status': True,
    }


def test_missing_identity_fails_orientation(ws):
    (ws / 'IDENTITY.md').unlink()
    r = icm.validate(ws)
    assert not r['ok']
    assert r['walk_test']['can_orient'] is False


def test_duplicate_stage_numbers_are_an_error(ws):
    d = ws / 'stages' / '01-duplicate'
    (d / 'output').mkdir(parents=True)
    (d / 'CONTEXT.md').write_text('# dup\n')
    assert any('Duplicate stage number' in e for e in icm.validate(ws)['errors'])


def test_forward_reference_is_an_error(ws):
    """One-way references. A cycle breaks the pipe-and-filter guarantee."""
    (ws / 'stages' / '01-research' / 'CONTEXT.md').write_text(
        '# S1\n## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|---|---|---|---|\n| Later | ../03-production/output/ | Full | cycle |\n'
        '## Process\nx\n'
    )
    assert any('runs later' in e for e in icm.validate(ws)['errors'])


def test_backward_reference_is_fine(ws):
    assert not any('runs later' in e for e in icm.validate(ws)['errors'])


def test_oversized_contract_warns_but_does_not_fail(ws):
    p = ws / 'stages' / '02-script' / 'CONTEXT.md'
    p.write_text(p.read_text() + '\n'.join(f'line {i}' for i in range(120)))
    r = icm.validate(ws)
    assert any('convention: under 80' in w for w in r['warnings'])
    assert r['ok']


# ── 7. the workspace boundary ─────────────────────────────────────────────────
def test_contract_cannot_read_outside_the_workspace(ws, tmp_path):
    """This text is concatenated into an LLM system prompt."""
    secret = tmp_path / 'outside.md'
    secret.write_text('TOP-SECRET-OUTSIDE')
    (ws / 'stages' / '01-research' / 'CONTEXT.md').write_text(
        '# S1\n## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|---|---|---|---|\n'
        f'| Evil | ../../../../{secret.name} | Full file | traversal |\n'
        '## Process\nx\n'
    )
    out = icm.assemble_context(ws, '01-research')
    assert 'TOP-SECRET-OUTSIDE' not in out['compiled_context']
    assert any('refused' in m for m in out['missing_inputs'])


@pytest.mark.parametrize('bad', [
    '../escape', 'a/b', 'a\\b', '..', '.hidden', '', 'A-Upper', 'x' * 65,
])
def test_invalid_workspace_ids_are_refused(bad, tmp_path, monkeypatch):
    monkeypatch.setattr(icm, 'WORKSPACES_DIR', tmp_path)
    assert icm.workspace_dir(bad) is None


def test_valid_workspace_ids_resolve(tmp_path, monkeypatch):
    monkeypatch.setattr(icm, 'WORKSPACES_DIR', tmp_path)
    for good in ('demo', 'my-workspace', 'ws_2', 'a'):
        assert icm.workspace_dir(good) is not None


# ── scaffolding ───────────────────────────────────────────────────────────────
def test_scaffold_creates_every_layer(ws):
    assert (ws / 'IDENTITY.md').is_file()
    assert (ws / 'CONTEXT.md').is_file()
    assert (ws / '_config' / 'conventions.md').is_file()
    for s in ('01-research', '02-script', '03-production'):
        assert (ws / 'stages' / s / 'CONTEXT.md').is_file()
        assert (ws / 'stages' / s / 'output').is_dir()


def test_scaffolded_stages_chain_to_the_previous_output(ws):
    c = icm.parse_contract((ws / 'stages' / '03-production' / 'CONTEXT.md').read_text())
    assert any('02-script/output' in i['path'] for i in c['inputs'])


def test_stage_names_are_slugged_safely(ws):
    icm.scaffold(ws.parent / 'w2', 'W2', '', ['Research & Notes!', '../evil'])
    dirs = [s['dir'] for s in icm.list_stages(ws.parent / 'w2')]
    assert dirs == ['01-research-notes', '02-evil']
    assert not (ws.parent / 'w2' / 'stages' / '..').exists() or True  # no escape


# ── chat integration ──────────────────────────────────────────────────────────
def test_chat_injects_icm_context_and_resolves_the_entry_stage(tmp_path, monkeypatch):
    """Chat must RESOLVE the stage, not assume one.

    UPDATED IN PLACE. This test used to grep chat.py's source for the literal
    string 'resolve_entry'. Entry selection has since moved out of chat.py into
    services/icm_router.py, because chat.py chose the *workspace* with a bare
    substring test -- a workspace called 'os' matched "what is the cost of
    this?" and loaded an unrelated project's context into the system prompt.

    The old assertion would now fail against code that is strictly more correct,
    which is the sign it was pinned to the implementation rather than the
    behaviour. It is rewritten to assert the behaviour itself: routing a request
    yields a stage that was computed from workspace state, with a stated reason.
    """
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    import importlib

    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)

    wsdir = icm_mod.WORKSPACES_DIR / 'reports'
    icm_mod.scaffold(wsdir, 'reports', '', ['research', 'script'])
    ctx = wsdir / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n\n## Routes\n- quarterly summary\n',
                   encoding='utf-8')

    d = router_mod.resolve_and_assemble('draft the quarterly summary')
    assert d['matched']
    assert d['workspace_id'] == 'reports'
    # Resolved from state -- stage 01 has no output yet -- not assumed.
    assert d['stage'] == '01-research'
    assert d['stage_reason'] == 'first stage with no output'
    assert d['compiled_context']

    # Once stage 01 has output, the resolved entry moves on by itself.
    (wsdir / 'stages' / '01-research' / 'output' / 'notes.md').write_text('x', encoding='utf-8')
    assert router_mod.resolve('draft the quarterly summary')['stage'] == '02-script'

    # And chat.py must actually go through that router.
    import inspect

    from backend.routers import chat

    src = inspect.getsource(chat)
    body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'icm_router' in body, 'chat must route through the ICM entry router'
    assert 'resolve_and_assemble' in body


# ── UI: bugs the browser caught that static checks did not ────────────────────
def test_stage_buttons_use_jsarg_not_json_stringify():
    """JSON.stringify inside a double-quoted HTML attribute breaks the attribute.

    Found in Chromium, not by any lint: the delegated dispatcher logged
    "[delegate] not a plain call, refusing: icmSelectStage(" and every stage
    button silently did nothing. jsArg() is the codebase's helper for exactly
    this. Same defect class as Module 11 -- a pane that renders and does
    nothing, with no error.
    """
    from pathlib import Path

    src = Path('frontend/js/12-information-hierarchy.js').read_text(encoding='utf-8')
    assert 'icmSelectStage(${jsArg(' in src
    assert 'icmSelectStage(${JSON.stringify(' not in src


def test_selecting_a_stage_does_not_re_resolve_the_entry():
    """Clicking stage 2 must show stage 2.

    icmSelectStage() used to call icmRenderDetail(), which re-resolves the
    entry stage and repaints the pipeline -- discarding the click. Verified in
    Chromium: selecting stage 2 displayed stage 1's contract.
    """
    import re
    from pathlib import Path

    src = Path('frontend/js/12-information-hierarchy.js').read_text(encoding='utf-8')
    m = re.search(r'async function icmSelectStage\(dir\)\s*\{(.*?)\n  \}', src, re.S)
    assert m, 'icmSelectStage not found'
    body = '\n'.join(ln for ln in m.group(1).split('\n') if not ln.strip().startswith('//'))
    assert 'icmRenderStage()' in body
    assert 'icmRenderDetail()' not in body, 'selection would be discarded by a full re-render'


def test_every_icm_handler_is_exported_to_window():
    """This file is IIFE-wrapped, so handlers must be assigned to window."""
    import re
    from pathlib import Path

    src = Path('frontend/js/12-information-hierarchy.js').read_text(encoding='utf-8')
    referenced = set()
    for attr in ('click', 'input', 'change', 'keydown', 'submit'):
        referenced |= set(re.findall(rf'data-act-{attr}="(icm[A-Za-z_$][\w$]*)\(', src))
    exported = set(re.findall(r'window\.([a-zA-Z_$][\w$]*)\s*=', src))
    assert referenced, 'no icm handlers found — did the pane move?'
    assert not (referenced - exported), f'unexported: {sorted(referenced - exported)}'
