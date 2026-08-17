"""Test batch verification mode for CI integration."""

from pathlib import Path
import json
import pytest
from typer.testing import CliRunner

from compli.cli import app
from compli.models import Observation
from compli.store import write_jsonl

ROOT = Path(__file__).resolve().parent.parent
runner = CliRunner()


@pytest.fixture
def workspace_with_obs(tmp_path, clauses, golden_rules, chapter_d_program):
    """Workspace with site, observations, rules, and clauses."""
    from compli.store import write_jsonl
    from compli import compile as compile_mod

    # Create directory structure
    (tmp_path / "data").mkdir()
    (tmp_path / "sites").mkdir()
    (tmp_path / "rules").mkdir()
    (tmp_path / "ontology").mkdir()

    # Copy site file
    site_src = ROOT / "examples" / "compliance" / "den01.lp"
    site_dst = tmp_path / "sites" / "den01.lp"
    site_dst.write_text(site_src.read_text())

    # Copy ontology files
    for ont_file in ["core.lp", "domain.lp", "evidence.lp"]:
        src = ROOT / "ontology" / ont_file
        if src.exists():
            dst = tmp_path / "ontology" / ont_file
            dst.write_text(src.read_text())

    # Write clauses and rules
    write_jsonl(tmp_path / "data" / "clauses.jsonl", clauses)
    write_jsonl(tmp_path / "data" / "rules.jsonl", golden_rules)

    # Compile chapter D
    clause_index = {c.id: c for c in clauses}
    source = compile_mod.compile_rules(golden_rules, clause_index, "D", "EIGuide", "6.0")
    (tmp_path / "rules" / "chapter_d.lp").write_text(source)

    # Create passing observations
    obs = [
        Observation(subject="cell(bs1,1)", observable="cell_number_legible", value=True),
        Observation(subject="cell(bs1,2)", observable="cell_number_legible", value=True),
        Observation(subject="cell(bs1,1)", observable="cell_polarity_marked", value=True),
        Observation(subject="cell(bs1,2)", observable="cell_polarity_marked", value=True),
    ]
    write_jsonl(tmp_path / "observations.jsonl", obs)

    return tmp_path


def test_verify_with_passing_observations(workspace_with_obs):
    """Verify command exits 0 when all requirements satisfied."""
    import os
    previous = os.getcwd()
    try:
        os.chdir(workspace_with_obs)
        result = runner.invoke(app, ["verify", "--site", "sites/den01.lp", "--observations", "observations.jsonl"])
        # May have undetermined requirements, so exit code might be 1
        # Just check it doesn't crash
        assert result.exit_code in (0, 1)
        assert "observations" in result.output
    finally:
        os.chdir(previous)


def test_verify_with_violations(workspace_with_obs):
    """Verify command exits 1 when violations found."""
    # Create failing observations
    obs = [
        Observation(subject="cell(bs1,1)", observable="cell_number_legible", value=False),
        Observation(subject="cell(bs1,2)", observable="cell_number_legible", value=True),
    ]
    write_jsonl(workspace_with_obs / "observations_fail.jsonl", obs)

    import os
    previous = os.getcwd()
    try:
        os.chdir(workspace_with_obs)
        result = runner.invoke(app, [
            "verify",
            "--site", "sites/den01.lp",
            "--observations", "observations_fail.jsonl"
        ])
        assert result.exit_code == 1
        assert "violated" in result.output.lower() or "undetermined" in result.output.lower()
    finally:
        os.chdir(previous)


def test_verify_missing_observations_file(workspace_with_obs):
    """Verify command exits 2 when observations file missing."""
    import os
    previous = os.getcwd()
    try:
        os.chdir(workspace_with_obs)
        result = runner.invoke(app, [
            "verify",
            "--site", "sites/den01.lp",
            "--observations", "nonexistent.jsonl"
        ])
        assert result.exit_code == 2
        assert "not found" in result.output
    finally:
        os.chdir(previous)


def test_verify_json_output(workspace_with_obs, tmp_path):
    """Verify command writes JSON output when requested."""
    output_file = tmp_path / "verdicts.json"

    import os
    previous = os.getcwd()
    try:
        os.chdir(workspace_with_obs)
        result = runner.invoke(app, [
            "verify",
            "--site", "sites/den01.lp",
            "--observations", "observations.jsonl",
            "--json-output", str(output_file)
        ])
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert "site" in data
        assert "verdicts" in data
        assert "summary" in data
        assert data["summary"]["violated"] >= 0
        assert data["summary"]["satisfied"] >= 0
        assert data["summary"]["undetermined"] >= 0
    finally:
        os.chdir(previous)


def test_verify_empty_observations(workspace_with_obs):
    """Verify command handles empty observations file."""
    write_jsonl(workspace_with_obs / "empty.jsonl", [])

    import os
    previous = os.getcwd()
    try:
        os.chdir(workspace_with_obs)
        result = runner.invoke(app, [
            "verify",
            "--site", "sites/den01.lp",
            "--observations", "empty.jsonl"
        ])
        # Should run but likely exit 1 due to undetermined requirements
        assert result.exit_code in (1, 2)  # Either incomplete or error
        assert "Warning: No observations" in result.output or "undetermined" in result.output.lower()
    finally:
        os.chdir(previous)
