"""First-run honesty (r93, #257) — the chat cannot fake an AI reply.

THE DEFECT THIS FILE PINS
─────────────────────────
With no AI connection configured, POST /api/chat streams its configuration
help ("⚠️ No OPENROUTER_API_KEY set…") over the same SSE channel as a real
model reply. Chat rendered that text as an ASSISTANT bubble — with a model
badge naming a model that was never called — and pushed it into chatHistory
as a genuine assistant turn. A brand-new user's very first message therefore
got a fake AI answer that was actually setup instructions, and the platform
logged it as a conversation turn.

THE FIX, PINNED HERE AT THE USER-VISIBLE LEVEL
─────────────────────────────────────────────
  1. sendChat gates on a real connection state (window.chatConnectionReady,
     fed by the same readiness poll that paints the header label). No
     connection -> an in-chat Connect card: a SYSTEM card, not an assistant
     bubble; the draft stays in the input; nothing is sent; nothing is
     recorded in history.
  2. The card's buttons route to Settings -> Connect AI (the 'api' tab).
  3. Belt and braces: if a stub stream ever reaches the UI anyway (a
     connection that vanishes server-side between the gate and the request —
     the one race the gate cannot close), it renders as a system notice with
     no model badge and is NOT pushed into chatHistory.
  4. Completing onboarding without a connection ends with an honest handoff
     (toast + connect card) instead of pure celebration.

These tests skip when a connection IS configured — that is a legitimate
deployment state, not a failure.
"""

from __future__ import annotations

import pytest

BASE = 'http://127.0.0.1:8787'


@pytest.fixture(scope='module')
def shared_page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


@pytest.fixture
def loaded(shared_page):
    """App booted, first-run overlays dismissed, readiness settled."""
    page = shared_page
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    # Let the readiness poll paint at least once. NOTE: wait_for_function
    # cannot be used for this predicate — under the app's strict CSP
    # (script-src 'self', no unsafe-eval) Playwright's string-predicate path
    # is refused for expressions with logical operators, while plain
    # page.evaluate is not. Poll from Python instead.
    import time as _time
    _deadline = _time.time() + 15
    while _time.time() < _deadline:
        if page.evaluate('Boolean(window._chatConnection && window._chatConnection.checked)'):
            break
        page.wait_for_timeout(250)
    page.evaluate("""
        () => {
            for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
                const el = document.getElementById(id);
                if (el) el.remove();
            }
            try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
            document.getElementById('connect-ai-card')?.remove();
        }
    """)
    page.wait_for_timeout(300)
    return page


def _connection_ready(page) -> bool:
    return bool(page.evaluate('window.chatConnectionReady ? window.chatConnectionReady() : true'))


def test_send_without_connection_shows_connect_card_not_a_fake_reply(loaded):
    if _connection_ready(loaded):
        pytest.skip('an AI connection is configured on this server')
    page = loaded

    history_before = page.evaluate('(window.S?.chatHistory || []).length')
    agent_before = page.evaluate(
        "document.querySelectorAll('#chat-messages .msg.agent:not(.system-connect-card)').length"
    )
    # Watch the wire: the entire point is that NOTHING is sent.
    chat_posts = []
    page.on('request', lambda r: chat_posts.append(r.url) if r.method == 'POST' and r.url.rstrip('/').endswith('/api/chat') else None)

    page.fill('#chat-input', 'Hello! What can you do?')
    page.press('#chat-input', 'Enter')
    page.wait_for_timeout(1500)

    card = page.query_selector('#connect-ai-card')
    assert card is not None, 'the Connect card must replace the send'
    assert 'Connect your AI' in card.inner_text()

    # The draft is preserved verbatim — the card promises exactly that.
    assert page.input_value('#chat-input') == 'Hello! What can you do?'

    # No assistant bubble was added for this send (delta, not absolute: a
    # restored session may legitimately contain earlier assistant messages).
    agent_after = page.evaluate(
        "document.querySelectorAll('#chat-messages .msg.agent:not(.system-connect-card)').length"
    )
    assert agent_after == agent_before, 'a stub/help reply must never render as an assistant message'

    # Nothing was recorded as a conversation turn.
    history_after = page.evaluate('(window.S?.chatHistory || []).length')
    assert history_after == history_before, 'a blocked send must not touch chatHistory'

    # And nothing left the page for the chat endpoint.
    assert chat_posts == [], f'blocked send still issued POST /api/chat: {chat_posts}'


def test_connect_card_routes_to_the_connect_ai_tab(loaded):
    if _connection_ready(loaded):
        pytest.skip('an AI connection is configured on this server')
    page = loaded
    page.fill('#chat-input', 'test')
    page.press('#chat-input', 'Enter')
    page.wait_for_timeout(800)
    card = page.query_selector('#connect-ai-card')
    assert card is not None
    card.query_selector('.connect-card-actions .btn').click()
    page.wait_for_timeout(800)
    pane = page.evaluate("window.NavigationState ? window.NavigationState.get() : ''")
    assert pane == 'settings', f'expected settings, got {pane!r}'
    active_tab = page.evaluate(
        "(document.querySelector('.settings-nav-item.active')||{}).id || ''"
    )
    assert active_tab in ('settings-nav-api', 'settings-nav-connection', 'settings-nav-ai'), (
        f'the Connect AI tab must be active, got {active_tab!r}'
    )


