# Module Review 01 — Chat

**Reviewed:** 2026-08-03 · **Commit:** `ad8df07` · **Sidebar position:** 1 of 67

**Scope (per your direction — everything reachable from the Chat pane):**
`backend/routers/chat.py`, `backend/routers/sessions.py`, `backend/services/llm.py`
(chat paths), the chat pane in `index.html`, `01-app-core.js` (sendChat and chat
surface), `56-chat-history.js`, attachments/vision, RAG + memory toggle, persona
and model selectors, slash commands, voice/TTS entry points.

**Verification method:** installed Ollama + `qwen2.5:0.5b` **inside the sandbox** and
exercised every path against a real model. All findings below were reproduced live,
not inferred from reading code.

> Note: my sandbox is an isolated cloud VM, so I could not reach the Ollama on your
> local machine (`localhost:11434` resolves to my container). Installing a small model
> locally gave equivalent — and fully reproducible — end-to-end coverage.

---

## Findings

### 🔴 1. Long-term memory was poisoning itself

**The worst bug in this module.** The memory-ingest guard was only a length check:

```python
if full_text and len(full_text) > 50:   # ← the ONLY gate
    memory_db.memory_add(source=f'chat:{agent_id}', content=full_text[:800], ...)
```

So every failure mode was permanently written to the knowledge store as if it were
fact — `⚠️ No OPENROUTER_API_KEY set…` stubs, `[stream error]…` text, provider
fallback notices. Those rows were then retrieved by the `use_rag` lookup and injected
into the system prompt of *later* conversations.

**Measured on this machine: 18 of 19 stored chat memories were error text.** The RAG
store was almost entirely garbage, and actively degrading answers.

**Fixed:** ingestion is gated on a genuine completion (the `stub`/`error` SSE flags,
plus a text-marker check). Retrieval is filtered too — the poison also arrives from
*other* subsystems (`source='webhook:…'` rows held the same API-key error), so a
chat-side guard alone was insufficient. The 18 poisoned rows were purged.

### 🔴 2. Image attachments never reached the model

The UI read the full base64 image, then sent **the first 80 characters as plain text**:

```js
return `\n\n[Attached image: ${item.file.name}]\n[image data: ${item.text.slice(0, 80)}...]`;
```

80 chars of a data URL is just the header (`data:image/png;base64,iVBORw0KGgo…`).
Vision was structurally impossible from Chat, on any model, however capable.

**Fixed:** images are sent as proper OpenAI `image_url` content parts — a shape
`llm._normalize_messages()` already supported. The router now accepts list-form
`message` (deriving a text view for logging/slash-parsing/RAG rather than calling
`.strip()` on a list, which would have crashed) and permits image-only sends.
Verified the data URL survives intact all the way to the provider call.

### 🟠 3. The "⚡ Stream" toggle was decorative

`toggleStream()` flipped `S.useStream` and toasted *"responses appear all at once"* —
but the flag was never included in the request body, and the backend always streamed.
The control did nothing.

**Fixed** end to end. Verified: **25 SSE frames** with `stream:true` vs **exactly 1**
with `stream:false`, usage and persistence identical in both modes.

### 🟠 4. `/clear` reported success while deleting nothing

It emitted `✅ Chat history cleared.` and wiped only the browser DOM. Rows stayed in
`chat_log`, so reloading the page or reopening the session brought the "cleared"
conversation straight back — and the model kept receiving it as context. A user
clearing a conversation for privacy reasons would have been actively misled.

**Fixed:** really deletes, resets `message_count`, distinguishes an already-empty
conversation, and reports failure honestly instead of a false success (the UI
transcript is only wiped when the server actually deleted something).

### 🟠 5. Token/cost tracking was structurally impossible

`_log_chat()` accepted `tokens`/`cost` parameters, but the streaming path never passed
them — so **every row was 0**, and `/api/cost`, the status-bar spend readout and every
FinOps surface had nothing to report. The data was available and being discarded:
Ollama returns `eval_count`/`prompt_eval_count` on its final chunk, and OpenRouter
returns a usage block when asked.

