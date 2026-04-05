"""Local auth proxy for Copilot CLI.

Runs a lightweight HTTP server that the Copilot binary hits via
``COPILOT_PROVIDER_BASE_URL``.  The proxy injects the real GitHub PAT
as a Bearer token and forwards requests to the Copilot API at
``api.business.githubcopilot.com``.

This way the agent subprocess never holds the PAT — it only sees
``http://localhost:{port}`` as its provider, with no API key.

Lifecycle:
  1. ``start_auth_proxy(token)`` → spawns a daemon thread, returns ``(port, stop_fn)``
  2. Caller sets ``COPILOT_PROVIDER_BASE_URL=http://localhost:{port}``
  3. After the agent finishes, call ``stop_fn()`` to shut down the server.
"""

from __future__ import annotations

import http.client
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

COPILOT_API_HOST = "api.business.githubcopilot.com"


def _make_handler(token: str) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class that injects *token* into upstream requests."""

    class _ProxyHandler(BaseHTTPRequestHandler):
        """Forward requests to the Copilot API with the real Bearer token."""

        def do_GET(self) -> None:
            self._proxy("GET")

        def do_POST(self) -> None:
            self._proxy("POST")

        # ── Core proxy logic ──────────────────────────────────────

        def _proxy(self, method: str) -> None:
            # Read request body (if any)
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else None

            # Build upstream headers — drop hop-by-hop, inject auth
            upstream_headers: dict[str, str] = {
                "Authorization": f"Bearer {token}",
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Accept": self.headers.get("Accept", "application/json"),
                "Copilot-Integration-Id": "copilot-developer-cli",
            }

            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(COPILOT_API_HOST, context=ctx)
            try:
                conn.request(method, self.path, body=body, headers=upstream_headers)
                resp = conn.getresponse()

                # Forward status + headers
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    lower = key.lower()
                    if lower not in ("transfer-encoding", "connection"):
                        self.send_header(key, val)
                self.end_headers()

                # Stream the response body in chunks
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception:
                self.send_error(502, "Upstream connection failed")
            finally:
                conn.close()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Suppress noisy default access logging."""

    return _ProxyHandler


def start_auth_proxy(token: str) -> tuple[int, Callable[[], None]]:
    """Start the auth proxy on a random available port.

    Returns ``(port, stop_fn)`` where *stop_fn* shuts down the server.
    """
    handler = _make_handler(token)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop() -> None:
        server.shutdown()
        thread.join(timeout=5)

    return port, stop
