"""Integration tests for the Gmail-web faithful send/draft path.

Mocks all Google API calls (People + Gmail parent fetch); never hits the
network. Synthetic data only (example.com / example.org, generic names).
"""

import base64
import quopri
import re
from unittest.mock import Mock

import pytest

from gmail.gmail_tools import send_gmail_message


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _raw_sent(mock_service) -> str:
    kwargs = mock_service.users.return_value.messages.return_value.send.call_args.kwargs
    raw = kwargs["body"]["raw"]
    return base64.urlsafe_b64decode(raw.encode()).decode("utf-8")


def _decode_bodies(raw: str) -> str:
    headers, _, body = raw.partition("\r\n\r\n")
    decoded = quopri.decodestring(body.encode("utf-8")).decode("utf-8")
    return f"{headers}\r\n\r\n{decoded}"


def _gmail_service():
    service = Mock()
    service.users().messages().send().execute.return_value = {"id": "sent123"}
    # No signature.
    service.users().settings().sendAs().list().execute.return_value = {"sendAs": []}
    return service


def _people_service_with(name: str, email: str):
    service = Mock()
    service.people().searchContacts().execute.return_value = {
        "results": [
            {
                "person": {
                    "names": [{"displayName": name}],
                    "emailAddresses": [{"value": email}],
                }
            }
        ]
    }
    # Warmup call (query="") is not used by our resolver, but keep it harmless.
    return service


def _people_service_empty():
    service = Mock()
    service.people().searchContacts().execute.return_value = {"results": []}
    return service


@pytest.mark.asyncio
async def test_send_resolves_display_names_on_to():
    gmail = _gmail_service()
    people = _people_service_with("Ada Lovelace", "ada@example.com")

    result = await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="Hello there",
        include_signature=False,
    )

    raw = _raw_sent(gmail)
    assert "Email sent" in result
    assert "To: Ada Lovelace <ada@example.com>" in raw
    assert 'Content-Type: multipart/alternative; boundary="000000000000' in raw


@pytest.mark.asyncio
async def test_send_falls_back_to_bare_addr_when_unresolved():
    gmail = _gmail_service()
    people = _people_service_empty()

    await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="Hello there",
        include_signature=False,
    )

    raw = _raw_sent(gmail)
    assert "To: ada@example.com" in raw
    # Still a full multipart/alternative.
    assert 'text/plain; charset="UTF-8"' in raw
    assert 'text/html; charset="UTF-8"' in raw


@pytest.mark.asyncio
async def test_send_degrades_when_name_lookup_raises():
    gmail = _gmail_service()
    people = Mock()
    people.people().searchContacts().execute.side_effect = RuntimeError("boom")

    await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="Hello there",
        include_signature=False,
    )

    raw = _raw_sent(gmail)
    assert "To: ada@example.com" in raw
    assert "multipart/alternative" in raw


@pytest.mark.asyncio
async def test_send_new_message_html_has_no_ai_or_tool_fingerprints():
    """Goal 2: the authored HTML must look hand-typed in Gmail web, not pasted
    from a tool. No class/style/p/data attributes in the new-body block, and
    none of the known AI/tool fingerprint tokens; no vendor mailer headers."""
    gmail = _gmail_service()
    people = _people_service_empty()

    await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="First line\n\nSecond line",
        include_signature=False,
    )

    msg = _decode_bodies(_raw_sent(gmail))

    # The authored new-body block.
    block = re.search(r'(<div dir="ltr">.*?</div>)\r?\n?--', msg, re.DOTALL)
    assert block, msg
    new_body = block.group(1)

    # Typed Gmail structure: per-line <div>, blank line as <div><br></div>.
    assert "<div>First line</div>" in new_body
    assert "<div><br></div>" in new_body
    assert "<div>Second line</div>" in new_body

    # No fingerprints inside the new-body block.
    assert "class=" not in new_body
    assert "style=" not in new_body
    assert "<p " not in new_body and "<p>" not in new_body
    assert "data-" not in new_body
    for token in (
        "gmail-font-",
        "claude",
        "whitespace-normal",
        "break-words",
        "leading-[",
        "list-disc",
        "pl-",
    ):
        assert token not in msg.lower() if token == "claude" else token not in msg

    # No vendor mailer headers anywhere.
    header_block = msg.split("\r\n\r\n", 1)[0].lower()
    assert "x-mailer" not in header_block
    assert "user-agent" not in header_block


@pytest.mark.asyncio
async def test_reply_builds_gmail_quote_from_parent():
    gmail = _gmail_service()
    # Parent thread fetch (full, with bodies) for the quote + auto-threading.
    thread_full = {
        "messages": [
            {
                "id": "p1",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "Message-ID", "value": "<parent@example.com>"},
                        {"name": "From", "value": "Ada Lovelace <ada@example.com>"},
                        {"name": "Subject", "value": "Project sync"},
                        {
                            "name": "Date",
                            "value": "Tue, 7 Apr 2026 19:19:00 +0000",
                        },
                    ],
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": _encode("Original line")},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": _encode("<div>Original line</div>")},
                        },
                    ],
                },
            }
        ]
    }
    gmail.users().threads().get().execute.return_value = thread_full
    people = _people_service_empty()
    # Reset call count so the assertion below measures only the send's fetch
    # (the setup line above already invoked .get() once).
    gmail.users.return_value.threads.return_value.get.reset_mock()

    await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="Thanks!",
        thread_id="thread123",
        include_signature=False,
    )

    msg = _decode_bodies(_raw_sent(gmail))
    # The thread is fetched exactly once (shared by auto-threading + the quote).
    assert gmail.users.return_value.threads.return_value.get.call_count == 1
    # Auto-populated reply headers from the thread.
    assert "In-Reply-To: <parent@example.com>" in msg
    assert "References: <parent@example.com>" in " ".join(msg.split())
    # gmail_quote container + exact attribution + verbatim parent html.
    assert "gmail_quote gmail_quote_container" in msg
    assert "On Tue, 7 Apr 2026 at 19:19, Ada Lovelace" in msg
    assert "<div>Original line</div>" in msg
    assert "> Original line" in msg


@pytest.mark.asyncio
async def test_reply_without_parent_sends_without_quote():
    gmail = _gmail_service()
    gmail.users().threads().get().execute.side_effect = RuntimeError("fetch failed")
    people = _people_service_empty()

    result = await _unwrap(send_gmail_message)(
        service=gmail,
        people_service=people,
        user_google_email="grace@example.org",
        to="ada@example.com",
        subject="Project sync",
        body="Thanks!",
        thread_id="thread123",
        include_signature=False,
    )

    msg = _decode_bodies(_raw_sent(gmail))
    assert "Email sent" in result
    assert "gmail_quote_container" not in msg
    # Still multipart with both parts.
    assert 'text/plain; charset="UTF-8"' in msg
    assert 'text/html; charset="UTF-8"' in msg
