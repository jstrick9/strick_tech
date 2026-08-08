"""A fake Ollama-compatible provider that fails in specific, chosen ways.

The point is to exercise the agentic core's behaviour when a model is
CONFIGURED and REACHABLE but misbehaves -- which is the common real-world case
and the one no audit in this repo has ever covered. Every existing probe tests
"no provider" (a clean 503) or "server down" (a transport error).

Modes, selected by the MODE env var:

  truncate  stream a few tokens, then close the connection mid-response.
            The user sees a half-written answer and no error.
  stall     accept the request and never send anything. Tests whether the UI
            has any timeout at all, or spins forever.
  garbage   return 200 with a body that is not the expected shape.
  error500  a hard provider failure after the request was accepted.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MODE = os.getenv('MODE', 'truncate')
PORT = int(os.getenv('PORT', '11434'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        # Ollama probes /api/tags to decide whether the provider is alive.
        if self.path.startswith('/models'):
            body = json.dumps({'data': [{'id': 'fake/model'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith('/api/tags'):
            body = json.dumps({'models': [{'name': 'fake:latest'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(length)
        # OpenRouter speaks SSE with an OpenAI-shaped delta; Ollama speaks
        # NDJSON. Both are served so the same four failure modes can be driven
        # down EITHER provider path -- the primary one had no test seam at all
        # until OPENROUTER_BASE_URL was made overridable.
        self.openai_style = '/chat/completions' in self.path

        if MODE == 'error500':
            body = b'{"error":"provider exploded"}'
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if MODE == 'garbage':
            body = b'{"unexpected":"shape","no_message_field":true}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if MODE == 'stall':
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            time.sleep(600)
            return

        # truncate: a few valid chunks, then hang up mid-answer.
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()
        for word in ('The ', 'answer ', 'is ', 'that '):
            if getattr(self, 'openai_style', False):
                chunk = 'data: ' + json.dumps({
                    'choices': [{'delta': {'content': word}}],
                }) + '\n\n'
            else:
                chunk = json.dumps({
                    'message': {'role': 'assistant', 'content': word},
                    'done': False,
                }) + '\n'
            try:
                self.wfile.write(chunk.encode())
                self.wfile.flush()
            except Exception:
                return
            time.sleep(0.05)
        # No `done: true`, no further data -- just close.
        try:
            self.wfile.close()
        except Exception:
            pass


HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
