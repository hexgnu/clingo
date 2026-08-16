"""Tests for unified Evidence model with identity, provenance, temporal ordering."""

import time
import pytest
from eiguide.models import Evidence, EvidenceSource, Observation


def test_evidence_source_model():
    """EvidenceSource captures who/what produced evidence."""
    human = EvidenceSource(type="human", id="inspector_alice")
    assert human.type == "human"
    assert human.id == "inspector_alice"
    assert human.system is None

    system = EvidenceSource(type="system", id="nms_01", system="samsung_nms")
    assert system.type == "system"
    assert system.system == "samsung_nms"


def test_evidence_model_basic():
    """Evidence model includes identity, provenance, temporal data."""
    source = EvidenceSource(type="human", id="alice")
    ev = Evidence(
        id="evidence_1",
        kind="observation",
        subject="cell(bs1,7)",
        property="cell_number_legible",
        value=True,
        source=source,
        timestamp=1723567890,
        confidence=1.0
    )

    assert ev.id == "evidence_1"
    assert ev.kind == "observation"
    assert ev.subject == "cell(bs1,7)"
    assert ev.property == "cell_number_legible"
    assert ev.value is True
    assert ev.source.id == "alice"
    assert ev.timestamp == 1723567890
    assert ev.confidence == 1.0


def test_evidence_to_asp_boolean_value():
    """Evidence with boolean value renders correctly."""
    source = EvidenceSource(type="human", id="alice")
    ev = Evidence(
        id="e1",
        kind="observation",
        subject="cell(bs1,7)",
        property="legible",
        value=True,
        source=source,
        timestamp=100,
        confidence=0.95
    )

    asp = ev.to_asp()
    assert "evidence(e1, observation, cell(bs1,7), legible, true," in asp
    assert "source(human, \"alice\")" in asp
    assert "100, 95/100)" in asp  # Confidence as fraction to avoid ASP decimal issues


def test_evidence_to_asp_string_value():
    """Evidence with string value is quoted."""
    source = EvidenceSource(type="system", id="nms", system="samsung")
    ev = Evidence(
        id="e2",
        kind="test_result",
        subject="link(uplink_3)",
        property="status",
        value="down",
        source=source,
        timestamp=200,
        confidence=0.8
    )

    asp = ev.to_asp()
    assert 'evidence(e2, test_result, link(uplink_3), status, "down",' in asp
    assert 'source(system, "nms", "samsung")' in asp


def test_evidence_to_asp_numeric_value():
    """Evidence with numeric value renders as number."""
    source = EvidenceSource(type="sensor", id="pdu_01")
    ev = Evidence(
        id="e3",
        kind="measurement",
        subject="circuit(c1)",
        property="amperage",
        value=42.5,
        source=source,
        timestamp=300,
        confidence=1.0
    )

    asp = ev.to_asp()
    # Float converted to fraction for ASP compatibility
    assert "85/2" in asp or "42.5" in asp  # 42.5 = 85/2


def test_observation_to_evidence_conversion():
    """Legacy Observation converts to Evidence with provenance."""
    obs = Observation(
        subject="cell(bs1,7)",
        observable="cell_number_legible",
        value=True,
        action="photo",
        note="Clear and legible"
    )

    source = EvidenceSource(type="human", id="inspector_bob")
    ev = obs.to_evidence("evidence_1", source, timestamp=123456)

    assert ev.id == "evidence_1"
    assert ev.kind == "observation"
    assert ev.subject == "cell(bs1,7)"
    assert ev.property == "cell_number_legible"
    assert ev.value is True
    assert ev.source.id == "inspector_bob"
    assert ev.timestamp == 123456
    assert ev.method == "photo"
    assert ev.notes == "Clear and legible"
    assert ev.confidence == 1.0


def test_observation_to_evidence_default_timestamp():
    """Observation conversion uses current time if not provided."""
    obs = Observation(
        subject="cell(bs1,1)",
        observable="polarity_marked",
        value=False
    )

    source = EvidenceSource(type="human", id="alice")
    before = int(time.time())
    ev = obs.to_evidence("e1", source)
    after = int(time.time())

    assert before <= ev.timestamp <= after


def test_evidence_confidence_validation():
    """Confidence must be between 0.0 and 1.0."""
    source = EvidenceSource(type="human", id="alice")

    # Valid range
    ev = Evidence(
        id="e1",
        kind="observation",
        subject="s",
        property="p",
        value=True,
        source=source,
        timestamp=100,
        confidence=0.5
    )
    assert ev.confidence == 0.5

    # Out of range should fail validation
    with pytest.raises(Exception):  # Pydantic ValidationError
        Evidence(
            id="e2",
            kind="observation",
            subject="s",
            property="p",
            value=True,
            source=source,
            timestamp=100,
            confidence=1.5  # Invalid
        )


def test_evidence_with_incident_correlation():
    """Evidence can be grouped by incident ID."""
    source = EvidenceSource(type="system", id="nms")
    
    ev1 = Evidence(
        id="e1",
        kind="alarm",
        subject="node(core01)",
        property="reachable",
        value=False,
        source=source,
        timestamp=100,
        incident_id="incident_5120"
    )

    ev2 = Evidence(
        id="e2",
        kind="alarm",
        subject="link(uplink_3)",
        property="status",
        value="down",
        source=source,
        timestamp=101,
        incident_id="incident_5120"
    )

    assert ev1.incident_id == ev2.incident_id
    assert ev1.incident_id == "incident_5120"


def test_multiple_observations_to_facts():
    """Multiple observations generate sequential evidence IDs and timestamps."""
    from eiguide.reason import observations_to_facts

    obs1 = Observation(subject="cell(bs1,1)", observable="legible", value=True)
    obs2 = Observation(subject="cell(bs1,2)", observable="legible", value=False)

    source = EvidenceSource(type="human", id="alice")
    facts = observations_to_facts([obs1, obs2], source)

    # Should contain both legacy obs/3 and new evidence/8 facts
    assert "obs(cell(bs1,1), legible, true)" in facts
    assert "obs(cell(bs1,2), legible, false)" in facts
    assert "evidence(evidence_0" in facts
    assert "evidence(evidence_1" in facts
    assert 'source(human, "alice")' in facts
