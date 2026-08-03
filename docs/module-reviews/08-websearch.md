# Module Review 08 — Web Search

**Reviewed:** 2026-08-03 · **Commit:** `3587f09` · **Sidebar position:** Web Search (AI TOOLS)

**Scope:** `backend/routers/websearch.py` (612 lines, 9 endpoints) and
`frontend/js/44-websearch.js` (472 lines).

**Verification:** every finding reproduced against the live DuckDuckGo service, and the
frontend URL issue reproduced in a real DOM before and after the fix.

---

## Findings

### 🔴 1. Web search was completely non-functional

Every query returned:

```json
{"ok": true, "query": "python asyncio tutorial", "results": [], "count": 0}
```

The feature reported success and produced **nothing** — so no error surfaced anywhere, and
anything built on it (grounded completion, research, citations) silently had no sources.

Two independent causes, both confirmed against the live service:

| Cause | Evidence |
|---|---|
| Scraped `lite.duckduckgo.com` with UA `Mozilla/5.0 AgenticOS/6.0` | That endpoint now returns **HTTP 403** to non-browser agents — measured 403, 236 bytes |
| Regex matched a generic `<a href>…</a>` | Not how DuckDuckGo marks up results; even a 200 would have collected navigation chrome |

The documented fallback (`api.duckduckgo.com` instant answers) doesn't rescue it either —
for `"python asyncio tutorial"` it returns an empty `AbstractText` and **zero**
`RelatedTopics`. Every path produced nothing.

**Fixed** — targets `html.duckduckgo.com/html` with a real browser UA and parses the
`result__a` / `result__snippet` markup that endpoint actually emits.

**Before: 0 results. After: 10 results** for the identical query.

### 🟠 2. Result URLs were tracker redirects

Results came back as `//duckduckgo.com/l/?uddg=<percent-encoded-target>` rather than real
destinations, so every citation and result link pointed through a redirect. Added
`_unwrap_ddg_url()`, with tests for wrapped, direct, protocol-relative and malformed input.

### 🟠 3. `javascript:` URLs could survive into a live href

The pane renders every result as `href="${escHtml(url)}"`. **`escHtml()` makes a string safe
as HTML *text* — it does not neutralise a dangerous URL scheme.** Verified in jsdom:

```
href after escHtml: javascript:alert(document.cookie)
is javascript: scheme still live? true
```

These URLs come from **scraped third-party content**, so they're attacker-influenced. A
poisoned search result could ship a clickable `javascript:` link.

**Fixed** — added `safeUrl()` (http/https only, control characters stripped so
`"java\tscript:"` can't slip past, `'#'` otherwise) and routed all four href sites through
it. Defence in depth on the backend too: `_ddg_search` now drops any non-http(s) result URL
and applies the existing SSRF guard to *result* URLs, not just to `/fetch-content`.

### 🟡 4. Eight error paths returned HTTP 200

Including the SSRF rejection, which reported *"URL not allowed: private/internal addresses
are blocked"* with a **success** status. Mapped by class: validation 400, SSRF 403, missing
history entry 404.

---

## Verified working (no change needed)

- **SSRF protection is genuinely strong** — blocks cloud metadata endpoints
  (`169.254.169.254`, `metadata.google.internal`), localhost variants, private ranges, and
  integer/hex-encoded IP bypasses like `2130706433`. All six payload families I tried were
  rejected.
- Grounded completion degrades gracefully without an LLM provider — returns real search
  results with an honest *"Pure search extraction summary"* label rather than pretending to
  have reasoned over them.
- **The frontend is one of the better-written modules I've reviewed** — every fetch checks
  both `response.ok` *and* the body's `ok` flag, and all rendered text is escaped.
- History, suggest, and content extraction all work correctly.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | `/research` slash command routes here — it was returning nothing. |
| **Browser Agent** | Next module in this group; shares the SSRF guard pattern. |
| **Supervisor** | The `researcher` specialist agent depends on web search for its task type. |
| **RAG / Memory** | Grounded completion feeds retrieved content into answers. |

---

## Tests added

`tests/unit/test_57_websearch_module_review.py` — **26 contracts** covering the scraper fix
(UA, endpoint, markup), redirect unwrapping, HTML cleaning, URL filtering (6 SSRF payload
families), frontend URL safety, and status codes.

**Suite:** 2923 backend passed / 12 skipped / **0 failed** · 75 vitest passed · ruff clean.

---

## Recommended follow-ups

1. **This module was broken by an external change, and nothing detected it.** DuckDuckGo
   started returning 403 at some point and the platform kept reporting `ok: true`. Any
   endpoint that scrapes a third party should treat "zero results" as a *degraded* state
   worth surfacing, not a successful empty response. I'd suggest a health signal for it.
2. **Consider a pluggable search provider.** Scraping will break again. Brave Search and
   Tavily both have free API tiers and stable contracts; the DDG scraper could remain the
   no-key default with an optional key-based provider preferred when configured.
3. **`safeUrl()` should be shared.** I added it locally to this module, but the same
   `href="${escHtml(url)}"` pattern likely exists elsewhere — worth promoting to the shared
   helpers alongside `escHtml`.
