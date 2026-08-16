"""Extraction fidelity.

These assertions are about the *source document*, so they fail loudly if a change to the
layout heuristics quietly starts dropping or corrupting clauses.
"""

from __future__ import annotations

import re

import pymupdf
import pytest

from eiguide import layout
from eiguide.extract import classify_modality
from tests.conftest import PDF

EXPECTED_CHAPTERS = set("ABCDEFGHIJK")


def test_every_chapter_is_recovered(clauses):
    found = {c.chapter for c in clauses}
    assert EXPECTED_CHAPTERS <= found, f"missing chapters: {EXPECTED_CHAPTERS - found}"


def test_clause_volume_is_plausible(clauses):
    # The document contains ~380 "shall" clauses; a large swing either way means the
    # paragraph segmentation has broken rather than improved.
    assert 450 <= len(clauses) <= 700
    binding = [c for c in clauses if c.modality in ("shall", "must", "imperative")]
    assert len(binding) >= 400


def test_layout_conventions_are_inferred_not_assumed():
    doc = pymupdf.open(PDF)
    try:
        lay = layout.analyze(doc)
        # Nothing tells the analyzer this document numbers clauses "6.6"; it works it out.
        assert lay.label_family == "dotted"
        header_bottom, footer_top = layout.chrome_bands(doc)
        assert header_bottom > 0 and footer_top < doc[0].rect.height
    finally:
        doc.close()


def test_battery_labelling_clause_is_verbatim(clause_index):
    clause = clause_index["D.6.6"]
    assert clause.page_label == "D-4"
    assert clause.chapter_title == "Equipment and Cable Designations"
    assert clause.text.startswith("Designate all batteries with black ink")
    # The whole clause must survive, including the sentences after the first.
    assert "Start labeling cell #1 from the positive end of the string" in clause.text
    assert "specification number" in clause.text


def test_ligatures_and_wrapping_survive(clauses):
    """Word-breaks and ligatures must not corrupt terms.

    A hand-rolled CID decoder on this file turns "fiber" into "Über" and joins hyphenated
    line breaks into "cus tomer". Both are silent corruptions that would poison every
    downstream consumer, so they are asserted against directly.
    """
    blob = " ".join(c.text for c in clauses)
    for corruption in ("Über", "Ýow", "conÜdential", "speciÜcation", "identiÜcation"):
        assert corruption not in blob
    assert "\xad" not in blob
    assert "cus tomer" not in blob
    assert "fiber" in blob.lower()


class TestTextIntegrity:
    """Corruptions that pass unnoticed because the output still looks like prose.

    Each of these shipped undetected until the corpus was measured rather than sampled.
    """

    def test_no_word_is_broken_across_a_line_break(self, clauses):
        """"applica- ble" reads as two tokens to everything downstream.

        34 clauses carried a break like this. The soft-hyphen case was handled; the plain
        ASCII hyphen was not, and only a corpus-wide count exposed it.
        """
        broken = [c.id for c in clauses if re.search(r"[a-z]- [a-z]", c.text)]
        assert broken == [], f"{len(broken)} clauses with split words, e.g. {broken[:5]}"

    def test_genuine_compounds_survive(self, clauses):
        """The repair must not fuse a real hyphenated compound into one word."""
        blob = " ".join(c.text for c in clauses)
        assert "wholedocument" not in blob.lower()
        assert re.search(r"\bas-built\b|\bwhole-document\b|\bon-line\b", blob, re.IGNORECASE)

    def test_clauses_are_not_truncated_at_a_page_break(self, clauses):
        """A clause continuing onto the next page used to lose its tail entirely.

        K.7.11 ended at "...on the same termi-" with the rest dropped. Nothing failed,
        because a truncated clause is still a plausible-looking clause.
        """
        cut = [c.id for c in clauses if c.text.rstrip().endswith("-")]
        assert cut == [], f"clauses cut mid-word: {cut}"

    def test_every_clause_id_is_unique(self, clauses):
        """Chapter K numbers three consecutive clauses "2.2" -- a defect in the standard.

        Any lookup keyed by clause id keeps one and silently drops the rest, so two real
        requirements vanish from citations. Ids must stay unique even when the source is
        not.
        """
        ids = [c.id for c in clauses]
        assert len(ids) == len(set(ids)), "duplicate clause ids would be silently dropped"

    def test_source_defects_are_reported_not_hidden(self, source_warnings, clauses):
        assert any("K.2.2" in w for w in source_warnings), source_warnings
        flagged = [c for c in clauses if c.duplicate_label]
        assert len(flagged) == len(source_warnings)
        # The disambiguated clauses must still carry their real, distinct text.
        texts = {c.text for c in clauses if c.id.startswith("K.2.2")}
        assert len(texts) == 3, "the three K.2.2 clauses collapsed into one"


def test_table_of_contents_is_not_mistaken_for_clauses(clauses):
    for clause in clauses:
        assert not re.search(r"\.{4,}", clause.text), f"TOC leader survived in {clause.id}"


def test_chapter_g_alternate_layout_is_handled(clause_index):
    """Chapter G puts the clause number on its own line instead of inline.

    It is the one place in the document that breaks the dominant layout, so it is the
    canary for the two-form paragraph splitter.
    """
    clause = clause_index["G.1.1"]
    assert "Fiber Guide System" in clause.text
    assert clause.modality == "must"


class TestModality:
    """Obligation is not signalled by the word "shall" alone."""

    def test_shall_outranks_weaker_modals(self):
        assert classify_modality("The rack shall be bonded, and should be labelled.") == "shall"

    def test_bare_imperative_counts_as_binding(self):
        assert classify_modality("Designate fuse panels with row designations.") == "imperative"

    def test_imperative_outranks_a_trailing_should(self):
        # D.6.6 opens with a command and closes with an advisory sentence. Ranking it
        # "should" would demote a real obligation.
        text = "Designate all batteries with black ink. The last cell should have the symbol."
        assert classify_modality(text) == "imperative"

    def test_prose_is_not_an_obligation(self):
        assert classify_modality("ADC Telecommunications is the approved vendor.") == "descriptive"


def test_figures_and_tables_are_captured(extraction):
    _, figures, tables, _ = extraction
    assert len(figures) > 20
    assert any(f.id == "D1" for f in figures)
    assert len(tables) > 5


@pytest.mark.parametrize(
    "clause_id,needle",
    [
        ("D.6.5", '"FUSE RECORD"'),
        ("D.6.10", '"Do Not Disconnect"'),
        ("H.10.2", "except with written permission"),
        ("D.6.8", "do not require 145C tags"),
    ],
)
def test_known_clauses_round_trip(clause_index, clause_id, needle):
    assert needle in clause_index[clause_id].text


def test_extract_handles_empty_pdf(tmp_path):
    """Extract gracefully handles PDF with no numbered content."""
    # This would test with a minimal PDF, but we don't have one
    # Real test would require generating or mocking a PDF
    # Placeholder for future implementation
    pass


def test_extract_handles_truncated_pdf(tmp_path):
    """Extract detects and reports truncated/corrupted PDFs."""
    # Would test with corrupted PDF file
    # Placeholder - actual implementation needs corrupted test file
    pass
