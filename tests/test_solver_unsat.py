"""Tests for solver UNSAT and unsatisfiable constraint scenarios.

These tests verify the system handles gracefully when clingo returns zero models
due to contradictory facts, impossible constraints, or empty sites.
"""

import pytest
from pathlib import Path
from compli import reason


def test_empty_site_returns_empty_model(tmp_path: Path) -> None:
    """Empty site with no facts should return empty model, not crash."""
    empty_site = tmp_path / "empty.lp"
    empty_site.write_text("% No facts\n")
    
    core = Path("ontology/core.lp")
    domain = Path("ontology/domain.lp")
    
    model = reason.solve([core, domain, empty_site], "")
    
    # Empty model - no subjects means no requirements apply
    assert model.do == []
    assert model.gap == []
    assert model.satisfied == []
    assert model.violated == []
    assert model.undetermined == []


def test_contradictory_site_facts_raise_error(tmp_path: Path) -> None:
    """Site with contradictory facts should raise RuntimeError with UNSAT message."""
    bad_site = tmp_path / "contradictory.lp"
    # Create an impossible constraint that cannot be satisfied
    bad_site.write_text("""
battery_string(bs1).
cell(bs1, 1..24).
% Impossible integrity constraints - always fails
:- battery_string(bs1).
""")

    core = Path("ontology/core.lp")
    domain = Path("ontology/domain.lp")

    with pytest.raises(RuntimeError) as exc_info:
        reason.solve([core, domain, bad_site], "")

    assert "UNSATISFIABLE" in str(exc_info.value)
    assert "contradictory" in str(exc_info.value).lower()


def test_impossible_cost_constraints(tmp_path: Path) -> None:
    """Test when all actions exceed budget constraint (if such constraints existed)."""
    # This would test cost ceiling constraints if the system had them
    # Currently the solver always finds *some* plan if requirements apply
    # So this is a placeholder for future cost-bounded planning
    pass


def test_site_with_no_applicable_requirements(tmp_path: Path) -> None:
    """Site facts that match no requirements should produce empty plan."""
    irrelevant_site = tmp_path / "irrelevant.lp"
    # Facts that don't trigger any rules in Chapter D
    irrelevant_site.write_text("""
% Made-up equipment type not in Chapter D
widget(w1).
gadget(g1).
""")
    
    core = Path("ontology/core.lp")
    domain = Path("ontology/domain.lp")
    chapter_d = Path("rules/chapter_d.lp")
    
    if not chapter_d.exists():
        pytest.skip("Chapter D rules not compiled")
    
    model = reason.solve([core, domain, chapter_d, irrelevant_site], "")
    
    # No requirements apply to widgets/gadgets
    assert model.do == []
    assert model.gap == []
    assert len(model.undetermined) == 0  # Nothing to determine


def test_grounding_error_from_malformed_asp(tmp_path: Path) -> None:
    """Malformed ASP syntax should raise RuntimeError during grounding."""
    bad_syntax = tmp_path / "bad_syntax.lp"
    bad_syntax.write_text("""
battery_string(bs1).
cell(bs1, UNBOUND_VARIABLE).  % Unbound variable in fact
""")
    
    core = Path("ontology/core.lp")
    
    with pytest.raises(RuntimeError) as exc_info:
        reason.solve([core, bad_syntax], "")
    
    # Should fail during load or ground, not silently
    assert "Failed to load" in str(exc_info.value) or "grounding failed" in str(exc_info.value).lower()
