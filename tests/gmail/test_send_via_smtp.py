"""Tests for send_via_smtp (XOAUTH2 SMTP submission).

All addresses and tokens are synthetic (example.com / fake values only).
"""

import base64

import pytest

import gmail.gmail_send_transport as t


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.cmds = []
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        self.cmds.append("ehlo")

    def starttls(self):
        self.cmds.append("starttls")

    def docmd(self, cmd, arg=""):
        self.cmds.append(("docmd", cmd, arg))
        return (235, b"OK")

    def sendmail(self, frm, to, msg):
        self.sent = (frm, to, msg)
        return {}


@pytest.fixture(autouse=True)
def _reset_fake_smtp_instances():
    """Clear the shared instance registry between tests to avoid cross-test bleed."""
    FakeSMTP.instances = []
    yield
    FakeSMTP.instances = []


@pytest.mark.asyncio
async def test_send_via_smtp_xoauth2(monkeypatch):
    monkeypatch.setattr(t.smtplib, "SMTP", FakeSMTP)
    await t.send_via_smtp(
        "me@example.com",
        ["a@example.com", "b@example.com"],
        b"raw-bytes",
        "me@example.com",
        "TOKEN123",
    )
    s = FakeSMTP.instances[-1]
    assert (s.host, s.port) == ("smtp.gmail.com", 587)
    assert "starttls" in s.cmds
    # STARTTLS must precede AUTH — XOAUTH2 credentials may never cross the wire
    # before the channel is encrypted.
    auth_index = next(
        i for i, c in enumerate(s.cmds) if isinstance(c, tuple) and c[1] == "AUTH"
    )
    assert s.cmds.index("starttls") < auth_index
    auth = next(c for c in s.cmds if isinstance(c, tuple) and c[1] == "AUTH")
    assert auth[2].startswith("XOAUTH2 ")
    decoded = base64.b64decode(auth[2].split(" ", 1)[1]).decode()
    assert decoded == "user=me@example.com\x01auth=Bearer TOKEN123\x01\x01"
    assert s.sent[0] == "me@example.com" and s.sent[1] == [
        "a@example.com",
        "b@example.com",
    ]
    assert s.sent[2] == b"raw-bytes"


@pytest.mark.asyncio
async def test_send_via_smtp_auth_failure_propagates(monkeypatch):
    """A 535 AUTH response must raise SMTPAuthenticationError, not be swallowed."""

    class FailAuthSMTP(FakeSMTP):
        def docmd(self, cmd, arg=""):
            self.cmds.append(("docmd", cmd, arg))
            return (535, b"5.7.8 Username and Password not accepted")

    monkeypatch.setattr(t.smtplib, "SMTP", FailAuthSMTP)
    with pytest.raises(t.smtplib.SMTPAuthenticationError):
        await t.send_via_smtp(
            "me@example.com",
            ["a@example.com"],
            b"raw-bytes",
            "me@example.com",
            "BADTOKEN",
        )


@pytest.mark.asyncio
async def test_send_via_smtp_connection_error_propagates(monkeypatch):
    """A connection-level error from smtplib.SMTP() must propagate unchanged."""

    def _raising_smtp(*args, **kwargs):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(t.smtplib, "SMTP", _raising_smtp)
    with pytest.raises(ConnectionRefusedError):
        await t.send_via_smtp(
            "me@example.com",
            ["a@example.com"],
            b"raw-bytes",
            "me@example.com",
            "TOKEN123",
        )
