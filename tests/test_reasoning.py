"""Solver behaviour: the three-valued verdict, the carve-outs, and the optimization.

This is where the project's actual claims live, so each test pins one of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eiguide import compile as compile_mod
from eiguide import reason
from eiguide.models import Observation

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = [ROOT / "ontology" / "core.lp", ROOT / "ontology" / "domain.lp"]
SITE = ROOT / "sites" / "den01.lp"


@pytest.fixture(scope="module")
def chapter_d(chapter_d_program):
    return chapter_d_program


def solve(chapter_d, observations: list[Observation] | None = None):
    return reason.solve(
        ONTOLOGY + [chapter_d, SITE],
        reason.observations_to_facts(observations or []),
    )


def status_for(model, rule: str, subject: str) -> str:
    if (rule, subject) in model.violated:
        return "violated"
    if (rule, subject) in model.satisfied:
        return "satisfied"
    if (rule, subject) in model.undetermined:
        return "undetermined"
    return "not_applicable"


class TestPartialObservation:
    def test_unobserved_site_is_undetermined_never_compliant(self, chapter_d):
        """The core claim.

        With no evidence at all, nothing may be reported satisfied. A closed-world engine
        would call this site clean simply because no violation had been proven.
        """
        model = solve(chapter_d)
        assert model.satisfied == []
        assert model.violated == []
        assert len(model.undetermined) > 0

    def test_every_undetermined_requirement_is_accounted_for(self, chapter_d):
        """Nothing may be undetermined for an unexplained reason.

        Each open requirement is either something capture can close, or one of the
        documentary obligations that carries no observables by design. A third category
        would mean a rule had gone missing from the plan silently.
        """
        model = solve(chapter_d)
        has_a_gap = {(r, s) for r, s, _ in model.gap}
        documentary = {"D.6.4", "D.6.5"}
        for rule, subject in model.undetermined:
            assert (rule, subject) in has_a_gap or rule in documentary, (
                f"{rule} on {subject} is open but nothing explains why"
            )

    def test_partial_evidence_does_not_satisfy(self, chapter_d):
        """A requirement with two observables is not met by satisfying one."""
        model = solve(chapter_d, [Observation(subject="fp1", observable="row_designation_present", value=True)])
        assert status_for(model, "D.6.1", "fp1") == "undetermined"


class TestCarveOuts:
    def test_exemption_removes_the_requirement(self, chapter_d):
        """D.6.8 exempts leads internal to the relay rack from 145C tagging.

        l3 is internal, so D.6.7 must not apply to it. Dropping this carve-out would send
        an inspector to photograph tags the standard says are not required.
        """
        model = solve(chapter_d)
        assert status_for(model, "D.6.7", "l3") == "not_applicable"
        assert status_for(model, "D.6.7", "l1") == "undetermined"

    def test_short_visible_ground_runs_are_exempt(self, chapter_d):
        """D.6.9's second sentence exempts short runs visible from the floor."""
        model = solve(chapter_d)
        assert status_for(model, "D.6.9", "l5") == "not_applicable"
        assert status_for(model, "D.6.9", "l4") == "undetermined"

    def test_conditional_applicability(self, chapter_d):
        """D.6.3 applies only to miscellaneous bay-mounted panels."""
        model = solve(chapter_d)
        assert status_for(model, "D.6.3", "fp2") == "undetermined"
        assert status_for(model, "D.6.3", "fp1") == "not_applicable"

    def test_bus_bar_only_obligation(self, chapter_d):
        """D.6.7b applies only to leads landing on the battery return bus bar."""
        model = solve(chapter_d)
        assert status_for(model, "D.6.7b", "l1") == "undetermined"
        assert status_for(model, "D.6.7b", "l2") == "not_applicable"


class TestOptimization:
    def test_one_sweep_beats_twenty_four_photos(self, chapter_d):
        """The reason this is a solver and not a checklist.

        24 cells x 2 observables is 48 individual captures. One pass down the string
        settles all of them, and the optimizer has to find that without being told.
        """
        model = solve(chapter_d)
        chosen = [str(a) for a in model.do]
        assert any(a.startswith("sweep(bs1") for a in chosen)
        cell_captures = [a for a in chosen if a.startswith("capture(cell(")]
        assert cell_captures == []
        assert len(chosen) < 12, f"plan should be short, got {len(chosen)}: {chosen}"

    def test_a_subject_is_photographed_once_not_once_per_marking(self, chapter_d):
        """fp2 carries four separate markings; it should still be one visit."""
        model = solve(chapter_d)
        fp2_actions = [str(a) for a in model.do if "fp2" in str(a)]
        assert len(fp2_actions) == 1

    def test_plan_closes_every_reachable_gap(self, chapter_d):
        """No silent truncation: anything closable must be in the plan."""
        model = solve(chapter_d)
        closed = {(r, s, o) for _, r, s, o in model.closes}
        unreachable = {(r, s, o) for r, s, o in model.unreachable}
        for gap in model.gap:
            assert gap in closed or gap in unreachable, f"gap dropped from plan: {gap}"

    def test_no_useless_actions(self, chapter_d):
        model = solve(chapter_d)
        acting = {str(a) for a in model.do}
        closing = {aid for aid, _, _, _ in model.closes}
        assert acting == closing


