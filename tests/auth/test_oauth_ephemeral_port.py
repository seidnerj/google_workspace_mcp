"""Tests for the stdio ephemeral OAuth callback port behavior.

In stdio mode with no explicitly-pinned port, the OAuth callback server should
bind a free OS-assigned (ephemeral) port at auth time and release it as soon as
the callback resolves, instead of squatting on a fixed port for the whole
process lifetime. An explicitly-pinned WORKSPACE_MCP_PORT/PORT (Web/confidential
client escape hatch) keeps the legacy fixed-port behavior.
"""

import socket
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from starlette.testclient import TestClient

from auth import oauth_callback_server


# --- pinned-port detection ------------------------------------------------


def test_callback_port_is_pinned_reflects_launch_snapshot(monkeypatch):
    # The pinned signal is captured from the launch environment at import time,
    # immune to later WORKSPACE_MCP_PORT mutation by the ephemeral path.
    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", True)
    assert oauth_callback_server._callback_port_is_pinned() is True

    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", False)
    assert oauth_callback_server._callback_port_is_pinned() is False


def test_callback_port_pin_snapshot_ignores_later_env_mutation(monkeypatch):
    # Simulate the ephemeral path setting WORKSPACE_MCP_PORT after launch.
    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", False)
    monkeypatch.setenv("WORKSPACE_MCP_PORT", "54321")
    assert oauth_callback_server._callback_port_is_pinned() is False


# --- ephemeral port acquisition -------------------------------------------


def test_acquire_ephemeral_port_returns_bound_free_socket():
    sock, port = oauth_callback_server._acquire_ephemeral_port("127.0.0.1")
    try:
        assert isinstance(sock, socket.socket)
        assert port > 1024
        # The returned port matches the socket's actual bound port.
        assert sock.getsockname()[1] == port
    finally:
        sock.close()


# --- ensure_stdio wiring --------------------------------------------------


