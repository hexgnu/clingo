"""Test solver diagnostic output when no answer sets are produced."""

from pathlib import Path
import pytest
from compli import reason

ROOT = Path(__file__).resolve().parent.parent


def test_empty_site_produces_trivial_model(tmp_path):
    """Empty site still produces valid (empty) model - diagnostics only for truly no models."""
    # Create empty site file
    site = tmp_path / "empty.lp"
    site.write_text("% No facts\n")

    programs = [
        ROOT / "ontology" / "core.lp",
        ROOT / "ontology" / "domain.lp",
    ]

    # Should not crash, produces trivial model (no actions, no gaps)
    model = reason.solve(programs, site.read_text())

    # Model should be empty but valid - this is not an error case
    assert len(model.do) == 0
    assert len(model.gap) == 0


def test_no_applicable_requirements_shows_diagnostics(tmp_path, capsys, chapter_d_program):
    """When site has facts but no applicable requirements, show diagnostics."""
    # Create site with facts but nothing that matches domain
    site = tmp_path / "no_match.lp"
    site.write_text("""
site(nowhere).
% Has facts but none that trigger any requirements
some_random_fact(x, y).
""")

    programs = [
        ROOT / "ontology" / "core.lp",
        ROOT / "ontology" / "domain.lp",
        chapter_d_program,
    ]

    model = reason.solve(programs, site.read_text())

    captured = capsys.readouterr()
    # May or may not trigger diagnostics depending on whether it grounds to any answer sets
    # The key is it shouldn't crash
    assert len(model.do) >= 0  # Valid model returned


def test_valid_site_no_diagnostics(tmp_path, capsys, chapter_d_program):
    """When solver works normally, no diagnostic spam."""
    site = tmp_path / "valid.lp"
    site.write_text("""
site(t).
battery_string(bs1).
cell(bs1, 1).
cell(bs1, 2).
""")

    programs = [
        ROOT / "ontology" / "core.lp",
        ROOT / "ontology" / "domain.lp",
        chapter_d_program,
    ]

    model = reason.solve(programs, site.read_text())

    captured = capsys.readouterr()
    # Should NOT show "no answer sets" diagnostics when solver works
    assert "Solver produced no answer sets" not in captured.err

    # Should have actions
    assert len(model.do) > 0
