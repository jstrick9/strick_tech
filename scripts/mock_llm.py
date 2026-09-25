#!/usr/bin/env python3
"""Mock LLM backends for the no-network preview/test topology.

      python3 scripts/mock_llm.py

  8790 — OpenAI/OpenRouter-compatible: GET /v1/models, POST /v1/chat/completions
         Jev (TypeSafe System One):    POST /v1/systemone
  8791 — Ollama-compatible:            GET /api/tags, POST /api/chat, POST /api/generate

Point a server at them with:

      OPENROUTER_BASE_URL=http://127.0.0.1:8790/v1 \
      JEV_BASE_URL=http://127.0.0.1:8790 \
      OLLAMA_BASE_URL=http://127.0.0.1:8791 \
      OPENROUTER_API_KEY=mock-key \
      TYPESAFE_API_KEY=mock-key \
      python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8787

Contracts worth knowing:

- Every chat completion echoes the requested model, so model-routing fixes
  can be verified in the cost ledger (FinOps pane) after a run.
- Image generation goes through /chat/completions with
  modalities:['image','text'] (see imagegen._do_generate). The mock answers
  those with a base64 PNG data URL in message.images — with a plain text
  reply the router honestly 502s ("did not return an image"), which the
  security sweep (test_sec_10, imagegen injection payloads as the model
  name) rightly flags as a server error.
- This file exists in the repo (not /tmp) because the sandbox it runs in is
  reset periodically: a mock that only ever lived in /tmp had to be
  recreated from memory after every reset, and one recreation got the
  image contract wrong, costing a full security-suite debug cycle.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

MODELS = [
    "anthropic/claude-3.5-sonnet", "openai/gpt-4o", "openai/gpt-4o-mini",
    "google/gemini-2.5-pro", "x-ai/grok-3", "nousresearch/hermes-3-llama-3.1-405b",
]


def _echo_schema_object(prompt_text):
    """Build a valid JSON object echoing the top-level keys of the example
    schema embedded in the prompt, with plausible values.

    Routes like hitl.assess-confidence and knowledge-graph.extract show the
    model an example object and demand ONLY valid JSON. A mock that answers
    prose can never exercise their success paths — the routes honestly
    refuse (by design). Echoing the advertised schema is the minimum a
    model must do to be useful to them.
    """
    # The schema follows the phrase "Return JSON:" — start the search there.
    # A prompt can legitimately contain EARLIER JSON (hitl embeds
    # `Context: {"sensitivity": ...}` before the schema), and echoing that
    # first block produces an object without the keys the route validates.
    low = prompt_text.lower()
    idx = low.rfind("return json")
    start = prompt_text.find("{", idx if idx >= 0 else 0)
    if start < 0:
        return None
    depth, end = 0, -1
    for i in range(start, len(prompt_text)):
        if prompt_text[i] == "{":
            depth += 1
        elif prompt_text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    body = prompt_text[start + 1:end]

    # split the object body on top-level commas
    parts, depth, buf, in_str = [], 0, [], False
    for ch in body:
        if ch == '"':
            in_str = not in_str
        if not in_str:
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))

    import re as _re
    out = {}
    for part in parts:
        m = _re.match(r'\s*"([\w-]+)"\s*:\s*(.*)', part, _re.DOTALL)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith("["):
            out[key] = []
        elif raw.startswith("{"):
            out[key] = {}
        elif "|" in raw:
            out[key] = raw.split("|")[0].strip().strip("\"' ")
        elif "true" in raw.lower() or "false" in raw.lower():
            out[key] = True
        elif _re.search(r"\d", raw):
            out[key] = 0.85
        else:
            out[key] = "mock"
    return out or None


def structured_answer(messages):
    """Deterministic structured replies for prompts that demand them.

    The app has a dozen routes that ask the model for SQL, code sections,
    or JSON — and honestly refuse (502/422/503) when the reply does not
    parse. A mock that always answers "Mock LLM response." can only ever
    exercise the refusal branches. These marker-driven answers (same
    philosophy as the image special-case below) let both branches be
    covered: success shapes against this mock, refusals by the routes'
    own tests.
    """
    if not isinstance(messages, list):
        return None
    text = " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
    low = text.lower()

    if "return only valid json" in low:
        obj = _echo_schema_object(text)
        if obj is not None:
            import json as _json
            return _json.dumps(obj)
    if "return only sql" in low:
        return (
            "CREATE TABLE mock_items (\n"
            "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),\n"
            "  name text NOT NULL,\n"
            "  created_at timestamptz DEFAULT now()\n"
            ");\n"
            "CREATE INDEX mock_items_name_idx ON mock_items (name);\n"
            "ALTER TABLE mock_items ENABLE ROW LEVEL SECURITY;\n"
            "INSERT INTO mock_items (name) VALUES ('seed');"
        )
    if "### checkout_html" in low:
        return (
            "### CHECKOUT_HTML\n"
            "<!doctype html><html><body><h1>Mock checkout</h1>\n"
            "<script src=\"https://js.stripe.com/v3\"></script></body></html>\n"
            "### WEBHOOK_PYTHON\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "async def stripe_webhook(payload):\n"
            "    return {'received': True}"
        )
    if '<file path=' in low:
        return (
            '<FILE path="mock_integration.js">\n'
            "export function mockIntegration() { return true; }\n"
            "</FILE>\n"
            '<FILE path="README.md">\n'
            "# Mock integration\n"
            "</FILE>"
        )
    if "return html first" in low:
        return (
            "<!doctype html><html><body><h1>Mock login</h1></body></html>\n\n"
            "# config.py\nMOCK_AUTH_PROVIDER = 'nextauth'"
        )
    return None


def jev_systemone_answer(req):
    """Deterministic mock for POST /v1/systemone (Jev / TypeSafe System One).

    Answers are derived from sha1(state + question key) so they are STABLE:
    the same request always gets the same answer, and tests can assert exact
    probabilities without a live key. Shape mirrors the documented API:

        {"model": ..., "answers": {key: {"type", ...fields, "confidence",
         "probabilities"}}, "usage": {"input_tokens", "output_tokens"}}

      - noul   -> noul in 0.05 steps (hash-derived)
      - choice -> probabilities split by per-option hash weights; the argmax
                  is the choice; confidence = its probability
      - score  -> same weighting over the ordered levels; score = argmax index
    """
    import hashlib

    def h(salt: str, key: str, state: str) -> int:
        return int.from_bytes(hashlib.sha1(f"{salt}|{state}|{key}".encode()).digest()[:4], "big")

    state = str(req.get("state") or "")
    answers = {}
    for key, q in (req.get("questions") or {}).items():
        qtype = str((q or {}).get("type") or "")
        if qtype == "noul":
            answers[key] = {"type": "noul", "noul": round((h("noul", key, state) % 21) / 20.0, 2)}
        elif qtype == "choice":
            crit = (q or {}).get("criteria") or {}
            weights = {str(opt): (h("c", str(opt), state) % 1000) + 1 for opt in crit}
            total = sum(weights.values())
            probs = {opt: round(w / total, 4) for opt, w in weights.items()}
            top = max(probs, key=probs.get)
            answers[key] = {
                "type": "choice", "choice": top,
                "confidence": round(probs[top], 2), "probabilities": probs,
            }
        elif qtype == "score":
            crit = (q or {}).get("criteria") or []
            weights = [(h("s", f"{key}#{i}", state) % 1000) + 1 for i in range(len(crit))]
            total = sum(weights)
            probs = {str(i): round(w / total, 4) for i, w in enumerate(weights)}
            top = max(probs, key=probs.get)
            answers[key] = {
                "type": "score", "score": float(top),
                "confidence": round(probs[top], 2),
                "legend": {str(i): str(c) for i, c in enumerate(crit)},
                "probabilities": probs,
            }
        else:
            answers[key] = {"type": qtype, "error": "unknown question type"}
    return {
        "model": "jev-mock-1.0",
        "answers": answers,
        "usage": {
            "input_tokens": max(1, len(state) // 4),
            "output_tokens": max(1, 8 * len(answers)),
        },
    }


def make_handler(port_kind):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if port_kind == "openai":
                if self.path.startswith("/v1/models"):
                    self._send({"data": [{"id": m} for m in MODELS]})
                elif self.path.startswith("/v1/auth/key"):
                    # r55: the backend's key-verification path (honouring
                    # OPENROUTER_BASE_URL) calls this authenticated endpoint;
                    # mirror OpenRouter's shape so save-and-verify works
                    # against the mock.
                    self._send({"data": {"label": "mock-key", "usage": 0, "limit": None}})
                else:
                    self._send({"error": "not found"}, 404)
            else:
                if self.path.startswith("/api/tags"):
                    self._send({"models": [{"name": "mockllama:8b"}, {"name": "mockqwen:7b"}]})
                else:
                    self._send({"error": "not found"}, 404)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                req = {}
            if port_kind == "openai":
                if self.path.startswith("/v1/systemone"):
                    # Jev (TypeSafe System One) mock — see
                    # jev_systemone_answer() below and services/jev.py.
                    # Reachable with JEV_BASE_URL=http://127.0.0.1:8790
                    self._send(jev_systemone_answer(req))
                    return
                special = structured_answer(req.get("messages"))
                msg = {"role": "assistant", "content": special or "Mock LLM response."}
                mods = req.get("modalities") or []
                m = str(req.get("model") or "")
                if "image" in mods or any(k in m.lower() for k in ("image", "flux", "dall", "stable")):
                    msg = {"role": "assistant", "content": "", "images": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + TINY_PNG}}]}
                if req.get("stream"):
                    # r52: SSE like OpenRouter — delta chunks, a usage-bearing
                    # final chunk, then [DONE]. Lets the app's streaming path
                    # (llm._stream_impl) be exercised against this mock.
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()

                    def sse(obj):
                        self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())

                    for piece in ("Mock ", "LLM ", "streamed ", "response."):
                        sse({"id": "mock-chatcmpl-1", "object": "chat.completion.chunk",
                             "model": req.get("model", "mock/mock-large"),
                             "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
                    sse({"id": "mock-chatcmpl-1", "object": "chat.completion.chunk",
                         "model": req.get("model", "mock/mock-large"),
                         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                self._send({
                    "id": "mock-chatcmpl-1", "object": "chat.completion",
                    "model": req.get("model", "mock/mock-large"),
                    "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
                })
            else:
                if self.path.startswith("/api/chat"):
                    special = structured_answer(req.get("messages"))
                    self._send({"model": req.get("model", "mockllama:8b"),
                                "message": {"role": "assistant", "content": special or "Mock ollama chat response."},
                                "done": True})
                else:
                    # /api/generate carries a bare prompt, not messages
                    special = structured_answer([{"role": "user", "content": req.get("prompt", "")}])
                    self._send({"model": req.get("model", "mockllama:8b"),
                                "response": special or "Mock ollama generate response.",
                                "done": True})
    return H


def serve(port, kind):
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(kind)).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve, args=(8790, "openai"), daemon=True).start()
    serve(8791, "ollama")
