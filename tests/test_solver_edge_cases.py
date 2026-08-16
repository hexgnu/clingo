"""Test solver behavior with unusual but valid ASP programs."""

from pathlib import Path
import pytest
from compli import reason

ROOT = Path(__file__).resolve().parent.parent


def test_solver_with_optimization_but_no_valid_solutions(tmp_path):
    """Test diagnostic output when optimization problem has no valid solutions."""
    # Program with impossible constraints
    program = tmp_path / "impossible.lp"
    program.write_text("""
% Require X and not X simultaneously
item(a).
:- item(X), selected(X).
:- item(X), not selected(X).
""")

    with pytest.raises(RuntimeError, match="UNSATISFIABLE"):
        reason.solve([program])


def test_solver_with_all_weak_constraints(tmp_path, capsys):
    """Program with only weak constraints (optimization) should produce models."""
    program = tmp_path / "weak.lp"
    program.write_text("""
item(1..3).
{ selected(X) } :- item(X).
:~ selected(X). [1@1, X]  % Prefer not selecting items
#show selected/1.
""")

    model = reason.solve([program])

    # Should produce a model (likely selecting nothing due to weak constraint)
    # This is valid - not a diagnostic case
    captured = capsys.readouterr()
    assert "Solver produced no answer sets" not in captured.err
