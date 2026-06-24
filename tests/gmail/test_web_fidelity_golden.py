import json
import pathlib
import re

from gmail.gmail_web_mime import (
    BLOCKQUOTE_STYLE,
    build_forwarded_container_html,
    build_forwarded_plain,
)
from tools.golden_skeleton import sanitize_html

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_blockquote_style_matches_current_golden():
    golden = json.loads((FIX / "golden_reply.json").read_text())
    assert BLOCKQUOTE_STYLE == golden["html_probes"]["blockquote_style"]


# ---------------------------------------------------------------------------
# build_forwarded_container_html tests
# ---------------------------------------------------------------------------


def _tags(html: str) -> str:
    """Sanitize HTML and return all tags as a single string for substring checks."""
    return "".join(
        re.sub(r'href="[^"]*"', 'href="‹h›"', t)
        for t in re.findall(r"<[^>]+>", sanitize_html(html))
    )


def test_forward_container_matches_golden_skeleton():
    """Verify builder output yields probes matching golden fixture values."""
    golden = json.loads((FIX / "golden_forward.json").read_text())
    html = build_forwarded_container_html(
        "Jane Roe",
        "jane@example.com",
        "Mon, 2 Jun 2025 at 14:05",
        "Quarterly",
        "joe@example.com",
        "<div>orig</div>",
    )
    # Probe the builder's output directly and compare to golden fixture.
    has_gmail_quote_container = 'class="gmail_quote gmail_quote_container"' in html
    has_gmail_sendername = "gmail_sendername" in html
    has_blockquote_gmail_quote = "blockquote" in html
    has_forwarded_literal = "Forwarded message" in html

    assert (
        has_gmail_quote_container == golden["html_probes"]["has_gmail_quote_container"]
    )
    assert has_gmail_sendername == golden["html_probes"]["has_gmail_sendername"]
    assert (
        has_blockquote_gmail_quote
        == golden["html_probes"]["has_blockquote_gmail_quote"]
    )
    assert has_forwarded_literal == golden["html_probes"]["has_forwarded_literal"]
    # Keep the existing tag-skeleton assertions.
    tags = _tags(html)
    assert 'class="gmail_quote gmail_quote_container"' in tags
    assert 'class="gmail_sendername"' in tags
    assert "blockquote" not in tags


def test_forward_container_html_no_blockquote():
    """Output must never contain a blockquote element."""
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Tue, 3 Jun 2025 at 09:00",
        "Test subject",
        "bob@example.com",
        "<div>body</div>",
    )
    assert "blockquote" not in html


def test_forward_container_html_required_classes():
    """All required Gmail structural classes must be present."""
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Tue, 3 Jun 2025 at 09:00",
        "Test subject",
        "bob@example.com",
        "<div>body</div>",
    )
    assert 'class="gmail_quote gmail_quote_container"' in html
    assert 'class="gmail_attr"' in html
    assert 'class="gmail_sendername"' in html


def test_forward_container_html_forwarded_literal():
    """The forwarded separator literal must appear verbatim."""
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Tue, 3 Jun 2025 at 09:00",
        "Test subject",
        "bob@example.com",
        "<div>body</div>",
    )
    assert "---------- Forwarded message ---------" in html


def test_forward_container_html_probes_match_golden():
    """All boolean probes must agree with golden_forward.json fixture values."""
    golden = json.loads((FIX / "golden_forward.json").read_text())
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Tue, 3 Jun 2025 at 09:00",
        "Test subject",
        "bob@example.com",
        "<div>body</div>",
    )
    assert ('class="gmail_quote gmail_quote_container"' in html) == golden[
        "html_probes"
    ]["has_gmail_quote_container"]
    assert ('class="gmail_attr"' in html) == golden["html_probes"]["has_gmail_attr"]
    assert ("gmail_sendername" in html) == golden["html_probes"]["has_gmail_sendername"]
    assert ("blockquote" in html) == golden["html_probes"]["has_blockquote_gmail_quote"]
    assert ("Forwarded message" in html) == golden["html_probes"][
        "has_forwarded_literal"
    ]


