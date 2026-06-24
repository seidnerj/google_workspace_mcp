"""Pure helpers for building Gmail-web faithful MIME content.

These functions are deliberately synchronous and side-effect free so they can be
unit-tested in isolation. Network-bound work (People API name resolution, parent
message fetching) happens in the async Gmail tools, which feed the resulting
strings into these builders and into ``_prepare_gmail_message``.

The one verbatim external constant here is Gmail's blockquote CSS string
(``BLOCKQUOTE_STYLE``); it is Gmail's own markup, not user data.
"""

from __future__ import annotations

import base64
import html as _html
import quopri
import secrets
from datetime import datetime
from email.header import Header
from email.utils import formataddr
from typing import List, Optional, Tuple

# Gmail's byte-identical blockquote style string for quoted replies.
BLOCKQUOTE_STYLE = (
    "margin:0px 0px 0px 0.8ex;border-left:1px solid rgb(204,204,204);padding-left:1ex"
)

# Three-letter day/month names matching Gmail's attribution line.
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MON = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def gmail_boundary() -> str:
    """Return a Gmail-style multipart boundary.

    Matches ``^0{12}[0-9a-f]{16,18}$`` -- the literal ``000000000000`` prefix
    followed by 16-18 random lowercase hex characters.
    """
    # 8 random bytes -> 16 hex chars (within the 16-18 allowed range).
    return "000000000000" + secrets.token_hex(8)


def format_display_address(name: Optional[str], email: str) -> str:
    """Format ``Display Name <email>`` for a header.

    - No name -> bare address (so unresolved lookups still send).
    - Non-ASCII names are RFC2047 encoded-word wrapped.
    - Names with commas/specials are RFC5322 quoted.

    ``email.utils.formataddr`` handles RFC5322 quoting; for non-ASCII it falls
    back to RFC2047 via ``email.headerregistry.Address``.
    """
    if not name or not name.strip():
        return email
    safe_name = name.replace("\r", "").replace("\n", "").replace("\x00", "")
    try:
        safe_name.encode("ascii")
        # ASCII name: formataddr applies RFC5322 quoting when needed.
        return formataddr((safe_name, email))
    except UnicodeEncodeError:
        # Non-ASCII name: RFC2047 encoded-word for the display phrase.
        encoded_name = Header(safe_name, "utf-8").encode()
        return f"{encoded_name} <{email}>"


def _escape_body(text: str) -> str:
    """Escape body text for inclusion in HTML (Gmail entity rules)."""
    # html.escape covers & < > and (quote=True) " and '. Gmail emits &#39; for
    # the apostrophe; html.escape emits &#x27; -- normalize to match.
    escaped = _html.escape(text, quote=True)
    return escaped.replace("&#x27;", "&#39;")


def plain_body_to_html(text: str) -> str:
    """Convert a plain-text body to Gmail's per-line ``<div>`` HTML.

    Each line becomes ``<div>line</div>``; blank lines become ``<div><br></div>``.
    Returned value is the inner HTML (caller wraps it in the ltr container).
    """
    lines = text.split("\n")
    parts = []
    for line in lines:
        if line == "":
            parts.append("<div><br></div>")
        else:
            parts.append(f"<div>{_escape_body(line)}</div>")
    return "".join(parts)


def new_message_html(body_html: str) -> str:
    """Wrap body HTML in Gmail's ``<div dir="ltr">`` container."""
    return f'<div dir="ltr">{body_html}</div>'


def _format_attribution_when(dt: datetime) -> str:
    """Format the ``On <Dow>, <D> <Mon> <YYYY> at <H>:<MM>`` clause.

    Day and hour are NOT zero-padded; minute IS zero-padded.
    """
    dow = _DOW[dt.weekday()]
    mon = _MON[dt.month - 1]
    return f"On {dow}, {dt.day} {mon} {dt.year} at {dt.hour}:{dt.minute:02d}"


def format_attribution_plain(name: str, email: str, dt: datetime) -> str:
    """Plain-text reply attribution line."""
    return f"{_format_attribution_when(dt)}, {name} <{email}> wrote:"


def format_attribution_html(name: str, email: str, dt: datetime) -> str:
    """HTML reply attribution div (the ``gmail_attr`` div, trailing ``<br>``)."""
    when = _format_attribution_when(dt)
    safe_name = _escape_body(name)
    safe_email = _html.escape(email)
    return (
        '<div dir="ltr" class="gmail_attr">'
        f"{when}, {safe_name} "
        f'&lt;<a href="mailto:{safe_email}">{safe_email}</a>&gt; wrote:<br></div>'
    )


