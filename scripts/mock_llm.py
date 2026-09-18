#!/usr/bin/env python3
"""Mock LLM backends for the no-network preview/test topology.

      python3 scripts/mock_llm.py

  8790 — OpenAI/OpenRouter-compatible: GET /v1/models, POST /v1/chat/completions
  8791 — Ollama-compatible:            GET /api/tags, POST /api/chat, POST /api/generate

Point a server at them with:

      OPENROUTER_BASE_URL=http://127.0.0.1:8790/v1 \
      OLLAMA_BASE_URL=http://127.0.0.1:8791 \
      OPENROUTER_API_KEY=mock-key \
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
                msg = {"role": "assistant", "content": "Mock LLM response."}
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
                    self._send({"model": req.get("model", "mockllama:8b"),
                                "message": {"role": "assistant", "content": "Mock ollama chat response."},
                                "done": True})
                else:
                    self._send({"model": req.get("model", "mockllama:8b"),
                                "response": "Mock ollama generate response.", "done": True})
    return H


def serve(port, kind):
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(kind)).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve, args=(8790, "openai"), daemon=True).start()
    serve(8791, "ollama")