def test_forward_container_html_from_fields():
    """From name, email, date, subject, to, and orig_html appear in output."""
    html = build_forwarded_container_html(
        "Jane Roe",
        "jane@example.com",
        "Mon, 2 Jun 2025 at 14:05",
        "Quarterly Report",
        "joe@example.com",
        "<div>original content</div>",
    )
    assert "Jane Roe" in html
    assert "jane@example.com" in html
    assert "Mon, 2 Jun 2025 at 14:05" in html
    assert "Quarterly Report" in html
    assert "joe@example.com" in html
    assert "<div>original content</div>" in html


def test_forward_container_html_empty_from_name():
    """When from_name is empty, omit the <strong> sendername element."""
    html = build_forwarded_container_html(
        "",
        "anon@example.com",
        "Wed, 4 Jun 2025 at 10:00",
        "No-name test",
        "recipient@example.com",
        "<div>content</div>",
    )
    assert "gmail_sendername" not in html
    assert "anon@example.com" in html


def test_forward_container_html_whitespace_only_from_name():
    """When from_name is whitespace only, treat as empty — omit sendername."""
    html = build_forwarded_container_html(
        "   ",
        "anon@example.com",
        "Wed, 4 Jun 2025 at 10:00",
        "Whitespace test",
        "recipient@example.com",
        "<div>content</div>",
    )
    assert "gmail_sendername" not in html
    assert "anon@example.com" in html


def test_forward_container_html_nonascii_from_name_escaped():
    """Non-ASCII from_name is HTML-escaped in output."""
    html = build_forwarded_container_html(
        "Ångström & Müller",
        "user@example.com",
        "Thu, 5 Jun 2025 at 08:00",
        "Unicode test",
        "other@example.com",
        "<div>x</div>",
    )
    # _escape_body must escape & to &amp;
    assert "&amp;" in html
    # Raw ampersand must NOT appear inside the sendername region
    # (it would indicate unescaped content).
    assert "Ångström & Müller" not in html
    # Non-ASCII characters themselves survive (it's only the & that gets escaped).
    assert "Ångström" in html


def test_forward_container_html_subject_escaped():
    """Subject containing < and & must be HTML-escaped."""
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Fri, 6 Jun 2025 at 12:00",
        "Subject <with> &special",
        "bob@example.com",
        "<div>body</div>",
    )
    assert "&lt;with&gt;" in html
    assert "&amp;special" in html
    # Raw < must not appear in the subject field (orig_html may contain it).
    # Check the attr div specifically.
    assert "Subject: Subject &lt;with&gt; &amp;special" in html


def test_forward_container_html_to_rendered_passthrough():
    """to_rendered (pre-rendered HTML) is inserted verbatim, not escaped."""
    to_html = '<a href="mailto:bob@example.com">Bob</a>'
    html = build_forwarded_container_html(
        "Alice",
        "alice@example.com",
        "Fri, 6 Jun 2025 at 12:00",
        "Meeting",
        to_html,
        "<div>body</div>",
    )
    assert to_html in html


def test_forward_container_html_from_email_escaped():
    """from_email containing & must be HTML-escaped in output."""
    html = build_forwarded_container_html(
        "Test User",
        "a&b@example.com",
        "Fri, 6 Jun 2025 at 12:00",
        "Email escape test",
        "recipient@example.com",
        "<div>body</div>",
    )
    # The escaped form must appear (in mailto href and in display text)
    assert "a&amp;b@example.com" in html
    # The raw, unescaped form must NOT appear
    assert "a&b@example.com" not in html


# ---------------------------------------------------------------------------
# build_forwarded_plain tests
# ---------------------------------------------------------------------------


def test_forward_plain_separator():
    """Plain-text separator line must be exact."""
    text = build_forwarded_plain(
        "Jane Roe",
        "jane@example.com",
        "Mon, 2 Jun 2025 at 14:05",
        "Quarterly",
        "joe@example.com",
        "original body",
    )
    assert "---------- Forwarded message ---------" in text


def test_forward_plain_header_lines():
    """All four header lines must appear with correct labels."""
    text = build_forwarded_plain(
        "Jane Roe",
        "jane@example.com",
        "Mon, 2 Jun 2025 at 14:05",
        "Quarterly Report",
        "joe@example.com",
        "original body",
    )
    assert "From: Jane Roe <jane@example.com>" in text
    assert "Date: Mon, 2 Jun 2025 at 14:05" in text
    assert "Subject: Quarterly Report" in text
    assert "To: joe@example.com" in text


