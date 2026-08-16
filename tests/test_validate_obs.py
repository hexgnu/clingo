"""Test observation validation against known rules."""

import pytest
from eiguide.models import Observation, Rule, Observable, Modality
from eiguide.validate_obs import validate_observations


def test_valid_observations_pass():
    """Observations matching known rules produce no warnings."""
    rules = [
        Rule(
            id="D.1a",
            clause_id="D.1",
            subject_type="cell",
            subject_term="cell(S,C)",
            predicate="has_label",
            modality="shall",
            verifiability="observable",
            observables=[Observable(name="cell_label_present", kind="photo", target="cell", method="visual")],
            citation_span="labeled",
        )
    ]

    observations = [
        Observation(subject="cell(bs1,1)", observable="cell_label_present", value=True),
        Observation(subject="cell(bs1,2)", observable="cell_label_present", value=False),
    ]

    problems = validate_observations(observations, rules)
    assert len(problems) == 0


def test_unknown_observable_warns():
    """Observations with unknown observable names produce warnings."""
    rules = [
        Rule(
            id="D.1a",
            clause_id="D.1",
            subject_type="cell",
            subject_term="cell(S,C)",
            predicate="has_label",
            modality="shall",
            verifiability="observable",
            observables=[Observable(name="cell_label_present", kind="photo", target="cell", method="visual")],
            citation_span="labeled",
        )
    ]

    observations = [
        Observation(subject="cell(bs1,1)", observable="cell_label_presnt", value=True),  # typo
    ]

    problems = validate_observations(observations, rules)
    assert len(problems) == 1
    assert "cell_label_presnt" in problems[0]
    assert "not found in rules" in problems[0]


def test_strict_mode_raises():
    """Strict mode raises on unknown observables."""
    rules = [
        Rule(
            id="D.1a",
            clause_id="D.1",
            subject_type="cell",
            subject_term="cell(S,C)",
            predicate="has_label",
            modality="shall",
            verifiability="observable",
            observables=[Observable(name="correct_name", kind="photo", target="cell", method="visual")],
            citation_span="labeled",
        )
    ]

    observations = [
        Observation(subject="cell(bs1,1)", observable="wrong_name", value=True),
    ]

    with pytest.raises(ValueError, match="unknown observable"):
        validate_observations(observations, rules, strict=True)


def test_non_field_verifiable_rules_ignored():
    """Rules that aren't field-verifiable don't contribute observables."""
    rules = [
        Rule(
            id="D.1a",
            clause_id="D.1",
            subject_type="cell",
            subject_term="cell(S,C)",
            kind="exemption",  # Not an obligation
            predicate="has_label",
            modality="shall",
            verifiability="observable",
            observables=[Observable(name="some_obs", kind="photo", target="cell", method="visual")],
            citation_span="labeled",
        ),
        Rule(
            id="D.1b",
            clause_id="D.1",
            subject_type="cell",
            subject_term="cell(S,C)",
            predicate="documented",
            modality="shall",
            verifiability="documentary",  # Not field-verifiable
            observables=[Observable(name="other_obs", kind="document", target="record", method="review")],
            citation_span="documented",
        ),
    ]

    # These observables shouldn't be recognized because rules aren't field-verifiable
    observations = [
        Observation(subject="cell(bs1,1)", observable="some_obs", value=True),
        Observation(subject="cell(bs1,1)", observable="other_obs", value=True),
    ]

    problems = validate_observations(observations, rules)
    # Both should be flagged as unknown
    assert len(problems) == 2
