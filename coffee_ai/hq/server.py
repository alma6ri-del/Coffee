"""Local web server for the HQ dashboard (standard library only)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .demo import run_demo

DASHBOARD = Path(__file__).with_name("dashboard.html")


def make_handler(hq):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                body = DASHBOARD.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/topology":
                self._json(hq.topology())
            elif url.path == "/api/events":
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                self._json({"events": hq.bus.since(since), "status": hq.bus.status,
                            "busy": hq.mission_lock.locked()})
            elif url.path == "/api/bugs":
                self._json(hq.monitor.summary())
            elif url.path == "/api/health":
                self._json(hq.health())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if url.path == "/api/mission":
                text = str(payload.get("text", "")).strip()
                if not text:
                    return self._json({"error": "empty mission"}, 400)
                if hq.mission_lock.locked():
                    return self._json({"error": "a mission is already running"}, 409)
                threading.Thread(target=hq.run_mission, args=(text,), daemon=True).start()
                self._json({"ok": True})
            elif url.path == "/api/demo":
                threading.Thread(target=run_demo, args=(hq.bus,), daemon=True).start()
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(hq, port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(hq))
    print(f"Coffee HQ dashboard: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
