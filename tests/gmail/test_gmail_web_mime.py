"""Tests for Gmail-web faithful MIME construction.

All fixtures use synthetic data only (example.com / example.org addresses and
generic names). No real personal data appears in this file.
"""

import base64
import quopri
import re
from datetime import datetime, timezone

from gmail.gmail_web_mime import (
    BLOCKQUOTE_STYLE,
    build_quote_container_html,
    build_quote_html,
    build_quote_plain,
    format_attribution_html,
    format_attribution_plain,
    format_display_address,
    gmail_boundary,
    new_message_html,
    plain_body_to_html,
)

BOUNDARY_RE = re.compile(r"^0{12}[0-9a-f]{16,18}$")


class TestBoundary:
    def test_matches_gmail_pattern(self):
        for _ in range(50):
            assert BOUNDARY_RE.match(gmail_boundary())

    def test_is_random(self):
        assert gmail_boundary() != gmail_boundary()


class TestDisplayAddress:
    def test_plain_name(self):
        assert (
            format_display_address("Ada Lovelace", "ada@example.com")
            == "Ada Lovelace <ada@example.com>"
        )

    def test_no_name_returns_bare_address(self):
        assert format_display_address(None, "ada@example.com") == "ada@example.com"
        assert format_display_address("", "ada@example.com") == "ada@example.com"

    def test_name_with_comma_is_quoted(self):
        result = format_display_address("Lovelace, Ada", "ada@example.com")
        assert result == '"Lovelace, Ada" <ada@example.com>'

    def test_non_ascii_name_rfc2047_encoded(self):
        result = format_display_address("Adá Lóvelace", "ada@example.com")
        assert "=?utf-8?" in result.lower()
        assert "<ada@example.com>" in result
        # No raw non-ASCII bytes leak into the header.
        result.encode("ascii")


class TestNewMessageHtml:
    def test_wraps_in_ltr_div(self):
        assert new_message_html("<div>Hi</div>") == '<div dir="ltr"><div>Hi</div></div>'

    def test_plain_body_to_html_escapes_and_wraps_lines(self):
        html = plain_body_to_html("Line one\n\nLine three & <stuff>")
        assert "&amp;" in html
        assert "&lt;stuff&gt;" in html
        assert "<div><br></div>" in html  # blank line


class TestAttribution:
    def test_plain_attribution_no_zero_pad(self):
        dt = datetime(2026, 4, 7, 9, 5, tzinfo=timezone.utc)
        attr = format_attribution_plain("Grace Hopper", "grace@example.org", dt)
        # Day 7 and hour 9 are NOT zero-padded; minute IS.
        assert (
            attr
            == "On Tue, 7 Apr 2026 at 9:05, Grace Hopper <grace@example.org> wrote:"
        )

    def test_html_attribution_structure(self):
        dt = datetime(2026, 4, 7, 19, 19, tzinfo=timezone.utc)
        attr = format_attribution_html("Grace Hopper", "grace@example.org", dt)
        assert 'class="gmail_attr"' in attr
        assert "On Tue, 7 Apr 2026 at 19:19, Grace Hopper" in attr
        assert (
            '&lt;<a href="mailto:grace@example.org">grace@example.org</a>&gt;' in attr
        )
        assert attr.rstrip().endswith("<br></div>")


class TestQuote:
    def test_plain_quote_prefixes_each_line(self):
        quoted = build_quote_plain("hello\nworld")
        assert quoted == "> hello\n> world"

    def test_plain_quote_blank_line_has_no_trailing_space(self):
        quoted = build_quote_plain("a\n\nb")
        assert quoted == "> a\n>\n> b"

    def test_blockquote_skeleton_exact(self):
        parent = "<div>Parent body</div>"
        bq = build_quote_html(parent)
        assert bq == (
            f'<blockquote class="gmail_quote" style="{BLOCKQUOTE_STYLE}">'
            f"{parent}</blockquote>"
        )

    def test_container_has_quote_container_class(self):
        dt = datetime(2026, 4, 7, 19, 19, tzinfo=timezone.utc)
        attr = format_attribution_html("Ada Lovelace", "ada@example.com", dt)
        container = build_quote_container_html(attr, "<div>Parent body</div>")
        assert container.startswith('<div class="gmail_quote gmail_quote_container">')
        assert "Parent body" in container

    def test_blockquote_style_constant(self):
        assert BLOCKQUOTE_STYLE == (
            "margin:0px 0px 0px 0.8ex;border-left:1px solid rgb(204,204,204);"
            "padding-left:1ex"
        )