def build_quote_plain(parent_text: str) -> str:
    """Prefix each parent line with Gmail's one-level ``> `` quote marker.

    Blank lines become a bare ``>`` (no trailing space). Inner quoting in the
    parent body is inherited verbatim (Gmail only adds its own one level).
    """
    out = []
    for line in parent_text.split("\n"):
        out.append(">" if line == "" else f"> {line}")
    return "\n".join(out)


def build_quote_html(parent_html: str) -> str:
    """Wrap the parent HTML body in Gmail's blockquote (no attribution div).

    The attribution div is assembled separately so the container can be built
    as: container-open + attribution + blockquote + container-close.
    """
    return (
        f'<blockquote class="gmail_quote" style="{BLOCKQUOTE_STYLE}">'
        f"{parent_html}</blockquote>"
    )


def build_quote_container_html(attribution_html: str, parent_html: str) -> str:
    """Assemble the full ``gmail_quote gmail_quote_container`` div for a reply."""
    return (
        '<div class="gmail_quote gmail_quote_container">'
        f"{attribution_html}"
        f"{build_quote_html(parent_html)}"
        "</div>"
    )


def build_forwarded_container_html(
    from_name: Optional[str],
    from_email: str,
    date_str: str,
    subject: str,
    to_rendered: str,
    orig_html: str,
) -> str:
    """Assemble the Gmail-web ``gmail_quote_container`` div for a forwarded message.

    The attribution block follows Gmail's exact forward header layout:
    a ``---------- Forwarded message ---------`` separator followed by
    From/Date/Subject/To lines inside a ``gmail_attr`` div.  No blockquote
    is used — forwarded content is embedded directly after the attr div.

    Args:
        from_name: Sender display name; empty/whitespace → bare-email rendering.
        from_email: Sender email address.
        date_str: Pre-formatted date string (passed through verbatim).
        subject: Email subject (HTML-escaped by this function).
        to_rendered: Pre-rendered recipient HTML (inserted verbatim).
        orig_html: Original message HTML body (inserted verbatim).

    Returns:
        A string containing the full forwarded container div.
    """
    safe_email = _html.escape(from_email)
    safe_subject = _escape_body(subject)

    if from_name and from_name.strip():
        safe_name = _escape_body(from_name)
        from_field = (
            f'<strong class="gmail_sendername" dir="auto">{safe_name}</strong> '
            f'<span dir="auto">&lt;<a href="mailto:{safe_email}">{safe_email}</a>&gt;</span>'
        )
    else:
        from_field = f'<span dir="auto">&lt;<a href="mailto:{safe_email}">{safe_email}</a>&gt;</span>'

    attr_div = (
        '<div dir="ltr" class="gmail_attr">'
        "---------- Forwarded message ---------<br>"
        f"From: {from_field}<br>"
        f"Date: {date_str}<br>"
        f"Subject: {safe_subject}<br>"
        f"To: {to_rendered}<br>"
        "</div>"
    )

    return f'<div class="gmail_quote gmail_quote_container">{attr_div}{orig_html}</div>'


def build_forwarded_plain(
    from_name: Optional[str],
    from_email: str,
    date_str: str,
    subject: str,
    to_rendered_plain: str,
    orig_plain: str,
) -> str:
    """Assemble the plain-text body for a forwarded message.

    Follows Gmail's exact plain-text forward layout: a separator line,
    From/Date/Subject/To header lines, a blank line, then the original body
    verbatim (NOT ``> ``-quoted).

    Args:
        from_name: Sender display name; empty/whitespace → bare email only.
        from_email: Sender email address.
        date_str: Pre-formatted date string.
        subject: Email subject (not escaped — plain text context).
        to_rendered_plain: Pre-rendered plain-text recipient string.
        orig_plain: Original message plain-text body (inserted verbatim).

    Returns:
        A plain-text string with the forwarded message structure.
    """
    if from_name and from_name.strip():
        from_field = f"{from_name} <{from_email}>"
    else:
        from_field = from_email

    return (
        "---------- Forwarded message ---------\n"
        f"From: {from_field}\n"
        f"Date: {date_str}\n"
        f"Subject: {subject}\n"
        f"To: {to_rendered_plain}\n"
        "\n"
        f"{orig_plain}"
    )


def _qp_encode(text: str) -> str:
    """Quoted-printable encode text with CRLF line endings (76-col soft wrap)."""
    # Normalize to CRLF so quopri's soft-wrapping operates on canonical lines.
    raw = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    encoded = quopri.encodestring(raw)
    return encoded.decode("ascii")