class TestVerdicts:
    def _pass_everything(self, model) -> list[Observation]:
        return [
            Observation(subject=s, observable=o, value=True)
            for _, _, s, o in model.closes
        ]

    def test_full_evidence_yields_compliance(self, chapter_d):
        first = solve(chapter_d)
        model = solve(chapter_d, self._pass_everything(first))
        assert model.violated == []
        assert len(model.satisfied) > 30
        # Only the documentary obligations remain open.
        remaining = {r for r, _ in model.undetermined}
        assert remaining <= {"D.6.4", "D.6.5"}

    def test_one_bad_cell_violates_only_that_cell(self, chapter_d):
        """A defect must be localized, not smeared across the whole group."""
        first = solve(chapter_d)
        observations = self._pass_everything(first)
        for obs in observations:
            if obs.subject == "cell(bs1,7)" and obs.observable == "cell_number_legible":
                obs.value = False
        model = solve(chapter_d, observations)
        assert ("D.6.6a", "cell(bs1,7)") in model.violated
        assert ("D.6.6a", "cell(bs1,9)") in model.satisfied
        assert len(model.violated) == 1

    def test_documentary_obligations_are_flagged_not_hidden(self, chapter_d):
        """D.6.4 and D.6.5 concern the fuse record book and no photo can settle them.

        They must stay visible as unsettled rather than disappearing from the output.
        """
        model = solve(chapter_d)
        open_rules = {r for r, _ in model.undetermined}
        assert {"D.6.4", "D.6.5"} <= open_rules
        planned = {r for _, r, _, _ in model.closes}
        assert "D.6.4" not in planned


class TestManifest:
    def test_manifest_carries_citations_and_criteria(self, chapter_d, clause_index, golden_rules):
        model = solve(chapter_d)
        clauses = {r.id: clause_index[r.clause_id] for r in golden_rules if r.clause_id in clause_index}
        manifest = reason.build_manifest(
            model, "den01", clauses, {"doc": "EIGuide"}, reason.acceptance_index(golden_rules)
        )
        assert manifest.actions
        for action in manifest.actions:
            assert action.instruction
            assert action.discharges
            # Every request must be traceable to the page it came from.
            assert action.citations, f"{action.id} has no citation"
            assert all(c.page_label for c in action.citations)
        # And the unsettleable ones must be reported, not dropped.
        assert {i.rule for i in manifest.undetermined_after_plan} >= {"D.6.4", "D.6.5"}


class TestCompiler:
    def test_exemptions_emit_no_obligation(self, golden_rules, clause_index):
        exemption = next(r for r in golden_rules if r.kind == "exemption")
        source = compile_mod.compile_rule(exemption, clause_index.get(exemption.clause_id))
        assert "applies(" not in source
        assert "D.6.7" in source  # the rule it narrows is still recorded

    def test_every_exemption_is_realized_as_a_guard(self, golden_rules):
        """An exemption that is not wired into the rule it narrows is silently inert.

        This is the failure mode the `exemption` rule kind exists to prevent, and until
        now nothing verified the link -- D.6.7 could lose its `not internal_to_rack(L)`
        guard and every test would still pass.
        """
        assert compile_mod.check_exemptions(golden_rules) == []

    def test_a_dropped_guard_is_detected(self, golden_rules):
        """Break the link on purpose; the checker must notice."""
        broken = [r.model_copy(deep=True) for r in golden_rules]
        target = next(r for r in broken if r.id == "D.6.7")
        target.applicability = [
            lit for lit in target.applicability if "internal_to_rack" not in lit
        ]
        problems = compile_mod.check_exemptions(broken)
        assert any("D.6.7" in p for p in problems), problems

    def test_observable_names_become_legal_constants(self):
        assert compile_mod.asp_constant("Cell Number Legible!") == "cell_number_legible"
        assert compile_mod.asp_constant("145c tag").startswith("o_")
