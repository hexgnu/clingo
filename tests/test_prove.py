"""The solver's claims, as regression tests.

`eiguide prove` reports these numbers for a human. These tests assert the *claims* hold,
so a change to the cost model or the action tiers cannot quietly turn the argument for
using a solver into an argument against it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eiguide import prove

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "sites" / "den01.lp"


@pytest.fixture(scope="module")
def programs(chapter_d_program):
    return [ROOT / "ontology" / "core.lp", ROOT / "ontology" / "domain.lp", chapter_d_program]


def test_closed_world_would_certify_an_uninspected_site(programs):
    """The central claim. If this ever fails, the whole ASP argument collapses."""
    result = prove.open_world(programs, prove.SiteSpec("t"))
    counts = dict(r for r in result.rows if r[0])
    assert counts["proven satisfied"] == 0
    assert counts["nobody looked (undetermined)"] > 30
    # Closed-world "compliant unless proven violated" certifies everything.
    assert counts["closed-world verdict: 'compliant'"] == counts["requirements in force"]
    assert result.verdict.startswith("SOLVER WINS")


def test_solver_beats_both_hand_written_strategies(programs):
    result = prove.optimization(programs, prove.SiteSpec("t"))
    by_name = {row[0]: row[2] for row in result.rows}
    solver = by_name["solver plan"]
    assert solver < by_name["per-subject visit"] < by_name["per-gap loop (one capture each)"]
    # A win under 25% would not justify the machinery.
    assert solver <= 0.75 * by_name["per-subject visit"]


def test_carve_outs_change_what_applies(programs):
    """Removing a single exemption fact must bring a requirement back into force."""
    result = prove.applicability(programs, SITE)
    deltas = {row[0]: row[2] for row in result.rows}
    assert deltas["l3 no longer internal to rack"] == "+1"
    assert deltas["l5 no longer a short visible run"] == "+1"
    assert deltas["fp2 not misc bay mounted"] == "-1"
    assert deltas["fp2 has other fuse identification"] == "-1"


class TestScaling:
    def test_plan_size_stays_flat_as_the_site_grows(self, programs):
        """Gaps grow linearly with the plant; the work list must not.

        This is the property that makes an inspection tractable, and it is the one an
        engineer would most reasonably doubt.
        """
        result = prove.scaling(programs, [1, 24, 240])
        gaps = [row[2] for row in result.rows]
        actions = [row[3] for row in result.rows]
        assert gaps[-1] > 10 * gaps[0], "test site is not actually scaling"
        assert max(actions) == min(actions), f"plan size grew with the site: {actions}"

    def test_strategy_switches_on_its_own(self, programs):
        """One cell is cheapest to survey; two or more are cheapest to sweep.

        Nobody codes that threshold -- it falls out of the cost model. If the strategy
        column ever stops changing, the optimizer has stopped making a decision and a
        static rule would do.
        """
        result = prove.scaling(programs, [1, 2, 24])
        strategies = [row[5] for row in result.rows]
        assert strategies[0] == "survey"
        assert strategies[1] == "sweep"
        assert len(set(strategies)) > 1

    def test_solving_stays_fast_enough_to_re_plan_interactively(self, programs):
        """`inspect` re-solves after every answer, so this is a UX constraint."""
        result = prove.scaling(programs, [240])
        millis = float(result.rows[0][6].removesuffix("ms"))
        assert millis < 3000, f"too slow to re-plan between questions: {millis}ms"


def test_identical_input_gives_an_identical_plan(programs):
    """A plan that changes between runs cannot support an audit finding."""
    result = prove.determinism(programs, SITE, runs=5)
    assert result.verdict.startswith("PASS"), result.headline
    hashes = {row[2] for row in result.rows}
    assert len(hashes) == 1
