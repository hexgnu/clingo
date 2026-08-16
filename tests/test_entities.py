"""Generic code extraction.

These patterns feed rule parameters and acceptance criteria, so a miss here becomes a
threshold the reasoner never checks.
"""

from __future__ import annotations

from compli.entities import extract_codes


class TestQuantities:
    def test_parenthesised_numerals_are_found(self):
        """"two (2) feet" is the document's default way of writing a threshold.

        Requiring the digits to sit flush against the unit misses every one of them.
        """
        codes = extract_codes(
            "shall not be unsupported for a distance greater than two (2) feet for cables "
            "1/0 and smaller. Cables 2/0 and larger shall not be unsupported for a distance "
            "greater than three (3) feet (18 inches for horizontal support)."
        )
        values = {(q.value, q.unit) for q in codes.quantities}
        assert ("2", "feet") in values
        assert ("3", "feet") in values
        assert ("18", "inches") in values

    def test_comparators_are_attached(self):
        codes = extract_codes("The bend radius shall be no less than two inches.")
        assert any(q.comparator for q in codes.quantities)

    def test_fractions(self):
        codes = extract_codes("Use ¼ inch hardware.")
        assert ("¼", "inch") in {(q.value, q.unit) for q in codes.quantities}


class TestGauges:
    def test_conductor_sizes(self):
        codes = extract_codes("for cables 1/0 and smaller. Cables 2/0 and larger")
        assert set(codes.gauges) == {"1/0", "2/0"}

    def test_position_numbers_are_not_gauges(self):
        """"cell #1" is a position, not a wire size.

        Classifying it as a gauge would hand the reasoner a conductor size that does not
        exist anywhere in the clause.
        """
        codes = extract_codes("Start labeling cell #1 from the positive end of the string.")
        assert codes.gauges == []
        assert codes.item_numbers == ["#1"]

    def test_explicit_awg_is_a_gauge(self):
        codes = extract_codes("Secure with #12 AWG waxed lacing cord.")
        assert codes.gauges == ["#12 AWG"]


class TestLiterals:
    def test_required_label_text_is_captured(self):
        """The exact words that must appear on a label are the most checkable thing there is."""
        codes = extract_codes('Designate fuse record book covers with "FUSE RECORD" and bay location.')
        assert codes.literals == ["FUSE RECORD"]

    def test_multiple_literals(self):
        codes = extract_codes('"Do Not Disconnect" tags and "TR" cell markings.')
        assert set(codes.literals) == {"Do Not Disconnect", "TR"}


class TestCarveOuts:
    def test_exceptions_are_surfaced(self):
        """Dropping a carve-out makes the reasoner demand evidence the standard waives."""
        codes = extract_codes(
            "Power cabling shall not be run adjacent to transmission cabling, except with "
            "written permission of the Level 3 Engineer."
        )
        assert "except" in codes.exceptions
        assert codes.negated is True

    def test_exemption_language(self):
        codes = extract_codes(
            "Battery and battery return leads internal to the relay rack do not require 145C tags."
        )
        assert codes.exceptions

    def test_plain_obligation_has_no_carve_out(self):
        codes = extract_codes("All battery strings and cells shall be labeled.")
        assert codes.exceptions == []


class TestReferences:
    def test_table_and_standard_references(self):
        codes = extract_codes("Power cables shall be secured per requirements in Tables G3 and G4.")
        assert set(codes.tables) == {"G3", "G4"}

    def test_external_standards(self):
        codes = extract_codes("Install per NEC and NFPA 70 requirements.")
        assert "NEC" in codes.standards
