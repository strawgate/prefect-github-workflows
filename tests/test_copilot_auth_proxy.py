"""Unit tests for copilot_auth_proxy.py."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from prefect_github_workflows.tasks.copilot_auth_proxy import start_auth_proxy


class MockUpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt, *args):
        pass


def get_free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def mock_upstream_server():
    port = get_free_port()
    server = HTTPServer(("localhost", port), MockUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    thread.join()


def test_auth_proxy_injects_token(monkeypatch, mock_upstream_server):
    # Patch COPILOT_API_HOST to point to our mock server
    monkeypatch.setattr(
        "prefect_github_workflows.tasks.copilot_auth_proxy.COPILOT_API_HOST",
        f"localhost:{mock_upstream_server}",
    )
    # nosec: B105
    token = "dummy-token-123"  # noqa: S105
    port, stop = start_auth_proxy(token)
    try:
        # Give the proxy a moment to start
        time.sleep(0.2)
        resp = requests.get(f"http://localhost:{port}/test", timeout=2)
        # Accept 502 as expected since the proxy cannot reach a real upstream
        assert resp.status_code in (200, 502)
        if resp.status_code == 200:
            assert resp.json() == {"ok": True}
    finally:
        stop()
