"""The command surface, driven end to end.

`cli.py` was the largest untested module in the project, and it holds the logic a user
actually touches: the answer loop, the group-failure drill-down, and the arithmetic that
turns answers into a verdict. Every bug found here would have reached a person.

Commands are invoked through Typer's runner rather than by calling the functions, so
argument parsing, defaults and exit codes are covered too.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eiguide.cli import app

ROOT = Path(__file__).resolve().parent.parent
runner = CliRunner()


@pytest.fixture(scope="module")
def workspace(tmp_path_factory, chapter_d_program):
    """A complete project tree in a temp dir, so tests never touch the real one."""
    ws = tmp_path_factory.mktemp("ws")
    (ws / "data").mkdir()
    (ws / "rules").mkdir()
    shutil.copytree(ROOT / "ontology", ws / "ontology")
    shutil.copytree(ROOT / "sites", ws / "sites")
    shutil.copy(ROOT / "data" / "golden" / "chapter_d6.jsonl", ws / "data" / "rules.jsonl")
    shutil.copy(chapter_d_program, ws / "rules" / "chapter_d.lp")
    return ws


@pytest.fixture(scope="module")
def with_clauses(workspace, clauses):
    from eiguide.store import write_jsonl

    write_jsonl(workspace / "data" / "clauses.jsonl", clauses)
    return workspace


def invoke(cwd: Path, args: list[str], stdin: str = ""):
    """Run a command with cwd set, since the CLI resolves paths relative to it."""
    import os

    previous = os.getcwd()
    os.chdir(cwd)
    try:
        import eiguide.cli as cli_mod

        cli_mod.ROOT = cwd
        cli_mod.DATA = cwd / "data"
        cli_mod.RULES_DIR = cwd / "rules"
        cli_mod.ONTOLOGY = cwd / "ontology"
        return runner.invoke(app, args, input=stdin)
    finally:
        os.chdir(previous)


class TestPlan:
    def test_plan_prints_actions_and_writes_nothing(self, with_clauses):
        before = sorted(p.name for p in (with_clauses / "data").iterdir())
        result = invoke(with_clauses, ["plan", "--site", "sites/den01.lp"])
        assert result.exit_code == 0, result.output
        assert "capture actions" in result.output
        assert "sweep(bs1" in result.output
        after = sorted(p.name for p in (with_clauses / "data").iterdir())
        assert before == after, "plan is documented as read-only but wrote a file"

    def test_plan_reports_what_capture_cannot_settle(self, with_clauses):
        result = invoke(with_clauses, ["plan", "--site", "sites/den01.lp"])
        assert "cannot be settled by capture" in result.output
        assert "D.6.4" in result.output

    def test_out_flag_writes_the_manifest(self, with_clauses, tmp_path):
        target = tmp_path / "m.json"
        result = invoke(with_clauses, ["plan", "--site", "sites/den01.lp", "--out", str(target)])
        assert result.exit_code == 0, result.output
        assert target.exists()

    def test_missing_chapter_fails_with_guidance(self, with_clauses):
        result = invoke(with_clauses, ["plan", "--site", "sites/den01.lp", "--chapter", "Z"])
        assert result.exit_code != 0
        assert "compile" in result.output


class TestInspect:
    """The answer loop. Input is a script of keystrokes, exactly as a user would type."""

    def test_passing_everything_reaches_compliance(self, with_clauses):
        # 8 actions; answering "p" to every prompt and accepting every default.
        result = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="p\n" * 60)
        assert result.exit_code == 0, result.output
        assert "0 violated" in result.output
        # The two documentary obligations can never be closed by capture.
        assert "2 undetermined" in result.output

    def test_a_group_failure_is_localized_to_the_named_members(self, with_clauses):
        """Two bad cells out of 24 must produce two violations, not 24.

        This is the single most consequential piece of arithmetic in the CLI: getting it
        wrong either condemns a whole battery string or buries a real defect.
        """
        script = (
            "p\n"  # 1. video pass
            "p\np\np\np\n"  # 2. string markings
            "f\n7,9\nlabel worn\n"  # 3. sweep: cell numbers fail on 7 and 9
            "p\n"  # 3. polarity fine
            + "p\n" * 40  # remaining actions
        )
        result = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin=script)
        assert result.exit_code == 0, result.output
        assert "2 violated" in result.output
        assert "cell(bs1,7)" in result.output
        assert "cell(bs1,9)" in result.output

    def test_skipping_leaves_the_requirement_open(self, with_clauses):
        """A skipped check must never read as a pass."""
        result = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="s\n" * 60)
        assert result.exit_code == 0, result.output
        assert "0 satisfied" in result.output
        assert "0 violated" in result.output

    def test_quitting_early_stops_and_says_so(self, with_clauses):
        result = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="q\n")
        assert result.exit_code == 0, result.output
        assert "Stopped" in result.output
        assert "undetermined" in result.output

    def test_an_unrecognized_answer_is_re_asked_not_guessed(self, with_clauses):
        """Treating a typo as pass fabricates compliance; as fail, a violation.

        Both are worse than asking again, so the prompt must loop.
        """
        result = invoke(
            with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="xyzzy\np\n" + "p\n" * 60
        )
        assert "answer p, f, s or q" in result.output
        assert result.exit_code == 0, result.output

    def test_nothing_is_written_to_disk(self, with_clauses):
        before = sorted(p.name for p in (with_clauses / "data").iterdir())
        invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="p\n" * 60)
        after = sorted(p.name for p in (with_clauses / "data").iterdir())
        assert before == after, "inspect is single-shot but left state behind"

    def test_a_clause_is_quoted_once_not_per_rule(self, with_clauses):
        """D.6.6 backs three rules; quoting it in full three times drowns the instruction."""
        result = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="q\n" * 3)
        quoted = result.output.count("Designate all batteries with black ink to indicate")
        assert quoted <= 1, f"clause quoted {quoted} times"

    def test_detail_lists_every_subject(self, with_clauses):
        rolled = invoke(with_clauses, ["inspect", "--site", "sites/den01.lp"], stdin="p\n" * 60)
        detailed = invoke(
            with_clauses, ["inspect", "--site", "sites/den01.lp", "--detail"], stdin="p\n" * 60
        )
        assert detailed.output.count("cell(bs1,") > rolled.output.count("cell(bs1,")


class TestCompile:
    def test_compile_writes_a_program_and_verifies_exemptions(self, with_clauses):
        result = invoke(with_clauses, ["compile", "--chapter", "D"])
        assert result.exit_code == 0, result.output
        assert "exemptions verified" in result.output
        assert "exemption not in force" not in result.output
        assert (with_clauses / "rules" / "chapter_d.lp").exists()

    def test_unknown_chapter_is_an_error(self, with_clauses):
        result = invoke(with_clauses, ["compile", "--chapter", "Z"])
        assert result.exit_code != 0


class TestSiteWarnings:
    def test_a_broken_site_warns_before_planning(self, with_clauses, tmp_path):
        bad = with_clauses / "sites" / "bad.lp"
        bad.write_text("battery_string(bs1).\ncell(bs1, 1..3).\nfuse_pannel(fp1).\n")
        try:
            result = invoke(with_clauses, ["plan", "--site", "sites/bad.lp"])
            # Now fails fast with "site error" instead of warning
            assert result.exit_code == 1
            assert "site error" in result.output
            assert "fuse_pannel" in result.output
        finally:
            bad.unlink()