# ---- Assembly-level tests via the sync builder in gmail_tools ----


def _decode_raw(raw_b64: str) -> str:
    return base64.urlsafe_b64decode(raw_b64.encode()).decode("utf-8")


def _decode_qp_parts(msg: str) -> str:
    """Return the message with each part's QP body decoded.

    Quoted-printable soft-wraps long lines with ``=\\r\\n`` so byte sequences
    (like an HTML class attribute) can be split across lines in the raw form.
    Decoding the bodies lets content assertions see the logical text.
    """
    headers, _, body = msg.partition("\r\n\r\n")
    decoded = quopri.decodestring(body.encode("utf-8")).decode("utf-8")
    return f"{headers}\r\n\r\n{decoded}"


def _new_bodies(plain="Hello there"):
    """Build the (plain, html) pair for a non-reply web compose."""
    html = new_message_html(plain_body_to_html(plain))
    return plain, html


def _reply_bodies(reply="Thanks!", parent_text="Original line", parent_html=None):
    dt = datetime(2026, 4, 7, 19, 19, tzinfo=timezone.utc)
    parent_html = parent_html or "<div>Original line</div>"
    attr_plain = format_attribution_plain("Ada Lovelace", "ada@example.com", dt)
    attr_html = format_attribution_html("Ada Lovelace", "ada@example.com", dt)
    plain = f"{reply}\n\n{attr_plain}\n{build_quote_plain(parent_text)}"
    html = (
        f"{new_message_html(plain_body_to_html(reply))}<br>"
        f"{build_quote_container_html(attr_html, parent_html)}"
    )
    return plain, html


class TestPrepareWebMessage:
    def _build(self, plain="Hello there", html=None, **kwargs):
        from gmail.gmail_tools import _prepare_gmail_message

        if html is None:
            plain, html = _new_bodies(plain)
        defaults = dict(
            subject="Project sync",
            body=plain,
            html_body=html,
            to="Ada Lovelace <ada@example.com>",
            from_email="grace@example.org",
            from_name="Grace Hopper",
            web_compose=True,
        )
        defaults.update(kwargs)
        raw, thread_id, count, errors = _prepare_gmail_message(**defaults)
        return _decode_raw(raw)

    def test_top_level_multipart_alternative_with_gmail_boundary(self):
        msg = self._build()
        m = re.search(r'Content-Type: multipart/alternative;\s*boundary="([^"]+)"', msg)
        assert m, msg
        assert BOUNDARY_RE.match(m.group(1))

    def test_two_parts_plain_then_html_uppercase_utf8_qp(self):
        msg = self._build()
        plain_idx = msg.index('Content-Type: text/plain; charset="UTF-8"')
        html_idx = msg.index('Content-Type: text/html; charset="UTF-8"')
        assert plain_idx < html_idx
        assert msg.count("Content-Transfer-Encoding: quoted-printable") == 2

    def test_from_to_carry_display_names(self):
        msg = self._build()
        assert "From: Grace Hopper <grace@example.org>" in msg
        assert "To: Ada Lovelace <ada@example.com>" in msg

    def test_cc_carries_display_name(self):
        msg = self._build(cc="Charles Babbage <charles@example.org>")
        assert "Cc: Charles Babbage <charles@example.org>" in msg

    def test_from_to_fall_back_to_bare_addr(self):
        # No from_name and a bare 'to' simulate unresolved name lookups.
        msg = self._build(from_name=None, to="ada@example.com")
        assert "To: ada@example.com" in msg
        assert "From: grace@example.org" in msg

    def test_new_message_html_has_ltr_div_no_quote(self):
        msg = self._build()
        # QP may soft-wrap, but the ltr opener fits on one line.
        assert '<div dir=3D"ltr">' in msg
        assert "gmail_quote_container" not in msg

    def test_plain_body_format_still_builds_both_parts(self):
        msg = self._build()
        assert 'text/plain; charset="UTF-8"' in msg
        assert 'text/html; charset="UTF-8"' in msg

    def test_header_order(self):
        msg = self._build()
        order = [
            "MIME-Version:",
            "Subject:",
            "From:",
            "To:",
            "Content-Type:",
        ]
        positions = [msg.index(h) for h in order]
        assert positions == sorted(positions)

    def test_reply_quote_in_both_parts(self):
        plain, html = _reply_bodies()
        raw = self._build(
            plain=plain,
            html=html,
            in_reply_to="<parent@example.com>",
            references="<parent@example.com>",
        )
        # Headers are not QP-encoded; assert on the raw form.
        assert "In-Reply-To: <parent@example.com>" in raw
        assert "References: <parent@example.com>" in raw
        # Bodies are QP-encoded (soft-wrapped); decode before content asserts.
        msg = _decode_qp_parts(raw)
        assert "gmail_quote gmail_quote_container" in msg
        assert "On Tue, 7 Apr 2026 at 19:19" in msg
        # Parent html inherited verbatim.
        assert "<div>Original line</div>" in msg
        # Plain-part one-level quote prefixing.
        assert "> Original line" in msg