def test_forward_plain_orig_not_quoted():
    """Original body must appear as-is (no '> ' quoting)."""
    orig = "line one\nline two"
    text = build_forwarded_plain(
        "Alice",
        "alice@example.com",
        "Sat, 7 Jun 2025 at 11:00",
        "Test",
        "bob@example.com",
        orig,
    )
    assert "> line one" not in text
    assert "line one\nline two" in text


def test_forward_plain_empty_from_name():
    """When from_name is empty, From line uses bare email."""
    text = build_forwarded_plain(
        "",
        "anon@example.com",
        "Sun, 8 Jun 2025 at 07:00",
        "No name",
        "r@example.com",
        "body",
    )
    assert "From: anon@example.com" in text
    assert "<anon@example.com>" not in text


def test_forward_plain_whitespace_only_from_name():
    """Whitespace-only from_name is treated as empty — bare email."""
    text = build_forwarded_plain(
        "  ",
        "anon@example.com",
        "Sun, 8 Jun 2025 at 07:00",
        "No name ws",
        "r@example.com",
        "body",
    )
    assert "From: anon@example.com" in text


def test_forward_plain_scaffold_matches_golden():
    """Plain scaffold structure must agree with golden_forward.json."""
    golden = json.loads((FIX / "golden_forward.json").read_text())
    text = build_forwarded_plain(
        "Jane Roe",
        "jane@example.com",
        "Mon, 2 Jun 2025 at 14:05",
        "Quarterly",
        "joe@example.com",
        "original line one\noriginal line two",
    )
    # The separator line must match the FWD_SEP pattern from the golden scaffold.
    fwd_sep = next(
        (line for line in golden["plain_scaffold"] if line.startswith("FWD_SEP:")), None
    )
    assert fwd_sep is not None
    sep_value = fwd_sep.split(": ", 1)[1]
    assert sep_value in text
    # Header labels must appear in order.
    fwd_hdrs = [
        line for line in golden["plain_scaffold"] if line.startswith("FWD_HDR:")
    ]
    labels = [h.split(": ", 1)[1].split(":")[0] for h in fwd_hdrs]
    pos = [text.index(f"{lbl}:") for lbl in labels]
    assert pos == sorted(pos), "Forward header labels must appear in golden order"


# ---------------------------------------------------------------------------
# assemble_mixed tests
# ---------------------------------------------------------------------------

_PDF_DATA = b"%PDF-1.4 fake"
_PNG_DATA = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


def test_assemble_mixed_tree():
    from gmail.gmail_web_mime import assemble_mixed
    from tools.golden_skeleton import extract_skeleton

    raw = assemble_mixed(
        [("From", "a@example.com"), ("To", "b@example.com"), ("Subject", "Fwd: x")],
        "plain",
        '<div dir="ltr">html</div>',
        [{"filename": "a.pdf", "mime_type": "application/pdf", "data": b"%PDF-1.4"}],
        "000000000000aaaaaaaaaaaaaaaa",
        "000000000000bbbbbbbbbbbbbbbb",
    )
    sk = extract_skeleton(raw.encode("utf-8"))
    top = sk["mime_tree"][0]
    assert top["content_type"] == "multipart/mixed"
    assert top["parts"][0]["content_type"] == "multipart/alternative"
    assert top["parts"][1]["content_type"] == "application/pdf"
    assert top["parts"][1]["disposition"] == "attachment"


def test_assemble_mixed_skeleton_matches_golden():
    """mime_shape from golden_forward_attach.json must match assembled output."""
    from gmail.gmail_web_mime import assemble_mixed
    from tools.golden_skeleton import extract_skeleton

    golden = json.loads((FIX / "golden_forward_attach.json").read_text())
    shape = golden["mime_shape"]

    raw = assemble_mixed(
        [("From", "a@example.com"), ("To", "b@example.com"), ("Subject", "Fwd: y")],
        "plain body",
        '<div dir="ltr">html body</div>',
        [{"filename": "report.pdf", "mime_type": "application/pdf", "data": _PDF_DATA}],
        "000000000000aaaaaaaaaaaaaaaa",
        "000000000000bbbbbbbbbbbbbbbb",
    )
    sk = extract_skeleton(raw.encode("utf-8"))
    top = sk["mime_tree"][0]

    # Top-level content_type
    assert top["content_type"] == shape["content_type"]
    # First child: multipart/alternative
    alt = top["parts"][0]
    assert alt["content_type"] == shape["parts"][0]["content_type"]
    assert (
        alt["parts"][0]["content_type"] == shape["parts"][0]["parts"][0]["content_type"]
    )
    assert (
        alt["parts"][1]["content_type"] == shape["parts"][0]["parts"][1]["content_type"]
    )
    # Second child: attachment
    attach = top["parts"][1]
    assert attach["content_type"] == shape["parts"][1]["content_type"]
    assert attach["disposition"] == shape["parts"][1]["disposition"]
    assert attach["cte"] == shape["parts"][1]["cte"]


