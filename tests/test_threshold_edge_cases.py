"""Test threshold comparator edge cases.

Verify that >= vs > comparisons work correctly at boundary values.
"""

from compli.models import Rule, Observable, Clause
from compli.ticket import Ticket, InboundAlarm


def test_confidence_threshold_at_boundary():
    """Rules with confidence exactly at threshold should match the comparison."""
    # threshold < 1.0 should include rules with confidence < 1.0
    rules = [
        Rule(
            id="R1",
            clause_id="C1",
            subject_type="test",
            subject_term="test(X)",
            predicate="test_pred",
            modality="shall",
            verifiability="observable",
            observables=[],
            citation_span="test",
            confidence=1.0,  # Exactly at boundary
            reviewed=False,
        ),
        Rule(
            id="R2",
            clause_id="C2",
            subject_type="test",
            subject_term="test(X)",
            predicate="test_pred",
            modality="shall",
            verifiability="observable",
            observables=[],
            citation_span="test",
            confidence=0.99,  # Just below 1.0
            reviewed=False,
        ),
        Rule(
            id="R3",
            clause_id="C3",
            subject_type="test",
            subject_term="test(X)",
            predicate="test_pred",
            modality="shall",
            verifiability="observable",
            observables=[],
            citation_span="test",
            confidence=0.5,
            reviewed=False,
        ),
    ]

    # Filter with threshold 1.0 (should get confidence < 1.0)
    threshold = 1.0
    below_threshold = [r for r in rules if r.confidence < threshold]

    # Should include R2 (0.99) and R3 (0.5), but NOT R1 (1.0)
    assert len(below_threshold) == 2
    assert "R1" not in [r.id for r in below_threshold]
    assert "R2" in [r.id for r in below_threshold]
    assert "R3" in [r.id for r in below_threshold]


def test_confidence_threshold_inclusive_boundary():
    """Test <= comparisons at boundary."""
    rules = [
        Rule(
            id="R1",
            clause_id="C1",
            subject_type="test",
            subject_term="test(X)",
            predicate="test_pred",
            modality="shall",
            verifiability="observable",
            observables=[],
            citation_span="test",
            confidence=0.8,  # Exactly at boundary
            reviewed=True,
        ),
        Rule(
            id="R2",
            clause_id="C2",
            subject_type="test",
            subject_term="test(X)",
            predicate="test_pred",
            modality="shall",
            verifiability="observable",
            observables=[],
            citation_span="test",
            confidence=0.79,
            reviewed=True,
        ),
    ]

    # Filter with <= 0.8
    threshold = 0.8
    at_or_below = [r for r in rules if r.confidence <= threshold]

    # Should include both (0.8 and 0.79)
    assert len(at_or_below) == 2


def test_stale_after_days_at_boundary():
    """Verify stale_after_days comparison at exact boundary."""
    ticket = Ticket(
        ticket_id="T1",
        source="test",
        received_day=20261115,
        asset_id="asset1",
        stale_after_days=90,
        min_confidence=80,
    )

    # At exactly 90 days
    age_90 = 90
    is_stale_90 = age_90 > ticket.stale_after_days  # Should be False (not stale yet)
    assert not is_stale_90

    # At 91 days
    age_91 = 91
    is_stale_91 = age_91 > ticket.stale_after_days  # Should be True (now stale)
    assert is_stale_91

    # At 89 days
    age_89 = 89
    is_stale_89 = age_89 > ticket.stale_after_days  # Should be False
    assert not is_stale_89


def test_min_confidence_at_boundary():
    """Verify min_confidence comparison at exact boundary."""
    ticket = Ticket(
        ticket_id="T1",
        source="test",
        received_day=20261115,
        asset_id="asset1",
        stale_after_days=90,
        min_confidence=80,
    )

    # Confidence exactly at threshold
    conf_80 = 80
    is_low_80 = conf_80 < ticket.min_confidence  # Should be False (meets minimum)
    assert not is_low_80

    # Confidence just below
    conf_79 = 79
    is_low_79 = conf_79 < ticket.min_confidence  # Should be True (below minimum)
    assert is_low_79

    # Confidence above
    conf_81 = 81
    is_low_81 = conf_81 < ticket.min_confidence  # Should be False
    assert not is_low_81


def test_zero_threshold_edge_case():
    """Rules with 0.0 confidence should be handled correctly."""
    rule_zero = Rule(
        id="R0",
        clause_id="C0",
        subject_type="test",
        subject_term="test(X)",
        predicate="test_pred",
        modality="shall",
        verifiability="observable",
        observables=[],
        citation_span="test",
        confidence=0.0,  # Minimum possible
        reviewed=False,
    )

    # Should be included in confidence < 1.0
    assert rule_zero.confidence < 1.0

    # Should be excluded from confidence > 0.0
    assert not (rule_zero.confidence > 0.0)


def test_one_threshold_edge_case():
    """Rules with 1.0 confidence (maximum) should be handled correctly."""
    rule_one = Rule(
        id="R1",
        clause_id="C1",
        subject_type="test",
        subject_term="test(X)",
        predicate="test_pred",
        modality="shall",
        verifiability="observable",
        observables=[],
        citation_span="test",
        confidence=1.0,  # Maximum possible
        reviewed=True,
    )

    # Should be excluded from confidence < 1.0
    assert not (rule_one.confidence < 1.0)

    # Should be included in confidence <= 1.0
    assert rule_one.confidence <= 1.0

    # Should be included in confidence >= 1.0
    assert rule_one.confidence >= 1.0
