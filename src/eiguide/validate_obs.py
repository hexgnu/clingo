"""Validate observations match known rules to catch typos early."""

from __future__ import annotations

from .models import Observation, Rule


def validate_observations(
    observations: list[Observation],
    rules: list[Rule],
    strict: bool = False,
) -> list[str]:
    """Check that observable names in observations match those in rules.

    Args:
        observations: Observations to validate
        rules: Rules defining known observables
        strict: If True, raise on unknown observables; if False, just warn

    Returns:
        List of warning/error messages about unknown observables

    This catches common typos like "cell_number_legible" vs "cell_number_legable"
    before they silently produce incomplete verdicts.
    """
    # Build index of known observables from field-verifiable rules
    known = {obs.name for rule in rules for obs in rule.observables if rule.field_verifiable}

    problems = []
    seen_unknown = set()

    for obs_rec in observations:
        if obs_rec.observable not in known and obs_rec.observable not in seen_unknown:
            seen_unknown.add(obs_rec.observable)
            problems.append(
                f"Observable '{obs_rec.observable}' not found in rules. Possible typo?\n"
                f"  Subject: {obs_rec.subject}\n"
                f"  Known observables: {', '.join(sorted(known)[:8])}..."
            )

    if strict and problems:
        raise ValueError(
            f"{len(problems)} unknown observable(s) found:\n" + "\n".join(problems)
        )

    return problems
