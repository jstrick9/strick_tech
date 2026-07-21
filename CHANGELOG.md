# Changelog

All notable changes to the Strick Tech Agentic OS Platform.

mocked LLM response

## [11.5.1] - 2026-07-21 — Verified Zero-Defect Button & Session Release
### Fixed & Verified via Headless Playwright E2E (`debug_e2e.py`)
- **100% Escaped HTML Attribute Bindings:** Resolved `SyntaxError: Unexpected end of input` quote termination across all buttons (`copy, regenerate, listen, fork, pin, rename, delete, load session`) by converting raw `JSON.stringify(id)` attributes to `&quot;` HTML safe strings (`01-app-core.js:2035` & `5140`).
- **In-App Modal Dialogs (`renameChatSessionModal`, `deleteChatSession`):** Replaced native `window.prompt(...)` (which returns `null` inside macOS Tauri M1/M2/M3/M4 `WKWebView`) with `gmPrompt(...)` and `gmConfirm(...)` in-app modal dialogs (`01-app-core.js:2100`).
- **Session Auto-Creation on Message Load (`session_messages`):** Upgraded `GET /api/sessions/{session_id}/messages` (`backend/routers/sessions.py:270`) to auto-create missing `chat_sessions` entries from `chat_log` when loading past chats, resolving the blank screen (`#chat-empty`) issue when clicking previous conversations.
- **Model Used Badge (`⚡ modelUsed`):** Added dynamic `⚡ [Exact Model Name]` rendering right inside `.msg-meta` for every streaming turn and historical message (`01-app-core.js:586` & `5252`).
- **Multi-Turn Alternating Normalization (`_normalize_messages`):** Added `_normalize_messages()` inside `backend/services/llm.py:172` and deduplicated `sendChat()` history (`01-app-core.js:498`), eliminating multi-turn HTTP 400 errors (`turn 2 no response`).
- **Content-Security-Policy & Highlight.js (`app.py:286`):** Allowed `https://cdnjs.cloudflare.com` across `style-src` and `font-src`, replacing fragmented CommonJS node highlight scripts with the single pre-bundled browser script (`highlight.min.js`). All 26 boot console errors eliminated.
