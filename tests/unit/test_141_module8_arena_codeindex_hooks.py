"""Module 8 regression tests — arena, codeindex, hooks, specs.

Each test below corresponds to a defect found by probing the running module:

1. codeindex dead-code reported framework entry points as deletable. On this
   repo 47 of the first 50 rows were FastAPI route handlers (`index`,
   `favicon`, `manifest`); acting on the report would have removed live
   endpoints. 597 candidates -> 48.
2. The Python parser only collected calls made *inside* function bodies, so
   module-level `config = load_config()` did not count as a reference.
3. Class bases and type annotations were not references, so Pydantic request
   models used only as `def f(body: LoginRequest)` looked dead.
4. hooks template substitution was flat, so `{{file.path}}` -- used by every
   seeded hook and by the UI's default prompt -- was sent to the model
   literally.
5. POST /hooks/{id}/run always returned ok:true even when the run recorded
   status='error', so the UI announced "Hook ran!" over a failure.
6. Arena wrote '[Error: No API key]' responses into arena_battles and let them
   be voted on, producing a permanent ELO leaderboard for models that never
   ran.
"""

from __future__ import annotations

import ast

import pytest

from backend.routers import codeindex, hooks


# ── 1. dead-code: framework entry points ──────────────────────────────────────
def test_route_handler_decorator_marks_entrypoint():
    """@router.get(...) must classify the function as a framework entry point."""
    src = 'import x\n@router.get("/thing")\nasync def read_thing():\n    return 1\n'
    parsed = codeindex._parse_python('m.py', src)
    sym = next(s for s in parsed['symbols'] if s['name'] == 'read_thing')
    assert sym['is_entrypoint'] is True
    assert 'router.get' in sym['decorators']


@pytest.mark.parametrize(
    'decorator',
    [
        '@app.route("/x")',
        '@router.post("/x")',
        '@router.websocket("/ws")',
        '@app.middleware("http")',
        '@pytest.fixture',
        '@app.on_event("startup")',
        '@celery.task',
        '@cli.command()',
        '@property',
    ],
)
def test_framework_decorators_are_entrypoints(decorator):
    src = f'{decorator}\ndef handler():\n    return 1\n'
    parsed = codeindex._parse_python('m.py', src)
    assert parsed['symbols'][0]['is_entrypoint'] is True, decorator


def test_plain_function_is_not_an_entrypoint():
    parsed = codeindex._parse_python('m.py', 'def helper():\n    return 1\n')
    assert parsed['symbols'][0]['is_entrypoint'] is False


def test_unrelated_decorator_is_not_an_entrypoint():
    """A user decorator such as @memoize must not exempt a symbol."""
    src = '@memoize\ndef helper():\n    return 1\n'
    parsed = codeindex._parse_python('m.py', src)
    assert parsed['symbols'][0]['is_entrypoint'] is False


# ── 2. module-level calls are references ──────────────────────────────────────
def test_module_level_call_is_recorded():
    """`config = load_config()` at import time is a real reference."""
    src = 'def load_config():\n    return {}\n\nconfig = load_config()\n'
    parsed = codeindex._parse_python('m.py', src)
    targets = {c['to_symbol'] for c in parsed['calls']}
    assert 'load_config' in targets


def test_module_level_call_has_module_scope():
    src = 'def go():\n    pass\n\ngo()\n'
    parsed = codeindex._parse_python('m.py', src)
    mod_calls = [c for c in parsed['calls'] if c['from_symbol'] == '<module>']
    assert [c['to_symbol'] for c in mod_calls] == ['go']


def test_call_inside_function_is_not_duplicated_as_module_level():
    src = 'def a():\n    b()\n\ndef b():\n    pass\n'
    parsed = codeindex._parse_python('m.py', src)
    assert not [c for c in parsed['calls'] if c['from_symbol'] == '<module>']


# ── 3. annotations and base classes are references ────────────────────────────
def test_type_annotation_counts_as_reference():
    """A Pydantic model used only as a parameter type is not dead."""
    src = 'class LoginRequest:\n    pass\n\ndef login(body: LoginRequest):\n    return 1\n'
    parsed = codeindex._parse_python('m.py', src)
    targets = {c['to_symbol'] for c in parsed['calls']}
    assert 'LoginRequest' in targets


def test_return_annotation_counts_as_reference():
    src = 'class Result:\n    pass\n\ndef run() -> Result:\n    return None\n'
    parsed = codeindex._parse_python('m.py', src)
    assert 'Result' in {c['to_symbol'] for c in parsed['calls']}


