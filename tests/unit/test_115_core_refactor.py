"""Removing dead coupling in 01-app-core.js doubled what can be lazy-loaded.

WHAT THIS BATCH DID
───────────────────
`01-app-core.js` held 23 modules (462 KB) in the eager bundle through three
constructs, none of which did anything useful:

1. **18 redundant renderer calls** in the stacked nav() wrappers --
   `if (pane === 'mcp') renderMCP();` -- duplicating what
   MASTER_PANE_REGISTRY already ran. Batch 30 made them harmless no-ops;
   this batch deletes them.

2. **A `wrappedRenders` block** that captured nine renderer references during
   boot and copied each onto `window.render<Name>` "to ensure they exist".
   They already existed: these are plain global scripts, so a top-level
   `function renderDashboard(){}` *is* `window.renderDashboard`. Verified in a
   live browser -- all nine were `typeof 'function'` on window before the
   block ran. A pure no-op that made nine modules undeferrable.

3. **Four `foo?.()` calls on bare identifiers** in command-palette actions.

RESULT: 18 lazy modules (504 KB) -> 36 lazy modules (797 KB, 38.5% of the
frontend). Core bundle 220 KB -> 182 KB brotli. Critical path 223 KB -> 185 KB.

THE SUBTLE ONE
──────────────
`foo?.()` looks like it tolerates a missing function, and for a missing
*value* it does. But optional chaining guards `null`/`undefined`, not an
absent *binding*: calling `undeclaredThing?.()` still throws

    ReferenceError: undeclaredThing is not defined

Verified directly in node. Only `window.foo?.()` is safe, because that is a
property read on an object that exists. These four sites were command-palette
actions -- precisely the code that runs before a lazy chunk has loaded.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
PLAN = json.loads((REPO / 'scripts' / 'split-plan.json').read_text(encoding='utf-8'))

APP_CORE = (JS / '01-app-core.js').read_text(encoding='utf-8')


def _strip_comments(source: str) -> str:
    """So an assertion cannot match the comment that explains it."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


CORE = _strip_comments(APP_CORE)


def _node():
    return shutil.which('node')


needs_node = pytest.mark.skipif(_node() is None, reason='node not installed')


# ──────────────────────────────────────────────────────────────────────
#  The dead coupling is gone
# ──────────────────────────────────────────────────────────────────────
def test_redundant_nav_wrapper_renderer_calls_are_gone():
    """`if (pane === 'x') renderX();` duplicated the registry.

    Every one of these had a MASTER_PANE_REGISTRY entry calling the same
    function -- verified in a live browser for all of them. They refired the
    pane's API calls and pinned the module into the eager bundle.
    """
    leftovers = re.findall(r"if \(pane === '[a-z-]+'\)\s+render\w+\??\(\);", CORE)
    assert not leftovers, (
        f'{len(leftovers)} redundant renderer calls remain: {leftovers[:5]}')


def test_wrapped_renders_no_op_block_is_gone():
    """It copied `renderX` onto `window.renderX`, which they already were."""
    assert 'wrappedRenders' not in CORE, (
        'the wrappedRenders block captured nine renderers during boot for no '
        'effect, making all nine undeferrable')


def test_no_optional_calls_on_bare_identifiers_for_lazy_modules():
    """`foo?.()` still throws ReferenceError if `foo` was never declared.

    Optional chaining guards a null/undefined VALUE, not a missing BINDING.
    Only `window.foo?.()` is safe. Every name provided by a lazily loaded
    module must therefore be called through `window.` from eager code.
    """
    lazy_names: set[str] = set()
    for module in PLAN['lazyFiles']:
        code = _strip_comments((JS / module).read_text(encoding='utf-8'))
        lazy_names |= set(re.findall(
            r'(?m)^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', code))
        lazy_names |= set(re.findall(r'window\.([A-Za-z_$][\w$]*)\s*=(?!=)', code))

    offenders = []
    for name in sorted(lazy_names):
        for match in re.finditer(r'(?<![.\w$])' + re.escape(name) + r'\?\.\(', CORE):
            line = CORE[:match.start()].count('\n') + 1
            offenders.append(f'{name} at line ~{line}')
    assert not offenders, (
        'bare optional calls to lazily loaded functions will throw '
        f'ReferenceError: {offenders[:6]}')


# ──────────────────────────────────────────────────────────────────────
#  The payoff, and that it is real
# ──────────────────────────────────────────────────────────────────────
def test_substantially_more_is_deferred_than_before():
    """Batch 29 shipped 18 modules / 504 KB. Regressing below that is a bug."""
    assert len(PLAN['lazyFiles']) >= 30, (
        f'only {len(PLAN["lazyFiles"])} modules deferred; the refactor freed '
        'nine more by deleting a no-op and nine more by deleting duplicates')
    assert PLAN['lazyBytes'] > 700_000, (
        f'only {PLAN["lazyBytes"]} bytes deferred, expected >700 KB')


def test_the_nine_modules_freed_by_deleting_the_no_op_are_deferred():
    """Pins the specific win, so a regression names what broke."""
    # NB 36-dashboard.js is deliberately absent: it is still blocked, by a
    # separate load-time wrapper (`renderDashBody = function(d){...}` at the
    # top level). Listing it here was an error in the first draft of this
    # test, caught because the test failed.
    for module in ('25-skills.js', '20-obsidian.js',
                   '35-deploy.js', '37-pipeline.js', '19-composer.js',
                   '38-system-monitor.js'):
        assert module in PLAN['lazyFiles'], (
            f'{module} was freed by removing the wrappedRenders no-op and '
            'should be lazily loaded')


def test_modules_freed_by_removing_duplicate_calls_are_deferred():
    for module in ('39-mcp-panel.js', '40-loops.js', '31-control-tower.js',
                   '30-workspaces.js', '33-webhooks.js', '34-test-generator.js',
                   '17-database-studio.js', '18-github.js',
                   '15-image-generation.js', '28-kanban.js',
                   '21-template-gallery.js', '22-integrations.js'):
        assert module in PLAN['lazyFiles'], f'{module} should be lazily loaded'


@needs_node
def test_split_plan_matches_a_fresh_analysis():
    """The plan must be re-derived, not hand-edited to make tests pass."""
    result = subprocess.run([_node(), 'scripts/analyse_split.js'],
                            cwd=REPO, capture_output=True, text=True)
    if result.returncode == 2:
        pytest.skip('acorn not installed')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['lazy'] == PLAN['lazy'], (
        'committed split plan is stale; run '
        'python3 scripts/build_bundle.py --refresh-split')


def test_core_boot_modules_are_still_eager():
    """Chat must work before any chunk loads."""
    for module in ('01-app-core.js', '00-pane-registry.js', '00-store.js',
                   '00-render-dedupe.js', '00-chunk-loader.js'):
        assert module not in PLAN['lazyFiles']


def test_remaining_blocked_modules_are_documented():
    """Five modules stay eager for real reasons, not by oversight.

    If this list shrinks that is good news and the test should be updated; if
    it grows, something re-coupled a module into the boot path.
    """
    assert set(PLAN['blocked']) <= {
        '04-workflow-specs.js',      # nav() itself lives here
        '23-plugin-marketplace.js',  # 32-collaboration.js reads it at load time
        '26-swarm.js',               # loadSwarmHistory assigned at load time
        '27-galaxy.js',              # gxGraph is module-level state
        '36-dashboard.js',           # renderDashBody wrapped at load time
    }, f'unexpected newly-blocked modules: {sorted(PLAN["blocked"])}'