def _alternative_parts(plain_text: str, html_text: str, boundary: str) -> str:
    """Return the body of a ``multipart/alternative`` subtree (no top-level headers).

    Emits the two body parts (text/plain + text/html, UTF-8 quoted-printable)
    bounded by ``boundary``, suitable for use both as a standalone message body
    and as a child part within a ``multipart/mixed`` message.
    """
    crlf = "\r\n"

    def _part(content_type: str, body: str) -> str:
        return crlf.join(
            [
                f"--{boundary}",
                f'Content-Type: {content_type}; charset="UTF-8"',
                "Content-Transfer-Encoding: quoted-printable",
                "",
                _qp_encode(body),
            ]
        )

    plain_part = _part("text/plain", plain_text)
    html_part = _part("text/html", html_text)
    closing = f"--{boundary}--"
    return crlf.join([plain_part, html_part, closing, ""])


def assemble_alternative(
    headers: List[Tuple[str, str]],
    plain_text: str,
    html_text: str,
    boundary: str,
) -> str:
    """Assemble a ``multipart/alternative`` message as a raw RFC5322 string.

    ``headers`` is an ordered list of (name, value) pairs authored exactly as the
    spec dictates (the caller controls order and which optional headers appear).
    The ``Content-Type`` header for the top-level multipart is appended here so
    its boundary always matches ``boundary``.

    Both body parts use ``charset="UTF-8"`` (uppercase, double-quoted) and
    ``Content-Transfer-Encoding: quoted-printable``. Returns the message as a
    string with CRLF separators (ready for base64url encoding).
    """
    crlf = "\r\n"
    lines: List[str] = [f"{name}: {value}" for name, value in headers]
    lines.append(f'Content-Type: multipart/alternative; boundary="{boundary}"')
    head = crlf.join(lines)
    return crlf.join([head, "", _alternative_parts(plain_text, html_text, boundary)])


def assemble_mixed(
    headers: List[Tuple[str, str]],
    plain_text: str,
    html_text: str,
    attachments: List[dict],
    boundary_mixed: str,
    boundary_alt: str,
) -> str:
    """Assemble a ``multipart/mixed`` message as a raw RFC5322 string.

    Structure matches Gmail-web's format for forwarded messages with attachments:
    ``multipart/mixed`` → [``multipart/alternative`` (plain + html)] + one part
    per attachment.

    Args:
        headers: Ordered (name, value) pairs (From, To, Subject, etc.).
        plain_text: Plain-text body.
        html_text: HTML body.
        attachments: List of ``{"filename": str, "mime_type": str, "data": bytes}``.
        boundary_mixed: Boundary string for the outer multipart/mixed.
        boundary_alt: Boundary string for the inner multipart/alternative child.

    Returns:
        Raw RFC5322 message string with CRLF separators.
    """
    crlf = "\r\n"
    lines: List[str] = [f"{name}: {value}" for name, value in headers]
    lines.append(f'Content-Type: multipart/mixed; boundary="{boundary_mixed}"')
    head = crlf.join(lines)

    # Inner multipart/alternative child part.
    alt_header = f'Content-Type: multipart/alternative; boundary="{boundary_alt}"'
    alt_body = _alternative_parts(plain_text, html_text, boundary_alt)
    alt_part = crlf.join([f"--{boundary_mixed}", alt_header, "", alt_body])

    # Attachment parts.
    attach_parts: List[str] = []
    for att in attachments:
        filename: str = att["filename"]
        mime_type: str = att["mime_type"]
        data: bytes = att["data"]
        # RFC 2045 quoted-string escaping: backslash first, then double-quote.
        escaped_fn = filename.replace("\\", "\\\\").replace('"', '\\"')
        b64 = base64.encodebytes(data).decode("ascii")
        # encodebytes wraps at 76 cols with a trailing newline; strip it so there
        # is no empty line between the payload and the next boundary delimiter.
        b64_crlf = b64.rstrip("\n").replace("\n", crlf)
        part = crlf.join(
            [
                f"--{boundary_mixed}",
                f'Content-Type: {mime_type}; name="{escaped_fn}"',
                "Content-Transfer-Encoding: base64",
                f'Content-Disposition: attachment; filename="{escaped_fn}"',
                "",
                b64_crlf,
            ]
        )
        attach_parts.append(part)

    closing = f"--{boundary_mixed}--"
    sections = [head, "", alt_part] + attach_parts + [closing, ""]
    return crlf.join(sections)


def encode_raw(message: str) -> str:
    """Base64url-encode an assembled message for the Gmail send API."""
    return base64.urlsafe_b64encode(message.encode("utf-8")).decode("ascii")