def test_ensure_stdio_unpinned_acquires_ephemeral_port(monkeypatch):
    monkeypatch.setattr(oauth_callback_server, "get_transport_mode", lambda: "stdio")
    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", False)
    monkeypatch.delenv("WORKSPACE_MCP_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("WORKSPACE_MCP_RESOLVED_PORT", raising=False)
    monkeypatch.setattr(
        oauth_callback_server,
        "get_oauth_config",
        lambda: SimpleNamespace(port=54321, base_uri="http://localhost"),
    )
    monkeypatch.setattr(oauth_callback_server, "reload_oauth_config", lambda: None)

    fake_sock = SimpleNamespace(closed=False, close=lambda: None)
    monkeypatch.setattr(
        oauth_callback_server,
        "_acquire_ephemeral_port",
        lambda host: (fake_sock, 54321),
    )

    captured = {}

    def fake_ensure(transport_mode, port, base_uri, **kwargs):
        captured["args"] = (transport_mode, port, base_uri)
        captured["kwargs"] = kwargs
        return True, ""

    monkeypatch.setattr(
        oauth_callback_server, "ensure_oauth_callback_available", fake_ensure
    )

    success, error = oauth_callback_server.ensure_stdio_oauth_callback_available()

    assert success is True and error == ""
    # The ephemeral port was published so the redirect URI is composed from it.
    import os

    assert os.environ["WORKSPACE_MCP_PORT"] == "54321"
    assert captured["args"][0] == "stdio"
    assert captured["args"][1] == 54321
    assert captured["kwargs"].get("ephemeral") is True
    assert captured["kwargs"].get("prebound_socket") is fake_sock


def test_ensure_stdio_pinned_keeps_fixed_port(monkeypatch):
    monkeypatch.setattr(oauth_callback_server, "get_transport_mode", lambda: "stdio")
    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", True)
    monkeypatch.setattr(
        oauth_callback_server,
        "get_oauth_config",
        lambda: SimpleNamespace(port=8000, base_uri="http://localhost"),
    )

    def fail_acquire(host):  # noqa: ARG001
        raise AssertionError("must not acquire ephemeral port when pinned")

    monkeypatch.setattr(oauth_callback_server, "_acquire_ephemeral_port", fail_acquire)

    captured = {}

    def fake_ensure(transport_mode, port, base_uri, **kwargs):
        captured["args"] = (transport_mode, port, base_uri)
        captured["kwargs"] = kwargs
        return True, ""

    monkeypatch.setattr(
        oauth_callback_server, "ensure_oauth_callback_available", fake_ensure
    )

    success, error = oauth_callback_server.ensure_stdio_oauth_callback_available()

    assert success is True and error == ""
    assert captured["args"] == ("stdio", 8000, "http://localhost")
    assert captured["kwargs"].get("ephemeral", False) is False


def test_ensure_stdio_noop_outside_stdio(monkeypatch):
    monkeypatch.setattr(
        oauth_callback_server, "get_transport_mode", lambda: "streamable-http"
    )

    def fail_acquire(host):  # noqa: ARG001
        raise AssertionError("must not bind a port outside stdio")

    monkeypatch.setattr(oauth_callback_server, "_acquire_ephemeral_port", fail_acquire)

    success, error = oauth_callback_server.ensure_stdio_oauth_callback_available()
    assert success is True and error == ""


# --- teardown after callback ----------------------------------------------


def _patch_callback_deps(monkeypatch):
    async def fake_handle_auth_callback(**kwargs):  # noqa: ARG001
        return "user@example.com", object()

    monkeypatch.setattr(oauth_callback_server, "check_client_secrets", lambda: None)
    monkeypatch.setattr(oauth_callback_server, "get_current_scopes", lambda: ["scope"])
    monkeypatch.setattr(
        oauth_callback_server,
        "get_oauth_redirect_uri",
        lambda: "http://localhost:54321/oauth2callback",
    )
    monkeypatch.setattr(
        oauth_callback_server, "handle_auth_callback", fake_handle_auth_callback
    )


def test_ephemeral_callback_schedules_shutdown(monkeypatch):
    _patch_callback_deps(monkeypatch)
    server = oauth_callback_server.MinimalOAuthServer(
        54321, "http://localhost", ephemeral=True
    )
    response = TestClient(server.app).get("/oauth2callback?code=abc")
    assert response.status_code == 200
    assert server._shutdown_requested is True


def test_non_ephemeral_callback_does_not_schedule_shutdown(monkeypatch):
    _patch_callback_deps(monkeypatch)
    server = oauth_callback_server.MinimalOAuthServer(8000, "http://localhost")
    response = TestClient(server.app).get("/oauth2callback?code=abc")
    assert response.status_code == 200
    assert server._shutdown_requested is False


# --- watchdog -------------------------------------------------------------


def test_ephemeral_server_serves_then_releases_port(monkeypatch):
    """End-to-end: an ephemeral server binds, serves one callback on its
    pre-bound socket, then releases the port so a later bind succeeds."""
    import urllib.request

    _patch_callback_deps(monkeypatch)

    sock, port = oauth_callback_server._acquire_ephemeral_port("127.0.0.1")
    server = oauth_callback_server.MinimalOAuthServer(
        port,
        "http://127.0.0.1",
        prebound_socket=sock,
        ephemeral=True,
        idle_timeout=10,
    )

    success, error = server.start()
    assert success is True, error

    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/oauth2callback?code=abc", timeout=5
    ) as resp:
        assert resp.status == 200
        resp.read()
    assert server._shutdown_requested is True

    # The serving thread exits once uvicorn honours should_exit; when serve()
    # returns the listening socket is closed, i.e. the port is released. Joining
    # the thread is the deterministic signal. (A same-port rebind probe would be
    # flaky here because the just-served connection lingers in TIME_WAIT; the
    # next real auth flow sidesteps that entirely by binding port 0 afresh.)
    server.server_thread.join(timeout=15)
    assert not server.server_thread.is_alive(), (
        "ephemeral server thread did not exit after the callback resolved"
    )


def test_ephemeral_arms_watchdog_timer(monkeypatch):
    created = {}

    class _FakeTimer:
        def __init__(self, interval, fn):
            created["interval"] = interval
            created["fn"] = fn
            self.daemon = False
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(oauth_callback_server.threading, "Timer", _FakeTimer)

    server = oauth_callback_server.MinimalOAuthServer(
        54321, "http://localhost", ephemeral=True, idle_timeout=123
    )
    server._arm_watchdog()

    assert created["interval"] == 123
    assert callable(created["fn"])


