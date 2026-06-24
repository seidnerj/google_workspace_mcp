"""Tests for resolve_effective_transport and dispatch_transmit.

All addresses and identifiers are synthetic (example.com only).
"""

import base64
from unittest.mock import MagicMock, AsyncMock

import pytest

import gmail.gmail_send_transport as t
from auth.scopes import MAIL_GOOGLE_COM_SCOPE, GMAIL_READONLY_SCOPE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER = "alice@example.com"
_RAW_MSG = base64.urlsafe_b64encode(b"Subject: hi\r\n\r\nBody").decode()


def _make_creds(scopes=()):
    creds = MagicMock()
    creds.scopes = set(scopes)
    creds.token = "tok-abc"
    creds.expired = False
    return creds


def _make_service(send_result=None, list_result=None):
    """Build a fake googleapiclient service stub."""
    service = MagicMock()

    # messages().send(…).execute returns send_result
    send_exec = MagicMock(return_value=send_result or {"id": "msg-default"})
    service.users.return_value.messages.return_value.send.return_value.execute = (
        send_exec
    )

    # messages().list(…).execute returns list_result
    list_exec = MagicMock(return_value=list_result or {"messages": []})
    service.users.return_value.messages.return_value.list.return_value.execute = (
        list_exec
    )

    return service


# ---------------------------------------------------------------------------
# resolve_effective_transport
# ---------------------------------------------------------------------------


class TestResolveEffectiveTransport:
    def test_env_api_returns_api_no_creds(self, monkeypatch):
        monkeypatch.setattr(t, "get_send_transport", lambda: "api")
        effective, creds, note = t.resolve_effective_transport(_USER)
        assert effective == "api"
        assert creds is None
        assert note == ""

    def test_env_smtp_with_mail_scope_returns_smtp(self, monkeypatch):
        monkeypatch.setattr(t, "get_send_transport", lambda: "smtp")
        fake_creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE])
        store = MagicMock()
        store.get_credential.return_value = fake_creds
        monkeypatch.setattr(t, "get_credential_store", lambda: store)

        effective, creds, note = t.resolve_effective_transport(_USER)

        assert effective == "smtp"
        assert creds is fake_creds
        assert note == ""

    def test_env_smtp_without_mail_scope_returns_api_with_note(self, monkeypatch):
        monkeypatch.setattr(t, "get_send_transport", lambda: "smtp")
        fake_creds = _make_creds(scopes=["https://www.googleapis.com/auth/gmail.send"])
        store = MagicMock()
        store.get_credential.return_value = fake_creds
        monkeypatch.setattr(t, "get_credential_store", lambda: store)

        effective, creds, note = t.resolve_effective_transport(_USER)

        assert effective == "api"
        assert creds is fake_creds
        assert "https://mail.google.com/" in note
        assert "Re-authenticate" in note

    def test_env_smtp_no_creds_returns_api_with_note(self, monkeypatch):
        monkeypatch.setattr(t, "get_send_transport", lambda: "smtp")
        store = MagicMock()
        store.get_credential.return_value = None
        monkeypatch.setattr(t, "get_credential_store", lambda: store)

        effective, creds, note = t.resolve_effective_transport(_USER)

        assert effective == "api"
        assert creds is None
        assert note != ""


# ---------------------------------------------------------------------------
# dispatch_transmit — API path
# ---------------------------------------------------------------------------


