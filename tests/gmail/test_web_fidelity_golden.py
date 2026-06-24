import json
import pathlib

from gmail.gmail_web_mime import BLOCKQUOTE_STYLE

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_blockquote_style_matches_current_golden():
    golden = json.loads((FIX / "golden_reply.json").read_text())
    assert BLOCKQUOTE_STYLE == golden["html_probes"]["blockquote_style"]