class TestNoToolFingerprints:
    """The authored HTML must look hand-typed in Gmail-web, with no markers that
    betray AI/tool-pasted content."""

    def _new_body_html(self, body: str) -> str:
        """Return the decoded new-body HTML block for a normal (non-reply) send."""
        from gmail.gmail_tools import _prepare_gmail_message

        plain, html = _new_bodies(body)
        raw, *_ = _prepare_gmail_message(
            subject="Project sync",
            body=plain,
            html_body=html,
            to="ada@example.com",
            from_email="grace@example.org",
            from_name="Grace Hopper",
            web_compose=True,
        )
        msg = _decode_qp_parts(_decode_raw(raw))
        start = msg.index('<div dir="ltr">')
        end = msg.index("</blockquote>") if "</blockquote>" in msg else len(msg)
        return msg[start:end]

    def test_typed_structure_for_multiline_body(self):
        block = self._new_body_html("Line one\n\nLine three")
        assert block.startswith('<div dir="ltr">')
        assert "<div>Line one</div>" in block
        assert "<div><br></div>" in block  # blank line
        assert "<div>Line three</div>" in block

    def test_no_ai_or_tool_fingerprints(self):
        block = self._new_body_html("Hello there\nSecond line")
        # No class attributes inside the authored body block.
        assert "class=" not in block
        # No gmail-font-* / tool font classes.
        assert "gmail-font-" not in block
        # No paragraph tags (Gmail types <div> lines, not <p>).
        assert not re.search(r"<p[ >]", block)
        # No data-* attributes.
        assert not re.search(r"\sdata-[a-z]", block)
        # No inline styles on the typed body lines.
        assert "style=" not in block
        # None of the Tailwind-style fingerprints.
        for marker in (
            "whitespace-normal",
            "break-words",
            "leading-[",
            "list-disc",
            "pl-",
            "[li_&]",
        ):
            assert marker not in block

    def test_no_vendor_headers(self):
        from gmail.gmail_tools import _prepare_gmail_message

        plain, html = _new_bodies("Hello")
        raw, *_ = _prepare_gmail_message(
            subject="Project sync",
            body=plain,
            html_body=html,
            to="ada@example.com",
            from_email="grace@example.org",
            from_name="Grace Hopper",
            web_compose=True,
        )
        msg = _decode_raw(raw)
        headers = msg.split("\r\n\r\n", 1)[0].lower()
        assert "x-mailer" not in headers
        assert "user-agent" not in headers
        assert "message-id" not in headers  # Gmail assigns it