class TestDispatchTransmitApiPath:
    @pytest.mark.asyncio
    async def test_api_path_calls_send_not_smtp(self, monkeypatch):
        smtp_called = []
        monkeypatch.setattr(
            t,
            "send_via_smtp",
            AsyncMock(side_effect=lambda *a, **kw: smtp_called.append(True)),
        )
        service = _make_service(send_result={"id": "abc123"})

        result = await t.dispatch_transmit(
            service,
            effective="api",
            creds=None,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        assert "Message ID: abc123" in result
        assert not smtp_called

    @pytest.mark.asyncio
    async def test_api_path_appends_fallback_note(self, monkeypatch):
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock())
        service = _make_service(send_result={"id": "xyz"})

        result = await t.dispatch_transmit(
            service,
            effective="api",
            creds=None,
            fallback_note=" Note: fallback active",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        assert "Message ID: xyz" in result
        assert "Note: fallback active" in result

    @pytest.mark.asyncio
    async def test_api_path_includes_thread_id(self, monkeypatch):
        service = _make_service(send_result={"id": "t1"})
        await t.dispatch_transmit(
            service,
            effective="api",
            creds=None,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final="thread-99",
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )
        # Check that the send body included threadId
        send_call = service.users().messages().send.call_args
        body = (
            send_call[1]["body"] if "body" in (send_call[1] or {}) else send_call[0][0]
        )
        assert body.get("threadId") == "thread-99"


# ---------------------------------------------------------------------------
# dispatch_transmit — SMTP path
# ---------------------------------------------------------------------------


class TestDispatchTransmitSmtpPath:
    @pytest.mark.asyncio
    async def test_smtp_happy_path_finds_message_id(self, monkeypatch):
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock(return_value="OK queued"))

        creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE, GMAIL_READONLY_SCOPE])
        service = _make_service(list_result={"messages": [{"id": "smtp-msg-1"}]})

        result = await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        assert "via SMTP!" in result
        assert "queued: OK queued" in result
        assert "Message ID: smtp-msg-1" in result
        # messages().send should NOT have been called
        service.users().messages().send.assert_not_called()

    @pytest.mark.asyncio
    async def test_smtp_lookup_no_match(self, monkeypatch):
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock(return_value="OK queued"))
        creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE, GMAIL_READONLY_SCOPE])
        service = _make_service(list_result={"messages": []})

        result = await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        assert "via SMTP!" in result
        assert "could not find message id via api — best effort" in result

    @pytest.mark.asyncio
    async def test_smtp_missing_readonly_scope(self, monkeypatch):
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock(return_value="OK queued"))
        # Use a scope that does NOT imply readonly (mail.google.com implies readonly
        # via the hierarchy, so use a narrow send-only scope to exercise the branch).
        creds = _make_creds(scopes=["https://www.googleapis.com/auth/gmail.send"])
        service = _make_service()

        result = await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        assert "via SMTP!" in result
        assert "due to missing scope(s):" in result
        assert GMAIL_READONLY_SCOPE in result
        assert "re-authenticate" in result.lower()

    @pytest.mark.asyncio
    async def test_smtp_lookup_raises_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock(return_value="OK queued"))
        creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE, GMAIL_READONLY_SCOPE])

        # Make list().execute raise
        service = MagicMock()
        service.users.return_value.messages.return_value.send.return_value.execute = (
            MagicMock(return_value={"id": "x"})
        )
        service.users.return_value.messages.return_value.list.return_value.execute = (
            MagicMock(side_effect=RuntimeError("network error"))
        )

        result = await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        # Must not raise; must degrade to best-effort string
        assert "via SMTP!" in result
        assert "could not find message id via api — best effort" in result

    @pytest.mark.asyncio
    async def test_smtp_envelope_includes_to_cc_bcc(self, monkeypatch):
        captured = {}

        async def fake_smtp(sender, envelope_recipients, raw_bytes, user_email, token):
            captured["envelope"] = envelope_recipients
            return "OK"

        monkeypatch.setattr(t, "send_via_smtp", fake_smtp)
        creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE])
        service = _make_service()

        await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["Bob <bob@example.com>"],
            cc=["carol@example.com"],
            bcc=["dave@example.com"],
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        env = captured["envelope"]
        assert "bob@example.com" in env
        assert "carol@example.com" in env
        assert "dave@example.com" in env

    @pytest.mark.asyncio
    async def test_smtp_expired_creds_refreshed(self, monkeypatch):
        """When creds are expired, refresh() must be called before sending."""
        monkeypatch.setattr(t, "send_via_smtp", AsyncMock(return_value="OK"))

        # MagicMock tracks calls automatically.
        creds = _make_creds(scopes=[MAIL_GOOGLE_COM_SCOPE])
        creds.expired = True

        # Patch google.auth.transport.requests.Request to avoid real HTTP.
        import google.auth.transport.requests as _gtr

        monkeypatch.setattr(_gtr, "Request", MagicMock)

        service = _make_service()

        await t.dispatch_transmit(
            service,
            effective="smtp",
            creds=creds,
            fallback_note="",
            raw_message_b64=_RAW_MSG,
            thread_id_final=None,
            sender="alice@example.com",
            to=["bob@example.com"],
            cc=None,
            bcc=None,
            subject="hi",
            user_google_email=_USER,
            action_label="Email sent",
            attachment_info="",
            trailing_note="",
        )

        # creds.refresh is a MagicMock attribute — assert it was called once.
        creds.refresh.assert_called_once()