def test_assemble_mixed_multiple_attachments_in_order():
    """Two attachments produce two child parts in the order supplied."""
    from gmail.gmail_web_mime import assemble_mixed
    from tools.golden_skeleton import extract_skeleton

    raw = assemble_mixed(
        [("From", "a@example.com"), ("To", "b@example.com"), ("Subject", "Multi")],
        "plain",
        "<div>html</div>",
        [
            {
                "filename": "first.pdf",
                "mime_type": "application/pdf",
                "data": _PDF_DATA,
            },
            {"filename": "second.png", "mime_type": "image/png", "data": _PNG_DATA},
        ],
        "000000000000aaaaaaaaaaaaaaaa",
        "000000000000bbbbbbbbbbbbbbbb",
    )
    sk = extract_skeleton(raw.encode("utf-8"))
    parts = sk["mime_tree"][0]["parts"]
    assert len(parts) == 3  # alt + 2 attachments
    assert parts[1]["content_type"] == "application/pdf"
    assert parts[2]["content_type"] == "image/png"
    assert parts[1]["disposition"] == "attachment"
    assert parts[2]["disposition"] == "attachment"


def test_assemble_mixed_filename_with_space_and_quote():
    """Filenames with spaces and quotes appear correctly in Content-Disposition."""
    from gmail.gmail_web_mime import assemble_mixed

    raw = assemble_mixed(
        [("From", "a@example.com"), ("To", "b@example.com"), ("Subject", "Filename")],
        "plain",
        "<div>html</div>",
        [
            {
                "filename": 'my file "final".pdf',
                "mime_type": "application/pdf",
                "data": b"x",
            }
        ],
        "000000000000aaaaaaaaaaaaaaaa",
        "000000000000bbbbbbbbbbbbbbbb",
    )
    assert (
        'filename="my file \\"final\\".pdf"' in raw
        or 'filename="my file "final".pdf"' in raw
    )
    # At minimum, the filename string appears somewhere in the attachment headers
    assert "my file" in raw


def test_assemble_mixed_inner_alternative_matches_assemble_alternative():
    """Inner alternative subtree body must equal what assemble_alternative produces."""
    from gmail.gmail_web_mime import assemble_alternative, assemble_mixed

    plain_text = "hello world"
    html_text = "<div>hello world</div>"
    boundary_alt = "000000000000bbbbbbbbbbbbbbbb"
    boundary_mixed = "000000000000aaaaaaaaaaaaaaaa"
    headers = [("From", "a@example.com"), ("To", "b@example.com"), ("Subject", "Test")]

    # Build standalone alternative
    alt_standalone = assemble_alternative(headers, plain_text, html_text, boundary_alt)

    # Build mixed and extract the alternative child part body
    mixed = assemble_mixed(
        headers,
        plain_text,
        html_text,
        [{"filename": "x.pdf", "mime_type": "application/pdf", "data": b"x"}],
        boundary_mixed,
        boundary_alt,
    )

    # The alternative child's plain+html QP-encoded bodies must appear in mixed
    # Extract the QP bodies from standalone (they appear between the boundary markers)
    crlf = "\r\n"
    # Get the plain-part QP body from standalone alternative
    plain_marker = f"--{boundary_alt}{crlf}Content-Type: text/plain"
    html_marker = f"--{boundary_alt}{crlf}Content-Type: text/html"
    alt_plain_start = alt_standalone.index(plain_marker)
    alt_html_start = alt_standalone.index(html_marker)
    alt_plain_body = alt_standalone[alt_plain_start:alt_html_start]
    assert alt_plain_body in mixed, (
        "Plain part body from alt must appear verbatim in mixed"
    )
