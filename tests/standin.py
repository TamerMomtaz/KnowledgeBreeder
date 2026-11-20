"""A stand-in model server for tests: it speaks the two protocols kb uses and answers what the test tells it to.

It runs on 127.0.0.1 in a thread. No model is behind it. It proves the plumbing, not the quality of any answer.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class StandIn:
    def __init__(self, reply=None, models=("small", "big")):
        self.reply = reply or (lambda model, system, user: "{}")
        self.models = list(models)
        self.seen: list[dict] = []                          # every request: path, headers, body
        self.redirect_to: str | None = None                 # when set, /hop/... answers 307 to this address
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj, headers=()):
                raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                outer.seen.append({"path": self.path, "headers": dict(self.headers), "body": None})
                if self.path.split("?")[0].endswith("/models"):
                    return self._send(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in outer.models]})
                self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                outer.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
                path = self.path.split("?")[0]
                if path.startswith("/hop/") and outer.redirect_to:
                    return self._send(307, {}, [("Location", outer.redirect_to)])
                if path.endswith("/chat/completions"):
                    system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
                    user = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
                    text = outer.reply(body["model"], system, user)
                    if isinstance(text, int):
                        return self._send(text, {"error": {"message": "the stand-in was told to fail"}})
                    return self._send(200, {"id": "c1", "object": "chat.completion", "model": body["model"],
                                            "choices": [{"index": 0, "finish_reason": "stop",
                                                         "message": {"role": "assistant", "content": text}}],
                                            "usage": {"prompt_tokens": max(1, (len(system) + len(user)) // 4),
                                                      "completion_tokens": max(1, len(text) // 4)}})
                if path.endswith("/v1/messages"):
                    user = body["messages"][-1]["content"]
                    user = user if isinstance(user, str) else "".join(b.get("text", "") for b in user)
                    system = body.get("system") or ""
                    system = system if isinstance(system, str) else "".join(b.get("text", "") for b in system)
                    text = outer.reply(body["model"], system, user)
                    stop = "refusal" if text == "REFUSE" else "end_turn"
                    return self._send(200, {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                            "content": [] if stop == "refusal" else [{"type": "text", "text": text}],
                                            "stop_reason": stop, "stop_sequence": None,
                                            "usage": {"input_tokens": max(1, (len(system) + len(user)) // 4),
                                                      "output_tokens": max(1, len(text) // 4)}})
                self._send(404, {"error": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()

    def posts(self) -> list[dict]:
        return [r for r in self.seen if r["body"] is not None]
