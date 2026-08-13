"""Ticket resolution: a ticket arrives from someone else's system and gets solved.

Two things are being tested. That the loop actually converges -- unsolved to solved,
spending cheap telemetry before expensive dispatch. And that it refuses to converge when it
should not: on an unverified record, on a refuted one, or on a vendor alarm code nobody has
mapped.

The second set matters more. A diagnostic engine that always produces an answer is worse
than useless, because the confident wrong answer is the one that rolls a truck to the wrong
span.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eiguide import triage
from eiguide.ticket import SourceFact, Ticket

ROOT = Path(__file__).resolve().parent.parent
KB = [ROOT / "knowledge" / "vendor_codes.lp", ROOT / "knowledge" / "samsung_router.lp"]
TICKET = ROOT / "tickets" / "samsung_4471.json"

# Telemetry consistent with a dark fibre: power fine, no upstream alarms, counters clean.
DARK_FIBRE = {
    "query_power_telemetry": "ac_present",
    "check_upstream_alarms": "none",
    "read_error_counters": "clean",
    "ping_node": "no_reply",
    "diff_running_config": "matches_golden",
    "read_optical_power": "no_light",
    "otdr_trace": "break_at_distance",
}


def oracle_from(tests: dict, records: dict):
    def answer(item: str, kind: str):
        return tests.get(item) if kind == "test" else records.get(item)

    return answer


@pytest.fixture
def ticket() -> Ticket:
    return Ticket.load(TICKET)


def solve_once(ticket: Ticket, evidence: str = ""):
    return triage.to_result(ticket, triage.solve(ticket, KB, evidence, ROOT))


class TestConvergence:
    def test_ticket_resolves_to_a_single_cause(self, ticket):
        result, path = triage.resolve(
            ticket, KB, oracle_from(DARK_FIBRE, {"uplink_span_known": True, "golden_config_known": True}), ROOT
        )
        assert result.solved, result.open_reasons
        assert result.candidates == ["fiber_cut"]
        assert result.recommended == ["dispatch_splice_crew"]
        assert result.truck_roll is True
        assert len(path) >= 2, "converged without narrowing anything"

    def test_cheap_telemetry_is_spent_before_a_truck(self, ticket):
        """The economic argument for planning at all.

        The first round must not reach for the OTDR (8) or a site visit (40) while
        one-cost remote reads are still informative.
        """
        first = solve_once(ticket)
        assert "site_visit" not in first.next_tests
        assert "otdr_trace" not in first.next_tests
        assert first.plan_cost <= 6

    def test_expensive_tests_are_skipped_when_cheap_ones_discriminate(self, ticket):
        """The property that actually matters, and the one a bug hid.

        `separates/3` was once defined per-test rather than per-outcome, so
        read_optical_power -- which responds to both fiber_cut and optic_degraded -- was
        judged unable to tell them apart, even though `no_light` confirms one and rules out
        the other. The planner reached past a cost-1 optical read for a cost-8 OTDR, and an
        earlier version of this test mistook that escalation for correct behaviour.

        With discrimination computed at outcome level the whole diagnosis completes on
        one-cost remote reads, and neither the OTDR nor a truck is ever scheduled.
        """
        _, path = triage.resolve(
            ticket, KB, oracle_from(DARK_FIBRE, {"uplink_span_known": True, "golden_config_known": True}), ROOT
        )
        scheduled = {t for r in path for t in r.tests}
        assert "site_visit" not in scheduled
        assert "otdr_trace" not in scheduled, (
            "reached for an 8-cost trace while a 1-cost optical read discriminates"
        )
        assert max(r.cost for r in path) <= 6


class TestUnreliableRecords:
    """OneVizion is authoritative about intent and approximate about reality."""

    def test_a_stale_record_makes_its_hypothesis_provisional(self, ticket):
        """The uplink span row is 130 days old against a 90-day threshold."""
        result = solve_once(ticket)
        assert "fiber_cut" in result.provisional
        assert "uplink_span_known" in result.verify_records

    def test_a_low_confidence_record_is_also_suspect(self, ticket):
        result = solve_once(ticket)
        assert "config_drift" in result.provisional
        assert "golden_config_known" in result.verify_records

    def test_a_fresh_confident_record_is_not_questioned(self, ticket):
        """Verifying rows nobody doubts is busywork and erodes trust in the flags."""
        result = solve_once(ticket)
        assert "site_location_known" not in result.verify_records
        assert "upstream_node_known" not in result.verify_records

    def test_a_refuted_record_eliminates_its_hypothesis(self, ticket):
        """The case that prevents a truck roll to the wrong span.

        Telemetry says the fibre is dark. The record says which span feeds this router.
        If that record is wrong, "dispatch a splice crew to span 17" is an expensive
        mistake, and the reasoner must not make it.
        """
        evidence = triage.evidence_facts(
            {k: v for k, v in DARK_FIBRE.items() if k != "otdr_trace"},
            {"uplink_span_known": False, "golden_config_known": True},
        )
        result = solve_once(ticket, evidence)
        assert "fiber_cut" not in result.candidates
        assert not result.truck_roll
        assert not result.solved

    def test_contradicting_sources_make_a_fact_suspect(self, ticket):
        """Two systems disagreeing is stronger evidence than either claim alone."""
        ticket.facts.append(
            SourceFact(
                source="samsung_nms",
                fact="site_location_known",
                confidence=95,
                as_of_day=239,
                negated=True,
            )
        )
        result = solve_once(ticket)
        assert "site_location_known" in result.verify_records


class TestUnknownVendorCodes:
    def test_an_unmapped_code_blocks_a_confident_answer(self, ticket):
        """The boundary failure that matters when tickets arrive from another system.

        Drop an unrecognized alarm and the ticket returns a tidy diagnosis reached without
        it. Here Samsung ships a rectifier alarm nobody has mapped; the reasoner narrows to
        fiber_cut but refuses to call it solved.
        """
        raw = json.loads(TICKET.read_text())
        raw["alarms"].append({"code": "PWR-RECT-DEGRADE-B7", "raised_day": 240})
        noisy = Ticket.model_validate(raw)

        result, _ = triage.resolve(
            noisy, KB, oracle_from(DARK_FIBRE, {"uplink_span_known": True, "golden_config_known": True}), ROOT
        )
        assert result.unrecognized_codes == ["PWR-RECT-DEGRADE-B7"]
        assert result.solved is False
        assert any("does not recognize" in r for r in result.open_reasons)
        assert not result.truck_roll

    def test_a_mapped_code_from_another_nms_works(self, ticket):
        """The vocabulary is per-source data, so a second NMS is a mapping, not a change."""
        raw = json.loads(TICKET.read_text())
        raw["source"] = "netcool"
        raw["alarms"] = [{"code": "SignalLoss"}, {"code": "LinkDown"}]
        other = Ticket.model_validate(raw)
        result = solve_once(other)
        assert result.unrecognized_codes == []
        assert "fiber_cut" in result.candidates


class TestIngestion:
    def test_vendor_wording_survives_to_the_reasoner(self, ticket):
        """Codes must not be normalized in Python, or the mapping stops being data."""
        asp = ticket.to_asp()
        assert 'raw_alarm(samsung_nms, "LOS-A1")' in asp
        assert "claim(onevizion, uplink_span_known, 85, 110)" in asp

    def test_provenance_and_age_are_preserved(self, ticket):
        asp = ticket.to_asp()
        assert "today(240)" in asp
        assert "stale_after(90)" in asp
        assert "min_confidence(80)" in asp

    def test_hostile_identifiers_do_not_break_the_program(self):
        """External ids are not required to be ASP-safe."""
        t = Ticket(
            ticket_id="SAMS/4471-A",
            source="Samsung NMS (west)",
            received_day=1,
            asset_id="RTR.DEN.042",
            alarms=[],
            facts=[],
        )
        asp = t.to_asp()
        assert "ticket(sams_4471_a)" in asp
        assert "asset(rtr_den_042)" in asp
        # And it must still ground.
        result = solve_once(t)
        assert result.candidates == []


class TestContradictoryEvidence:
    """Readings that disagree must be named, never silently reconciled.

    This is the failure the design document called the important one, and it was worse in
    practice than on paper: the ticket reported SOLVED with a resolution it had no positive
    evidence for.
    """

    CONFLICT = {
        "read_optical_power": "no_light",   # confirms fiber_cut
        "otdr_trace": "continuous",         # rules out fiber_cut
        "query_power_telemetry": "ac_present",
        "check_upstream_alarms": "none",
        "read_error_counters": "clean",
        "ping_node": "replies",
    }

    def _conflicted(self, ticket):
        evidence = triage.evidence_facts(
            self.CONFLICT, {"uplink_span_known": True, "golden_config_known": True}
        )
        return solve_once(ticket, evidence)

    def test_conflicting_readings_block_a_verdict(self, ticket):
        """Before the fix this returned solved=True, push_golden_config.

        A dark fibre and an intact trace cannot both be right. `eliminated` quietly won,
        fiber_cut vanished from the candidate set, and the only survivor was reported as
        the answer despite nothing confirming it.
        """
        result = self._conflicted(ticket)
        assert result.solved is False
        assert result.recommended == []
        assert not result.truck_roll

    def test_the_conflict_is_named_not_guessed_at(self, ticket):
        result = self._conflicted(ticket)
        assert any("for and against" in r for r in result.open_reasons), result.open_reasons


class TestKnowledgeBaseIntegrity:
    """Guardrails on the knowledge base itself.

    An author who knows routers is not required to also know ASP, so anything that can be
    derived from the outcome table must be, and anything that cannot be checked by hand
    must be checked by the solver.
    """

    def test_no_knowledge_file_authors_observes(self):
        """`observes/2` is derived. Authoring it lets it drift from the outcomes.

        Two pairs had already drifted -- claiming discriminating power that no result
        delivered, so the planner scheduled tests that could not move either candidate.
        """
        for path in KB:
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("%"):
                    continue
                assert not stripped.startswith("observes("), f"{path.name}: {stripped}"

    def test_every_test_has_a_recordable_outcome(self, ticket):
        """A test that can be planned but whose result cannot be entered sends a
        technician to do work that changes nothing."""
        model = triage.solve(ticket, KB, "", ROOT)
        holes = [str(a[0]) for n, a in model["atoms"] if n == "test_without_outcomes"]
        assert holes == [], holes

    def test_the_plan_is_reproducible(self, ticket):
        """Four plans tie at the optimum. A technician must get the same one twice."""
        plans = {tuple(solve_once(ticket).next_tests) for _ in range(5)}
        assert len(plans) == 1, plans
