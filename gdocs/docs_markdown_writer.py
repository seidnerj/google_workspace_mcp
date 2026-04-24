"""Markdown to Google Docs API batchUpdate request converter.

Parses CommonMark+GFM markdown and emits a list of Docs API request dicts
that, when applied in order, render the markdown into a document or a
specific tab within a document.

Primary entry point - markdown_to_docs_requests(markdown_text, tab_id=None).
"""

from __future__ import annotations

from typing import Optional

from markdown_it import MarkdownIt


def markdown_to_docs_requests(
    markdown_text: str,
    tab_id: Optional[str] = None,
    start_index: int = 1,
) -> list[dict]:
    """Convert markdown to a list of Docs API batchUpdate request dicts.

    Args:
        markdown_text - the markdown source
        tab_id - optional tab ID; when provided, every range targets this tab
        start_index - document index at which content insertion begins

    Returns:
        Ordered list of request dicts. Empty list for empty input.
    """
    if not markdown_text.strip():
        return []

    md = MarkdownIt("commonmark")
    tokens = md.parse(markdown_text)

    requests: list[dict] = []
    _emit_requests(tokens, requests, tab_id, start_index)
    return requests


def _emit_requests(tokens, requests, tab_id, start_index):
    """Walk markdown-it tokens and append Docs API requests.

    Maintains a running `cursor` that represents the current insertion point
    in the document. Each insertText advances cursor by len(text).
    """
    cursor = [start_index]  # mutable via list so helpers can advance it

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])  # 'h1' -> 1
            inline_tok = tokens[i + 1]
            text = _render_inline_plain(inline_tok.children or [])
            text += "\n"
            range_start = cursor[0]
            requests.append(_build_insert_text(cursor[0], text, tab_id))
            cursor[0] += len(text)
            range_end = cursor[0]
            requests.append(
                _build_heading_style(range_start, range_end, level, tab_id)
            )
            i += 3
            continue

        if tok.type == "paragraph_open":
            # paragraph_open is followed by inline (children), then paragraph_close
            inline_tok = tokens[i + 1]
            text = _render_inline_plain(inline_tok.children or [])
            text += "\n"
            requests.append(_build_insert_text(cursor[0], text, tab_id))
            cursor[0] += len(text)
            i += 3  # skip paragraph_open, inline, paragraph_close
            continue

        i += 1


def _render_inline_plain(children) -> str:
    """Render inline tokens as plain text, ignoring styling for now.

    Tasks 7+ expand this to handle bold, italic, code, links.
    """
    out = []
    for child in children:
        if child.type == "text":
            out.append(child.content)
        elif child.type == "softbreak":
            out.append(" ")
        elif child.type == "hardbreak":
            out.append("\n")
    return "".join(out)


def _build_insert_text(index: int, text: str, tab_id: Optional[str]) -> dict:
    """Build an insertText request dict, threading tab_id if provided."""
    location = {"index": index}
    if tab_id:
        location["tabId"] = tab_id
    return {"insertText": {"location": location, "text": text}}


def _build_heading_style(
    start: int, end: int, level: int, tab_id: Optional[str]
) -> dict:
    """Build updateParagraphStyle request setting HEADING_N named style."""
    rng = {"startIndex": start, "endIndex": end}
    if tab_id:
        rng["tabId"] = tab_id
    return {
        "updateParagraphStyle": {
            "range": rng,
            "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
            "fields": "namedStyleType",
        }
    }
