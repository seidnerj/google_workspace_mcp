"""Unit tests for gdocs.docs_markdown_writer."""

import pytest

from gdocs.docs_markdown_writer import markdown_to_docs_requests


def test_empty_markdown_returns_empty_list():
    requests = markdown_to_docs_requests("")
    assert requests == []


def test_returns_list_of_dicts():
    requests = markdown_to_docs_requests("Hello world")
    assert isinstance(requests, list)
    assert len(requests) >= 1, "Non-empty input should produce at least one request"
    assert all(isinstance(r, dict) for r in requests)


def test_single_paragraph_emits_insert_text():
    requests = markdown_to_docs_requests("Hello world")
    inserts = [r for r in requests if "insertText" in r]
    assert len(inserts) == 1
    assert inserts[0]["insertText"]["text"] == "Hello world\n"
    assert inserts[0]["insertText"]["location"]["index"] == 1


def test_two_paragraphs_emit_two_inserts_with_correct_indices():
    requests = markdown_to_docs_requests("First para\n\nSecond para")
    inserts = [r for r in requests if "insertText" in r]
    assert len(inserts) == 2
    assert inserts[0]["insertText"]["text"] == "First para\n"
    assert inserts[0]["insertText"]["location"]["index"] == 1
    # Second paragraph starts after first's text + newline
    assert inserts[1]["insertText"]["text"] == "Second para\n"
    assert inserts[1]["insertText"]["location"]["index"] == 1 + len("First para\n")


def test_h1_emits_insert_and_heading_style():
    requests = markdown_to_docs_requests("# My Title")
    inserts = [r for r in requests if "insertText" in r]
    styles = [r for r in requests if "updateParagraphStyle" in r]
    assert len(inserts) == 1
    assert inserts[0]["insertText"]["text"] == "My Title\n"
    assert len(styles) == 1
    assert styles[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
    # Range should cover the heading text
    rng = styles[0]["updateParagraphStyle"]["range"]
    assert rng["startIndex"] == 1
    assert rng["endIndex"] == 1 + len("My Title\n")


def test_h2_h3_h4_h5_h6_all_emit_correct_named_style():
    for level in range(2, 7):
        hashes = "#" * level
        md = f"{hashes} Heading L{level}"
        requests = markdown_to_docs_requests(md)
        styles = [r for r in requests if "updateParagraphStyle" in r]
        assert len(styles) == 1
        assert styles[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == f"HEADING_{level}"
