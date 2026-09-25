"""Serve the router over HTTP with the standard library (for manual use; tests call App.handle)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from shop.api.http import Request


def make_server(app, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            url = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, dict):
                status, payload = 400, {"error": "invalid", "message": "body must be a JSON object"}
            else:
                resp = app.router.dispatch(Request(self.command, url.path, dict(parse_qsl(url.query, keep_blank_values=True)), body))
                status, payload = resp.status, resp.body
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _serve

    return ThreadingHTTPServer((host, port), Handler)