# --- redirect URI / port consumers see the ephemeral port ------------------


def _arm_real_ephemeral_path(monkeypatch):
    """Run the real stdio ephemeral path (bind, publish, reload) with the
    listener start stubbed out. Returns a dict that receives the bound port."""
    monkeypatch.setattr(oauth_callback_server, "get_transport_mode", lambda: "stdio")
    monkeypatch.setattr(oauth_callback_server, "_OPERATOR_PINNED_CALLBACK_PORT", False)
    # setenv-then-delenv records the vars as originally unset, so teardown also
    # removes the values the ephemeral path writes into os.environ.
    for var in ("WORKSPACE_MCP_PORT", "PORT", "WORKSPACE_MCP_RESOLVED_PORT"):
        monkeypatch.setenv(var, "0")
        monkeypatch.delenv(var)
    monkeypatch.setenv("WORKSPACE_MCP_BASE_URI", "http://localhost")
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("WORKSPACE_EXTERNAL_URL", raising=False)
    oauth_callback_server.reload_oauth_config()

    bound = {}
    real_acquire = oauth_callback_server._acquire_ephemeral_port

    def recording_acquire(host):
        sock, port = real_acquire(host)
        bound["port"] = port
        return sock, port

    def fake_ensure(transport_mode, port, base_uri, prebound_socket=None, **kwargs):  # noqa: ARG001
        if prebound_socket is not None:
            prebound_socket.close()
        return True, ""

    monkeypatch.setattr(
        oauth_callback_server, "_acquire_ephemeral_port", recording_acquire
    )
    monkeypatch.setattr(
        oauth_callback_server, "ensure_oauth_callback_available", fake_ensure
    )
    return bound


@pytest.mark.asyncio
async def test_auth_url_redirect_uri_uses_ephemeral_port(monkeypatch):
    """Regression: the redirect URI handed to start_auth_flow must be composed
    after the ephemeral listener is bound, not from the stale default :8000."""
    from auth.google_auth import (
        GoogleAuthenticationError,
        get_authenticated_google_service,
    )

    bound = _arm_real_ephemeral_path(monkeypatch)

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    captured = {}

    async def fake_start_auth_flow(**kwargs):
        captured["redirect_uri"] = kwargs["redirect_uri"]
        return "auth-url"

    monkeypatch.setattr("auth.google_auth.get_fastmcp_session_id", lambda: None)
    monkeypatch.setattr("auth.google_auth.get_fastmcp_context", None)
    monkeypatch.setattr("auth.google_auth.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("auth.google_auth.get_credentials", lambda **kwargs: None)
    monkeypatch.setattr("auth.google_auth.start_auth_flow", fake_start_auth_flow)

    with pytest.raises(GoogleAuthenticationError, match="auth-url"):
        await get_authenticated_google_service(
            service_name="gmail",
            version="v1",
            tool_name="test_tool",
            user_google_email="user@gmail.com",
            required_scopes=["scope.a"],
            allow_auth_flow=True,
        )

    assert bound["port"] != 8000
    assert urlparse(captured["redirect_uri"]).port == bound["port"]


def test_attachment_url_uses_ephemeral_port(monkeypatch):
    """Regression: the stdio attachment URL must point at the port the
    lazily-started callback listener actually bound."""
    from core import attachment_storage

    bound = _arm_real_ephemeral_path(monkeypatch)
    monkeypatch.setattr("core.gcs_attachment_storage.gcs_files_enabled", lambda: False)

    url = attachment_storage.get_attachment_url("file-id")

    assert urlparse(url).port == bound["port"]


def test_gmail_trusted_attachment_origin_tracks_current_port(monkeypatch):
    """Regression: the trusted local attachment origin must follow the port
    published at auth time, not the value frozen when gmail_tools was imported."""
    # Import before publishing the port, as happens at real server startup.
    from gmail import gmail_tools

    monkeypatch.setenv("WORKSPACE_MCP_RESOLVED_PORT", "1")
    monkeypatch.setenv("WORKSPACE_MCP_PORT", "54321")

    origins = gmail_tools._get_trusted_attachment_origins()

    assert any(netloc.endswith(":54321") for _, netloc in origins)
