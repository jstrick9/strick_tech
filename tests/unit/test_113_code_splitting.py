"""Per-pane code splitting: correctness of the plan and of the loader.

WHAT THIS BUYS
──────────────
18 modules (448 KB raw) belong to exactly one pane each and are referenced by
nothing during boot. They are now fetched when that pane is first opened, and
prefetched during browser idle time. Measured in real Chromium:

    critical path before DOMContentLoaded:  223 KB  (was 288 KB brotli)
    slow-link DOMContentLoaded:           3,239 ms  (was 4,089 ms bundled,
                                                     13,667 ms unbundled)

WHY THE PLAN IS DERIVED, NOT WRITTEN
────────────────────────────────────
A hand-maintained "pane -> modules" list is the exact pattern behind repeated
bugs in this review: a module gains a dependency, the list is not updated, and
a pane renders blank. `scripts/analyse_split.js` re-derives the plan from the
source with a real JS parser; these tests fail if the committed plan drifts.

THE THREE ANALYSIS BUGS THESE TESTS PIN
───────────────────────────────────────
Each one shipped a broken pane in a live browser before being caught, and each
is reproduced below as a focused unit test:

1. **Load-time snapshots.** `01-app-core.js` builds
   `const wrappedRenders = { dashboard: typeof renderDashboard === 'function'
   ? renderDashboard : null, ... }` during boot. Deferring 36-dashboard.js
   makes that entry `null` and the pane silently dies.

2. **Unguarded bare calls inside functions.** `nav()` is wrapped several times
   and each layer calls renderers directly: `if (pane === 'mcp') renderMCP();`
   A bare identifier that was never declared throws ReferenceError -- unlike
   `window.renderMCP`, which is merely undefined. Verified live: deferring
   these produced `ReferenceError: renderMCP is not defined`,
   `renderLoops is not defined`, `renderIntegrations is not defined`,
   `renderImageGen is not defined`.

3. **Guards are per call site, not per file.** The fix for (2) first collected
   every `typeof x` in a file into one set. `01-app-core.js` guards
   `renderMCP` at line 3070 but calls it bare at line 2434, so the file-wide
   set said "safe" and the MCP pane threw. A guard only protects the statement
   it encloses.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / 'frontend'
JS_DIR = FRONTEND / 'js'
DIST = FRONTEND / 'dist'
PLAN_PATH = REPO / 'scripts' / 'split-plan.json'
ANALYSER = REPO / 'scripts' / 'analyse_split.js'

sys.path.insert(0, str(REPO / 'scripts'))

from backend.services import asset_bundle  # noqa: E402


def _node() -> str | None:
    return shutil.which('node')


def _has_acorn() -> bool:
    if not _node():
        return False
    return subprocess.run([_node(), '-e', "require('acorn');require('acorn-walk')"],
                          cwd=REPO, capture_output=True).returncode == 0


needs_acorn = pytest.mark.skipif(
    not _has_acorn(),
    reason='acorn not installed (npm install --no-save acorn acorn-walk)')


def _analyse_fixture(tmp_path: Path) -> dict:
    """Run the real analyser against a synthetic frontend/js tree.

    The probe script is written inside the repo, not into tmp_path: Node
    resolves `require('acorn')` by walking up from the SCRIPT's directory, so
    a copy in /tmp cannot find the repo's node_modules.
    """
    script = ANALYSER.read_text(encoding='utf-8').replace(
        "path.resolve(__dirname, '..')", json.dumps(str(tmp_path)))
    probe = REPO / 'scripts' / '_analyse_probe.tmp.js'
    probe.write_text(script, encoding='utf-8')
    try:
        result = subprocess.run([_node(), str(probe)], cwd=REPO,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    finally:
        probe.unlink(missing_ok=True)


@pytest.fixture(scope='module')
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def manifest() -> dict:
    return json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))


# ──────────────────────────────────────────────────────────────────────
#  The plan is real, current, and internally consistent
# ──────────────────────────────────────────────────────────────────────
def test_split_plan_is_committed(plan):
    assert plan['lazyFiles'], 'no modules are being split out'
    assert plan['lazy'], 'no panes have chunks'


@needs_acorn
def test_split_plan_matches_a_fresh_analysis(plan):
    """Editing frontend/js without re-deriving the plan must fail CI.

    Otherwise a module quietly gains a boot-time dependency, the stale plan
    keeps deferring it, and a pane breaks for whoever opens it.
    """
    result = subprocess.run([_node(), str(ANALYSER)],
                            cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    fresh = json.loads(result.stdout)
    assert fresh['lazy'] == plan['lazy'], (
        'the committed split plan is stale. Run:\n'
        '  python3 scripts/build_bundle.py --refresh-split')


def test_every_lazy_module_belongs_to_exactly_one_pane(plan):
    seen: dict[str, str] = {}
    for pane, modules in plan['lazy'].items():
        for module in modules:
            assert module not in seen, (
                f'{module} is claimed by both {seen[module]} and {pane}; '
                'a module two panes need cannot be a per-pane chunk')
            seen[module] = pane
    assert sorted(seen) == sorted(plan['lazyFiles'])


def test_lazy_modules_are_not_also_in_the_core_bundle(plan, manifest):
    """A module in both places would ship twice and re-execute on load."""
    core = set(manifest['head_modules']) | set(manifest['body_modules'])
    overlap = core & set(plan['lazyFiles'])
    assert not overlap, f'shipped both eagerly and lazily: {sorted(overlap)}'


def test_every_module_ships_exactly_once(plan, manifest):
    """No module may be dropped by the split -- that is a pane going dark."""
    core = set(manifest['head_modules']) | set(manifest['body_modules'])
    chunked = {m for c in manifest['chunks'].values() for m in c['modules']}
    on_disk = {p.name for p in JS_DIR.glob('*.js')}
    assert core | chunked == on_disk, (
        f'missing from the build: {sorted(on_disk - core - chunked)}; '
        f'unknown: {sorted(core | chunked - on_disk)}')


def test_boot_modules_are_never_deferred(plan):
    """Defer the navigation itself and nothing can request the chunks."""
    for module in ('00-pane-registry.js', '01-app-core.js', '00-store.js',
                   '00-workstations.js', '00-chunk-loader.js',
                   '00-style-hydrate.js'):
        assert module not in plan['lazyFiles'], f'{module} must stay eager'


def test_the_split_actually_defers_something_substantial(plan):
    """A plan that defers three tiny files would satisfy every test above."""
    assert plan['lazyBytes'] > 300_000, (
        f'only {plan["lazyBytes"]} bytes deferred; the split is not earning '
        'its complexity')


# ──────────────────────────────────────────────────────────────────────
#  The three analysis bugs, each pinned directly
# ──────────────────────────────────────────────────────────────────────
@needs_acorn
def test_modules_referenced_during_boot_are_not_deferred(plan, tmp_path):
    """Bug 1: a module whose names are read during top-level execution.

    `01-app-core.js` builds `const wrappedRenders = { dashboard: typeof
    renderDashboard === 'function' ? renderDashboard : null, ... }` while the
    page boots, capturing the function reference. Defer that module and the
    entry is `null` -- the pane dies with no error.

    An earlier version of this test just listed the modules named in
    `wrappedRenders` and asserted they were eager. **It passed against a build
    with the load-time check removed**, because the unguarded-bare-call rule
    happens to catch those same modules for a different reason. A test that
    passes against both the fixed and the broken analyser proves nothing, so
    it is replaced with a fixture that isolates load-time capture on its own:
    the module below is referenced ONLY from top-level code, never called
    bare.
    """
    module = tmp_path / 'frontend' / 'js'
    module.mkdir(parents=True)
    (module / '00-pane-registry.js').write_text(
        "window.MASTER_PANE_REGISTRY = {\n"
        "  'thing': () => typeof window.renderThing === 'function' && window.renderThing(),\n"
        "};\n", encoding='utf-8')
    # Top-level capture, exactly like wrappedRenders. No bare call anywhere.
    (module / '01-app-core.js').write_text(
        "const wrapped = { thing: typeof renderThing === 'function' ? renderThing : null };\n"
        "window.wrapped = wrapped;\n", encoding='utf-8')
    (module / '50-thing.js').write_text(
        "function renderThing(){ return 1; }\n", encoding='utf-8')

    out = _analyse_fixture(tmp_path)
    assert '50-thing.js' not in out['lazyFiles'], (
        'a module captured by a top-level expression during boot was marked '
        'deferrable; the captured reference would be null at runtime')

    # And the real plan must agree for the real file.
    assert 'const wrappedRenders' in (JS_DIR / '01-app-core.js').read_text(
        encoding='utf-8'), (
        'the construct this guards has been renamed; re-check the analysis')
    assert '26-swarm.js' not in plan['lazyFiles']


@needs_acorn
def test_modules_called_bare_from_nav_are_not_deferred(plan):
    """Bug 2: `if (pane === 'mcp') renderMCP();` throws if not yet loaded.

    Verified live -- deferring these produced ReferenceError for renderMCP,
    renderLoops, renderIntegrations and renderImageGen.
    """
    for module in ('39-mcp-panel.js', '40-loops.js', '22-integrations.js',
                   '15-image-generation.js', '28-kanban.js'):
        assert module not in plan['lazyFiles'], (
            f'{module} is called by a bare identifier from nav(); deferring '
            'it throws ReferenceError when its pane is opened')


@needs_acorn
def test_a_guard_only_protects_its_own_call_site(tmp_path):
    """Bug 3: one guarded use must not whitelist an unguarded one elsewhere.

    This is the shape of the real 01-app-core.js bug: `renderMCP` guarded at
    line 3070, called bare at line 2434.
    """
    module = tmp_path / 'frontend' / 'js'
    module.mkdir(parents=True)
    (module / '00-pane-registry.js').write_text(
        "window.MASTER_PANE_REGISTRY = {\n"
        "  'thing': () => typeof window.renderThing === 'function' && window.renderThing(),\n"
        "};\n", encoding='utf-8')
    (module / '01-app-core.js').write_text(
        "function guarded(){ if (typeof renderThing === 'function') renderThing(); }\n"
        "function unguarded(pane){ if (pane === 'thing') renderThing(); }\n",
        encoding='utf-8')
    (module / '50-thing.js').write_text(
        "function renderThing(){ return 1; }\n", encoding='utf-8')

    out = _analyse_fixture(tmp_path)
    assert '50-thing.js' not in out['lazyFiles'], (
        'an unguarded bare call was masked by a guarded one elsewhere in the '
        'same file -- guards must be evaluated per call site')


@needs_acorn
def test_a_purely_guarded_module_is_still_deferrable(tmp_path):
    """The mirror of the test above: guards must not be ignored entirely.

    Without this, "treat every bare name as blocking" would pass the previous
    test while deferring nothing at all.
    """
    module = tmp_path / 'frontend' / 'js'
    module.mkdir(parents=True)
    (module / '00-pane-registry.js').write_text(
        "window.MASTER_PANE_REGISTRY = {\n"
        "  'thing': () => typeof window.renderThing === 'function' && window.renderThing(),\n"
        "};\n", encoding='utf-8')
    (module / '01-app-core.js').write_text(
        "function onlyGuarded(){ if (typeof renderThing === 'function') renderThing(); }\n",
        encoding='utf-8')
    (module / '50-thing.js').write_text(
        "function renderThing(){ return 1; }\n", encoding='utf-8')

    out = _analyse_fixture(tmp_path)
    assert '50-thing.js' in out['lazyFiles'], (
        'a module used only behind typeof guards should be deferrable')


# ──────────────────────────────────────────────────────────────────────
#  Chunks are built, served and addressable
# ──────────────────────────────────────────────────────────────────────
def test_every_chunk_exists_and_is_precompressed(manifest):
    for pane, chunk in manifest['chunks'].items():
        path = DIST / chunk['file']
        assert path.is_file(), f'{pane}: missing {chunk["file"]}'
        gz = path.with_name(path.name + '.gz')
        assert gz.is_file(), f'{pane}: chunk is not precompressed'
        assert gz.stat().st_size < path.stat().st_size


def test_chunk_manifest_is_a_file_not_an_inline_script(manifest):
    """Inline scripts are refused under the enforced `script-src 'self'`.

    Shipping the manifest inline would have required loosening a policy that
    took three phases to tighten.
    """
    assert manifest.get('chunk_manifest'), 'no chunk manifest emitted'
    html = asset_bundle.rewrite_html(
        (FRONTEND / 'index.html').read_text(encoding='utf-8'), manifest)
    assert f'/static/dist/{manifest["chunk_manifest"]}' in html
    assert '__CHUNK_MANIFEST__' not in html, (
        'the manifest was inlined into the HTML; CSP will refuse it')


def test_chunk_manifest_loads_before_the_app_bundle(manifest):
    """00-chunk-loader.js reads the manifest while installing its wrappers."""
    html = asset_bundle.rewrite_html(
        (FRONTEND / 'index.html').read_text(encoding='utf-8'), manifest)
    assert html.index(manifest['chunk_manifest']) < html.index(manifest['body'])


def test_chunk_manifest_covers_exactly_the_lazy_panes(manifest, plan):
    js = (DIST / manifest['chunk_manifest']).read_text(encoding='utf-8')
    payload = json.loads(js.split('=', 1)[1].rstrip().rstrip(';'))
    assert sorted(payload) == sorted(plan['lazy'])
    for pane, filename in payload.items():
        assert (DIST / filename).is_file(), f'{pane} -> missing {filename}'


def test_chunks_are_served_compressed_and_cacheable(client, manifest):
    pane, chunk = next(iter(sorted(manifest['chunks'].items())))
    r = client.get(f'/static/dist/{chunk["file"]}',
                   headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert r.headers.get('content-encoding') == 'gzip'
    cache = r.headers.get('cache-control', '')
    assert 'immutable' in cache, f'{pane} chunk is not cacheable: {cache}'


# ──────────────────────────────────────────────────────────────────────
#  The loader hooks the registry, not individual call sites
# ──────────────────────────────────────────────────────────────────────
def test_loader_wraps_the_registry_rather_than_nav():
    """Three separate call sites invoke renderers.

    Patching nav() alone would leave showWorkstationTab() and the third caller
    in 14-prompt-library.js unprotected -- the "second door" bug this review
    has hit six times. Hooking MASTER_PANE_REGISTRY covers all of them, and
    any call site added later, by construction.
    """
    src = (JS_DIR / '00-chunk-loader.js').read_text(encoding='utf-8')
    assert 'MASTER_PANE_REGISTRY' in src
    # Reassignment, not the guarded `typeof window.nav === 'function'` read
    # used by the retry button.
    assert not re.search(r'window\.nav\s*=[^=]', src), (
        'the loader should not patch nav() directly -- hooking the registry '
        'is what covers all three renderer call sites')

    callers = [f for f in JS_DIR.glob('*.js')
               if 'MASTER_PANE_REGISTRY[' in f.read_text(encoding='utf-8')]
    assert len(callers) >= 3, (
        'expected several renderer call sites; if this dropped to one, the '
        'registry indirection may no longer be necessary')


def test_loader_runs_before_app_core():
    """It must install its wrappers before anything can navigate."""
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    assert html.index('00-pane-registry.js') < html.index('00-chunk-loader.js')
    assert html.index('00-chunk-loader.js') < html.index('01-app-core.js')


def test_loader_allows_retry_after_a_failed_fetch():
    """A transient network failure must not kill a pane for the session."""
    src = (JS_DIR / '00-chunk-loader.js').read_text(encoding='utf-8')
    assert 'delete loaded[pane]' in src, (
        'a failed chunk load must clear its cached promise so the next '
        'navigation retries')
    assert 'Retry' in src


def test_prefetch_respects_save_data_and_slow_connections():
    """Speculatively pulling 450 KB is wrong on a capped mobile plan."""
    src = (JS_DIR / '00-chunk-loader.js').read_text(encoding='utf-8')
    assert 'saveData' in src
    assert 'effectiveType' in src
    assert "rel = 'prefetch'" in src, (
        'prefetch should warm the cache without executing the chunk')