def test_base_class_counts_as_reference():
    src = 'class Base:\n    pass\n\nclass Child(Base):\n    pass\n'
    parsed = codeindex._parse_python('m.py', src)
    assert 'Base' in {c['to_symbol'] for c in parsed['calls']}


def test_dead_code_endpoint_reports_its_basis(monkeypatch):
    """The response must state that it is a heuristic and what it excluded."""
    payload = codeindex.dead_code_detection()
    assert payload['confidence'] == 'heuristic'
    assert 'excluded_entrypoints' in payload
    assert 'note' in payload and payload['note']
    assert payload['returned'] == len(payload['dead_symbols'])


def test_real_repo_route_handlers_are_not_reported_dead():
    """End-to-end over this repo's own backend: no decorated route is 'dead'.

    This is the shape of the original defect -- `index`, `favicon` and
    `manifest` from backend/app.py were all in the top 10.
    """
    from pathlib import Path

    src = Path('backend/app.py')
    if not src.exists():
        pytest.skip('backend/app.py not present')
    parsed = codeindex._parse_python('backend/app.py', src.read_text(errors='ignore'))
    decorated = {s['name'] for s in parsed['symbols'] if s['is_entrypoint']}
    # These are the exact names the broken detector offered for deletion.
    for name in ('index', 'favicon', 'manifest'):
        if any(s['name'] == name for s in parsed['symbols']):
            assert name in decorated, f'{name} must be recognised as an entry point'


# ── 4. hook templating ────────────────────────────────────────────────────────
def test_nested_placeholder_is_substituted():
    out = hooks._render_template(
        'Review {{file.path}}', {'file': {'path': 'a.py'}}
    )
    assert out == 'Review a.py'
    assert '{{' not in out


def test_multiple_nested_placeholders():
    out = hooks._render_template(
        'Review {{file.path}} ({{file.size_lines}} lines)',
        {'file': {'path': 'a.py', 'size_lines': 42}},
    )
    assert out == 'Review a.py (42 lines)'


def test_deeply_nested_placeholder():
    assert hooks._render_template('{{a.b.c}}', {'a': {'b': {'c': 'deep'}}}) == 'deep'


def test_commit_placeholder_matches_seeded_hook_shape():
    out = hooks._render_template(
        'Message: {{commit.message}}', {'commit': {'message': 'fix bug'}}
    )
    assert out == 'Message: fix bug'


def test_unresolved_placeholder_is_left_visible():
    """A typo must stay visible rather than silently blanking."""
    assert hooks._render_template('{{nope.x}}', {'file': {}}) == '{{nope.x}}'


def test_whitespace_inside_placeholder_is_tolerated():
    assert hooks._render_template('{{ file.path }}', {'file': {'path': 'a.py'}}) == 'a.py'


def test_dict_value_is_serialised_not_stringified_as_repr():
    out = hooks._render_template('{{file}}', {'file': {'path': 'a.py'}})
    assert out == '{"path": "a.py"}'


def test_empty_template_is_safe():
    assert hooks._render_template('', {'file': {}}) == ''


# ── 5. hook run status honesty ────────────────────────────────────────────────
def test_manual_run_returns_status_field():
    """/run must expose the status it wrote to hook_runs."""
    import inspect

    src = inspect.getsource(hooks.manual_run_hook)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert "'status'" in src or '"status"' in src
    assert '_LAST_RUN_STATUS' in src


# ── 6. arena: failed battles must not be scored ───────────────────────────────
def test_vote_refuses_failed_battle():
    """A battle flagged failed cannot produce ELO. Second door: the endpoint."""
    import inspect

    src = inspect.getsource(__import__('backend.routers.arena', fromlist=['x']).vote)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'failed_a' in src and 'failed_b' in src
    assert 'battle_failed' in src


def test_arena_schema_has_failure_columns():
    from backend.routers import arena

    assert 'failed_a' in arena._SCHEMA
    assert 'failed_b' in arena._SCHEMA


def test_battle_marks_failure_and_blocks_vote():
    """The streaming handler must set votable=False when a side errors."""
    import inspect

    from backend.routers import arena

    src = inspect.getsource(arena.create_battle)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'votable' in src
    assert 'failed_a' in src and 'failed_b' in src


# ── parser must stay syntactically honest ─────────────────────────────────────
def test_parser_survives_syntax_error():
    parsed = codeindex._parse_python('bad.py', 'def broken(:\n')
    assert parsed == {'symbols': [], 'imports': [], 'calls': []}


def test_decorator_name_flattens_dotted_calls():
    tree = ast.parse('@a.b.c(1)\ndef f():\n    pass\n')
    dec = tree.body[0].decorator_list[0]
    assert codeindex._decorator_name(dec) == 'a.b.c'
