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
    _, figures, tables = extraction
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
