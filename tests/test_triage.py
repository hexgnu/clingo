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

    def test_the_plan_escalates_only_as_cheap_options_run_out(self, ticket):
        _, path = triage.resolve(
            ticket, KB, oracle_from(DARK_FIBRE, {"uplink_span_known": True, "golden_config_known": True}), ROOT
        )
        assert path[0].cost < max(r.cost for r in path), "cost never escalated"


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