def test_connect_card_is_dismissible_and_does_not_block_the_input(loaded):
    if _connection_ready(loaded):
        pytest.skip('an AI connection is configured on this server')
    page = loaded
    page.fill('#chat-input', 'draft stays')
    page.press('#chat-input', 'Enter')
    page.wait_for_timeout(800)
    assert page.query_selector('#connect-ai-card') is not None
    page.click('.connect-card-dismiss')
    page.wait_for_timeout(300)
    assert page.query_selector('#connect-ai-card') is None
    # The draft survived dismissal, and the input still accepts typing.
    assert page.input_value('#chat-input') == 'draft stays'
    page.fill('#chat-input', 'still typing')
    assert page.input_value('#chat-input') == 'still typing'


def test_a_stub_stream_if_it_ever_arrives_is_a_system_notice_not_a_reply(loaded):
    """The one race the gate cannot close: a connection that is configured
    client-side (so the gate passes) but gone server-side (so the backend
    streams its stub help). Simulated by forcing the client state, which is
    exactly what a vanishing key looks like to sendChat."""
    page = loaded
    # Force the gate to pass, send, then restore whatever was there.
    page.evaluate("""
        () => {
            window.__savedConnection = window._chatConnection;
            window._chatConnection = { checked: true, cloudReady: true, localModels: 0, at: Date.now() };
        }
    """)
    try:
        history_before = page.evaluate('(window.S?.chatHistory || []).length')
        badge_before = page.evaluate("document.querySelectorAll('#chat-messages .model-used-tag').length")
        page.fill('#chat-input', 'race condition probe')
        page.press('#chat-input', 'Enter')
        # The stub stream is short; give it time to finish.
        page.wait_for_timeout(4000)

        system = page.query_selector('#chat-messages .msg.system-connect-card')
        assert system is not None, (
            'a stub stream must render as a system notice, not an assistant reply'
        )
        badge_after = page.evaluate("document.querySelectorAll('#chat-messages .model-used-tag').length")
        assert badge_after == badge_before, 'no model badge may be added: no model was called'
        assert 'No AI connection is configured' in system.inner_text()

        # The USER turn legitimately enters history (the message was sent).
        # The stub must NOT become an assistant turn: history grows by exactly
        # one, and the last entry is the user's own message.
        history_after = page.evaluate('(window.S?.chatHistory || []).length')
        assert history_after == history_before + 1, (
            'history grew by more than the user turn — the stub became a conversation turn'
        )
        last_role = page.evaluate('(window.S?.chatHistory || []).slice(-1)[0]?.role')
        assert last_role == 'user', (
            f'the last history entry must be the user turn, not {last_role!r}'
        )
    finally:
        page.evaluate("""
            () => {
                if (window.__savedConnection) window._chatConnection = window.__savedConnection;
            }
        """)


def test_completing_onboarding_without_a_connection_ends_with_the_connect_card(loaded):
    """The wizard may complete, but it may not celebrate its way past the
    fact that no AI is connected: the ending is an honest handoff — a toast
    that says what is still missing, and the Connect card in chat.

    The status endpoint is routed to report an incomplete onboarding (what a
    real first-run server reports for a new user) because the live server's
    own profile is long since complete."""
    page = loaded
    if _connection_ready(loaded):
        pytest.skip('an AI connection is configured on this server')

    import json as _json

    def mock_status(route):
        route.fulfill(status=200, content_type='application/json',
                      body=_json.dumps({'complete': False}))

    page.route('**/api/onboarding/status', mock_status)
    try:
        page.goto(BASE)
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(3500)

        for _ in range(10):
            if not page.query_selector('#ob-next'):
                break
            try:
                page.click('#ob-next', timeout=2000)
                page.wait_for_timeout(250)
            except Exception:
                break
        # Toasts + the 600ms-delayed card.
        page.wait_for_timeout(1800)

        state = page.evaluate("""() => ({
            onboarded: localStorage.getItem('agentic_os_onboarded'),
            pane: window.NavigationState ? window.NavigationState.get() : null,
            card: !!document.querySelector('.system-connect-card'),
            oneMoreThing: [...document.querySelectorAll('[class*=toast]')]
                .some(t => t.textContent.includes('One more thing')),
        })""")
        assert state['onboarded'] == 'true', 'the wizard still completes — this is a handoff, not a block'
        assert state['pane'] == 'chat'
        assert state['oneMoreThing'], 'the handoff toast must say what is still missing'
        assert state['card'], 'the Connect card must be waiting in chat'
        assert page.evaluate(
            "document.querySelectorAll('#chat-messages .msg.agent').length"
        ) == 0
    finally:
        page.unroute('**/api/onboarding/status')


def test_gm_dialog_confirm_buttons_actually_confirm(loaded):
    """A confirm button that silently does nothing is the worst failure mode
    in the file's vocabulary, and it really happened: a jsArg helper collision
    (#257) rendered dialog button arguments unquoted, the delegation shim
    refused them, and every gm dialog's Confirm/Delete/Cancel was dead —
    trusted clicks included. The delete journey above covers kanban; this pins
    the dialog mechanism itself, which every pane shares."""
    page = loaded
    # Fire-and-forget: gmDanger resolves on the user's click, and
    # page.evaluate would otherwise await that promise until timeout.
    page.evaluate("""() => {
        window.gmDanger('Test dialog', 'Confirm to close this dialog.', 'Delete');
        return null;
    }""")
    page.wait_for_timeout(500)
    btn = page.query_selector('#gm-btns button.btn-danger')
    assert btn is not None, 'the danger-confirm button must render'
    assert btn.get_attribute('data-act-click') == '_gm_click("ok")', (
        'the confirm action must carry a QUOTED literal argument — the unquoted '
        'form is refused by the delegation shim and the button does nothing'
    )
    btn.click()
    page.wait_for_timeout(400)
    assert page.evaluate(
        "document.getElementById('gmodal').style.display"
    ) == 'none', 'clicking Confirm must resolve the dialog'
