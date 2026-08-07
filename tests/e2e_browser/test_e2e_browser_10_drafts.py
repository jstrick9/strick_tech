"""Long-form input is not lost to an accidental reload.

THE GAP
───────
`00-drafts.js` saves and restores any field tagged `data-draft="<key>"`, and it
observes nodes added after load. The mechanism was fine; COVERAGE was not.

Driving all 28 panes and inspecting every visible textarea found **14 long-form
inputs, 5 protected, 9 not** -- and the unprotected ones were where users write
the most:

    #comp-instruction    Composer -- the whole point of the pane
    #t1-editor-textarea  Hierarchy note editor
    #img-prompt          Image generator prompt
    #eval-prompt         Evals -- the prompt under test
    #eval-response       Evals -- the response under test
    #mcp-agent-prompt    MCP agent task
    #mcp-args            MCP tool arguments (hand-written JSON)

Losing a carefully written Composer instruction to a stray Cmd+R is exactly the
failure 00-drafts.js exists to prevent. These fields simply never opted in.

The Studio fallback textarea is deliberately excluded: Code Studio already
autosaves its buffer 600ms after the last keystroke, so a draft copy would be a
second source of truth that can disagree with the file on disk.
"""
import pytest

BASE = "http://127.0.0.1:8787"

_DISMISS = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""


@pytest.fixture
def app(page):
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(1500)
    page.evaluate(_DISMISS)
    page.wait_for_timeout(300)
    return page


# Fields that hold expensive, hand-written input and must be recoverable.
EXPECTED_DRAFTS = [
    ('composer', 'comp-instruction'),
    ('imagegen', 'img-prompt'),
    ('evals', 'eval-prompt'),
    ('evals', 'eval-response'),
    ('mcp', 'mcp-agent-prompt'),
    ('mcp', 'mcp-args'),
]


@pytest.mark.parametrize('pane,field', EXPECTED_DRAFTS)
def test_expensive_inputs_are_draft_protected(app, pane, field):
    app.evaluate("p => window.nav(p)", pane)
    app.wait_for_timeout(1600)
    tagged = app.evaluate("""(id) => {
        const el = document.getElementById(id);
        if (!el) return null;
        return el.hasAttribute('data-draft') ? el.getAttribute('data-draft') : false;
    }""", field)
    if tagged is None:
        pytest.skip(f'#{field} not rendered in this build')
    assert tagged, (
        f'#{field} on the {pane} pane has no data-draft key, so anything typed '
        'into it is lost on reload'
    )


def test_a_draft_survives_a_full_page_reload(app):
    """The whole journey, not just the attribute.

    A `data-draft` tag proves nothing on its own -- the save could be
    debounced away, the restore could run before the pane renders, or the key
    could collide. This types, reloads, and reads the value back.
    """
    text = 'Build me a multi-tenant billing dashboard with Stripe webhooks'

    app.evaluate("() => window.nav('composer')")
    app.wait_for_timeout(1800)
    typed = app.evaluate("""(t) => {
        const el = document.getElementById('comp-instruction');
        if (!el) return false;
        el.value = t;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
    }""", text)
    if not typed:
        pytest.skip('composer instruction field not present')

    app.wait_for_timeout(1200)   # let the debounce fire
    keys = app.evaluate("""() => Object.keys(localStorage)
        .filter(k => k.startsWith('agentic_draft:'))""")
    assert any('composer' in k for k in keys), f'draft was never saved: {keys}'

    app.reload(wait_until='domcontentloaded')
    app.wait_for_timeout(2500)
    app.evaluate(_DISMISS)
    app.evaluate("() => window.nav('composer')")
    app.wait_for_timeout(2000)

    restored = app.evaluate(
        "() => { const el = document.getElementById('comp-instruction'); return el ? el.value : null; }")
    assert restored == text, (
        f'the draft did not come back after reload.\n  wanted: {text!r}\n  got:    {restored!r}'
    )


def test_most_long_form_inputs_are_protected(app):
    """A coverage floor, so a newly added textarea does not quietly regress it.

    Asserted as a ratio rather than a fixed list: the exact set changes as
    panes evolve, but "most long-form input is recoverable" should not.
    """
    panes = [p for p in app.evaluate(
        "() => [...document.querySelectorAll('#sidebar .nav-item')]"
        "        .map(e => e.getAttribute('data-nav'))") if p]

    total = protected = 0
    unprotected = []
    for pane in panes:
        app.evaluate("p => window.nav(p)", pane)
        app.wait_for_timeout(500)
        rows = app.evaluate("""() => [...document.querySelectorAll('textarea')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({ id: el.id || '-', draft: el.hasAttribute('data-draft') }))""")
        for r in rows:
            total += 1
            if r['draft']:
                protected += 1
            else:
                unprotected.append(f"{pane}#{r['id']}")

    assert total >= 8, f'only found {total} textareas; did the panes render?'
    assert protected / total >= 0.75, (
        f'only {protected}/{total} long-form inputs are draft-protected. '
        f'Unprotected: {sorted(set(unprotected))[:10]}'
    )
