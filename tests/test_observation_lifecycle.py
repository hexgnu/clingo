"""Test observation value edge cases and full lifecycle."""

from pathlib import Path
import pytest

from eiguide.models import Observation, Evidence, EvidenceSource
from eiguide.reason import observations_to_facts
from eiguide.store import write_jsonl, read_jsonl


def test_observation_bool_values():
    """Observations handle both pass and fail values."""
    obs_pass = Observation(subject="cell(bs1,1)", observable="labeled", value=True)
    obs_fail = Observation(subject="cell(bs1,2)", observable="labeled", value=False)

    assert obs_pass.value is True
    assert obs_fail.value is False


def test_observation_with_note():
    """Observations can include notes about failures."""
    obs = Observation(
        subject="cell(bs1,7)",
        observable="cell_number_legible",
        value=False,
        note="Label obscured by corrosion"
    )

    assert obs.note == "Label obscured by corrosion"


def test_observation_with_action():
    """Observations can reference the action that produced them."""
    obs = Observation(
        subject="cell(bs1,1)",
        observable="labeled",
        value=True,
        action="sweep(bs1)"
    )

    assert obs.action == "sweep(bs1)"


def test_observation_to_evidence_conversion():
    """Observations convert to Evidence model with provenance."""
    obs = Observation(
        subject="cell(bs1,1)",
        observable="cell_number_legible",
        value=True,
        note="Clear and readable"
    )

    source = EvidenceSource(type="human", id="inspector_alice")
    ev = obs.to_evidence("evidence_1", source, timestamp=1723567890)

    assert ev.id == "evidence_1"
    assert ev.kind == "observation"
    assert ev.subject == "cell(bs1,1)"
    assert ev.property == "cell_number_legible"
    assert ev.value is True
    assert ev.source.type == "human"
    assert ev.source.id == "inspector_alice"
    assert ev.timestamp == 1723567890
    assert ev.notes == "Clear and readable"


def test_observations_to_facts_generates_both_formats():
    """observations_to_facts generates both obs/3 and evidence/8."""
    obs = [
        Observation(subject="cell(bs1,1)", observable="labeled", value=True),
        Observation(subject="cell(bs1,2)", observable="labeled", value=False),
    ]

    source = EvidenceSource(type="human", id="inspector")
    facts = observations_to_facts(obs, source)

    # Should have legacy obs/3 facts
    assert "obs(cell(bs1,1), labeled, true)" in facts
    assert "obs(cell(bs1,2), labeled, false)" in facts

    # Should have new evidence/8 facts
    assert "evidence(evidence_0" in facts
    assert "evidence(evidence_1" in facts
    assert "observation" in facts  # evidence kind


def test_observation_persistence_roundtrip(tmp_path):
    """Observations serialize to/from JSONL correctly."""
    obs_list = [
        Observation(subject="cell(bs1,1)", observable="labeled", value=True),
        Observation(subject="cell(bs1,2)", observable="legible", value=False, note="worn"),
        Observation(subject="cable(l1)", observable="tagged", value=True, action="photo(l1)"),
    ]

    path = tmp_path / "obs.jsonl"
    write_jsonl(path, obs_list)

    loaded = read_jsonl(path, Observation)

    assert len(loaded) == 3
    assert loaded[0].subject == "cell(bs1,1)"
    assert loaded[0].value is True
    assert loaded[1].note == "worn"
    assert loaded[2].action == "photo(l1)"


def test_observation_without_optional_fields():
    """Observations work with minimal fields."""
    obs = Observation(
        subject="node(core01)",
        observable="powered",
        value=True
    )

    assert obs.note is None
    assert obs.action is None


def test_empty_observation_list_to_facts():
    """Empty observation list produces empty facts."""
    facts = observations_to_facts([])
    assert facts == ""


def test_observation_special_characters_in_subject():
    """Observations handle subjects with special ASP characters."""
    obs = Observation(
        subject='cable("weird-name", rack_1)',
        observable="tagged",
        value=True
    )

    # Should serialize without errors
    assert obs.subject == 'cable("weird-name", rack_1)'


def test_multiple_observations_same_subject():
    """Multiple observations for same subject are independent."""
    obs1 = Observation(subject="cell(bs1,1)", observable="labeled", value=True)
    obs2 = Observation(subject="cell(bs1,1)", observable="polarity_marked", value=False)

    assert obs1.observable != obs2.observable
    assert obs1.value != obs2.value


def test_observation_value_type_is_bool():
    """Observation value is strictly boolean."""
    obs_true = Observation(subject="x", observable="y", value=True)
    obs_false = Observation(subject="x", observable="y", value=False)

    assert isinstance(obs_true.value, bool)
    assert isinstance(obs_false.value, bool)
    assert obs_true.value is not 1
    assert obs_false.value is not 0