**Fixed:** request `stream_options.include_usage` from OpenRouter, capture both
providers' counts from the terminal SSE frame, persist them. Verified **1106 real
tokens** recorded and surfaced through `/api/cost`. (Cost correctly stays `$0` for
free local inference.)

Also hardened: the OpenRouter usage chunk arrives with `choices: []`, so the previous
`chunk['choices'][0]` indexing would have thrown and lost the payload.

### 🟠 6. Stop button double-fired and dropped the partial reply

`index.html` had a hardcoded `onclick="sendChat()"` while `sendChat()` *additionally*
attached a stop handler via `addEventListener` to the same element. Clicking Stop ran
**both** — aborting the stream and instantly firing a duplicate request.

Separately, a stopped response was rendered on screen but never pushed to
`S.chatHistory`, so the assistant turn the user could still see was invisible to the
model on the next message — the conversation silently desynchronised after any Stop.

**Fixed:** one delegated dispatcher (`window.onChatSendClick`) that branches on
streaming state, so send and stop can never both run for a single click. Partial
replies are retained in history; a bubble aborted before the first token is removed
rather than left blank.

### 🟡 7. UX — `/models` hid the models that actually work

It listed only the hardcoded OpenRouter registry. A local-only user was shown a menu
of cloud models they had no key for, and **none** of the models installed on their
machine. Now lists local Ollama models first, annotates whether a cloud key exists,
and guides setup when nothing is usable.

---

## Verified working (no change needed)

- SSE streaming, cancel/abort plumbing, session auto-titling, history drawer
  (folder tree + date grouping, pagination, pin/rename/delete, context menus)
- Slash commands `/help`, `/goal`, `/research`, `/code`, `/review`, `/ship`, `/swarm`,
  `/memory` — including real goal creation via `goals_v2`
- Attachment intake: 5-file cap, 250 KB text / 4 MB document limits, PDF/DOCX
  server-side extraction, removable chips, drag-and-drop
- Tier-1 hierarchy + steering injection (~3.7k chars on every message — intentional,
  matches the documented "applies to every conversation" behavior)
- `escHtml()` discipline on rendered message content

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Memory / Galaxy / RAG** | Store cleaned (18 rows purged); retrieval now filters junk from *all* sources. Quality of grounded answers improves platform-wide. |
| **FinOps / Dashboard / Analytics** | These panes were empty because chat never recorded usage. They now receive real token data — worth re-reviewing when I reach them. |
| **Webhooks** | Confirmed as a *second* producer of poisoned memories (`webhook:…` rows holding API-key errors). Its own ingest path needs the same guard — flagged for that module's review. |
| **Swarm / Composer / Studio** | Share `llm.stream()`; they inherit the usage-reporting and empty-`choices` hardening. |
| **Sessions** | `message_count` is now correctly reset by `/clear`. |

---

## Tests added

- `tests/unit/test_46_chat_module_review.py` — **19** contracts covering error-text
  detection, the ingestion guard, usage capture/persistence for both providers,
  `/clear` honesty, and `/models` content.
- `frontend/tests/chat-send-stop.test.js` — **3** jsdom tests proving the send/stop
  dispatcher can't double-fire (written failing first, against the real bug).
- `tests/unit/test_47_chat_file_intake.py` — extended to guard the image-parts fix and
  pin the lossy 80-char truncation permanently shut.

**Suite status:** 2683 backend passed / 12 skipped / **0 failed**; 45 vitest passed;
ruff clean.

---

## Recommended follow-ups (not done — out of module scope)

1. **Apply the memory-ingest guard at the `memory_db.memory_add()` layer**, not
   per-caller. Chat and Webhooks both poisoned the store independently; a shared
   choke point would prevent the next producer from doing it again. Worth doing once
   I've seen the other ingest sites.
2. `chat_log.message` is truncated to 4000 chars on write while the API accepts
   16000 — long replies are silently clipped in history. Needs a product decision on
   the right limit before changing.
3. Consider persisting `prompt_tokens`/`completion_tokens` separately (currently only
   the total is stored), which FinOps will want for input-vs-output cost attribution.
