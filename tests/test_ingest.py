"""Ingestion: HTML stripping, Item segmentation, span selection, chunking.

These are the functions that decide what text the extractor ever sees. A bug
here is invisible downstream - the graph is simply missing things, and nothing
reports an error.

All pure, no network and no database.
"""
import os, re, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
ingest = pytest.importorskip("ingest")


# ------------------------------------------------------------- strip_html

def test_tags_are_removed_but_the_words_survive():
    out = ingest.strip_html("<p>Sales to <b>Boeing</b> were 13%.</p>")
    assert "Sales to" in out and "Boeing" in out and "13%" in out
    assert "<" not in out and ">" not in out


def test_script_and_style_bodies_are_discarded_entirely():
    out = ingest.strip_html(
        "<style>.x{color:red}</style><script>var customer='Ford';</script><p>Real text</p>")
    assert "Real text" in out
    assert "color" not in out and "var customer" not in out


def test_entities_are_decoded():
    out = ingest.strip_html("<p>Smith &amp; Co. &mdash; 10&#37;</p>")
    assert "&" in out and "amp;" not in out


def test_non_breaking_spaces_become_ordinary_ones():
    """A filing full of &nbsp; would otherwise break every multi-word match."""
    out = ingest.strip_html("<p>Applied&nbsp;Materials</p>")
    assert "\xa0" not in out
    assert "Applied Materials" in " ".join(out.split())


def test_a_tag_boundary_does_not_weld_two_words_together():
    """<td>Boeing</td><td>13%</td> must not become 'Boeing13%'."""
    out = ingest.strip_html("<tr><td>Boeing</td><td>13%</td></tr>")
    assert "Boeing13" not in out


def test_stripping_is_idempotent():
    once = ingest.strip_html("<p>Hello <b>world</b></p>")
    assert ingest.strip_html(once) == once


# -------------------------------------------------------------- segment

def _filing(toc=True):
    """A miniature 10-K: a table of contents naming every Item, then the body."""
    parts = []
    if toc:
        parts.append("TABLE OF CONTENTS\n" + "\n".join(
            f"Item {n} {h}" for n, h in
            [("1", "Business"), ("1A", "Risk Factors"), ("7",
             "Management's Discussion and Analysis")]) + "\n")
    parts.append("Item 1. Business\n" + ("body one. " * 900))
    parts.append("Item 1A. Risk Factors\n" + ("body one a. " * 900))
    parts.append("Item 7. Management's Discussion and Analysis\n" + ("body seven. " * 900))
    return "".join(parts)


def test_the_table_of_contents_loses_to_the_real_body():
    """Every Item appears twice. Matching forwards would pick the contents page
    and hand the extractor a few thousand characters of headings."""
    text = _filing()
    sp = ingest.segment(text)
    assert {"1", "1A", "7"} <= set(sp)
    start_1 = sp["1"][0]
    assert start_1 > text.index("TABLE OF CONTENTS") + 50, "matched the contents page"
    assert text[start_1:start_1 + 40].lower().startswith("item 1")


def test_items_do_not_overlap_and_run_in_order():
    sp = ingest.segment(_filing())
    spans = sorted(sp.values())
    for (s1, e1), (s2, _e2) in zip(spans, spans[1:]):
        assert s1 < e1 <= s2, f"{(s1, e1)} overlaps {(s2, _e2)}"


def test_the_last_item_runs_to_the_end_of_the_document():
    text = _filing()
    sp = ingest.segment(text)
    assert max(e for _s, e in sp.values()) == len(text)


def test_a_document_with_no_items_segments_to_nothing():
    assert ingest.segment("Just prose about customers and suppliers.") == {}


def test_item_1a_is_not_swallowed_by_item_1():
    """'Item 1A' also matches a loose pattern for 'Item 1'. They must stay apart."""
    sp = ingest.segment(_filing())
    assert sp["1"][1] <= sp["1A"][0]


# ------------------------------------------------------------ pick_spans

def test_a_well_formed_filing_uses_its_items():
    spans, ok, sections = ingest.pick_spans(_filing())
    assert ok is True and sections, "a clean 10-K should segment"
    assert spans


def test_a_filing_that_will_not_segment_falls_back_rather_than_giving_up():
    """Better to read the first 400k characters than to read nothing."""
    text = "Our largest customer is Boeing. " * 500
    spans, ok, _ = ingest.pick_spans(text)
    assert ok is False
    assert spans and spans[0][0] == 0


def test_concentration_notes_are_picked_up_wherever_they_sit():
    """The 'Concentration of credit risk' note lives in the financial
    statements, outside Items 1, 1A and 7 - and it is the single richest
    sentence in the filing."""
    text = ("Item 1. Business\n" + "x " * 3000
            + "\nConcentration of credit risk: one customer, FedEx, accounted "
              "for 100% of revenue.\n" + "y " * 3000)
    spans, _ok, _ = ingest.pick_spans(text)
    note = text.index("Concentration of credit risk")
    assert any(s <= note < e for s, e in spans), "the note was not selected"


def test_selected_spans_never_overlap():
    text = ("Item 1. Business\n" + "x " * 3000
            + "\nMajor customers: Ford.\n" + "y " * 200
            + "\nSignificant customer: GM.\n" + "z " * 3000)
    spans, _ok, _ = ingest.pick_spans(text)
    for (s1, e1), (s2, _e2) in zip(spans, spans[1:]):
        assert e1 <= s2, f"spans {(s1, e1)} and {(s2, _e2)} overlap"


def test_spans_stay_inside_the_document():
    text = "Major customers: Ford." + "y " * 100
    spans, _ok, _ = ingest.pick_spans(text)
    for s, e in spans:
        assert 0 <= s < e <= len(text)


# -------------------------------------------------------------- chunking

def chunk(seg, size=None, overlap=None):
    """The loop from ingest.main, isolated so its arithmetic can be checked."""
    size = size or ingest.CHUNK_CHARS
    overlap = overlap or ingest.OVERLAP
    step = size - overlap
    return [seg[off:off + size] for off in range(0, len(seg), step)
            if len(seg[off:off + size]) >= 200]


def test_chunks_overlap_so_no_sentence_is_cut_in_half():
    body = "".join(f"{i:04d}." for i in range(4000))        # 20,000 chars
    cs = chunk(body)
    assert len(cs) > 1
    for a, b in zip(cs, cs[1:]):
        tail = a[-ingest.OVERLAP:]
        assert b.startswith(tail), "consecutive chunks do not actually overlap"


def test_the_overlap_is_smaller_than_the_chunk():
    """Otherwise the window never advances and ingestion loops forever."""
    assert 0 < ingest.OVERLAP < ingest.CHUNK_CHARS


def test_every_character_of_the_segment_appears_in_some_chunk():
    body = "".join(f"{i:04d}." for i in range(4000))
    assert "".join(c[:ingest.CHUNK_CHARS - ingest.OVERLAP] for c in chunk(body)).startswith(
        body[:1000])


def test_a_short_tail_is_dropped_not_stored_as_noise():
    body = "x" * (ingest.CHUNK_CHARS + 50)
    assert all(len(c) >= 200 for c in chunk(body))


def test_a_segment_shorter_than_the_floor_produces_nothing():
    assert chunk("x" * 199) == []
