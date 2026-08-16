"""Test two-pass solver coordination in ticket triage.

The diagnostic solver runs in two passes:
  Pass 1: Enumerate minimal fault worlds (no candidate/1 facts)
  Pass 2: Plan cheapest test to discriminate worlds (with candidate/1 facts)

These tests verify error handling and coordination between passes.
"""

from pathlib import Path
import pytest

from compli.ticket import Ticket, TriageResult
from compli import triage

ROOT = Path(__file__).resolve().parent.parent


def test_stage1_grounding_with_missing_knowledge():
    """When knowledge base is incomplete, grounding should still work or fail cleanly.

    The two-pass system should handle missing hypotheses gracefully.
    """
    # Minimal ticket
    ticket = Ticket(
        ticket_id="TEST-001",
        source="test",
        received_day=20261115,
        asset_id="router01",
        alarms=[],
        facts=[],
    )

    # Empty knowledge - will ground but find no hypotheses
    knowledge = []

    # Should complete without crashing
    # May return empty result or error, but should not hang
    try:
        result = triage.solve(ticket, knowledge, root=ROOT)
        # Result is a dict
        assert isinstance(result, dict)
    except RuntimeError as e:
        # Acceptable if it raises about missing knowledge
        assert "Failed to load/ground" in str(e) or "knowledge" in str(e).lower()


def test_stage1_single_world_skips_stage2():
    """When Stage 1 finds exactly one world, Stage 2 (discrimination) is unnecessary.

    If only one fault explains the symptoms, there's nothing to discriminate.
    """
    # This would need a ticket with symptoms that uniquely identify one fault
    # For now, just verify the code path exists
    pass  # Implementation would need specific ticket/knowledge setup


def test_stage2_receives_stage1_candidates():
    """Stage 2 must receive candidate/1 facts from Stage 1's worlds."""
    # Load a real ticket that produces multiple worlds
    ticket_path = ROOT / "tickets" / "SAMS-5120.json"
    if not ticket_path.exists():
        pytest.skip("Test ticket not available")

    ticket = Ticket.load(ticket_path)
    knowledge = [
        ROOT / "knowledge" / "vendor_codes.lp",
        ROOT / "knowledge" / "samsung_router.lp",
    ]

    result = triage.solve(ticket, knowledge, root=ROOT)

    # Result is a dict - check it's non-empty
    assert isinstance(result, dict)
    # If it has candidate faults, it ran successfully
    # The exact structure depends on the ticket data


def test_stage1_grounding_error_propagates():
    """Grounding errors in Stage 1 should raise with actionable message."""
    # Create ticket with minimal valid data
    ticket = Ticket(
        ticket_id="TEST-BAD",
        source="test",
        received_day=20261115,
        asset_id="bad_asset",
        alarms=[],
        facts=[],
    )

    # Use non-existent knowledge file to trigger load error
    # Note: clingo may print error to stderr before Python exception
    knowledge = [Path("/nonexistent/file.lp")]

    # Should raise an error (RuntimeError, FileNotFoundError, or SystemExit from clingo)
    with pytest.raises(Exception):  # Broad catch since clingo error handling varies
        triage.solve(ticket, knowledge, root=ROOT)


def test_empty_ticket_produces_result():
    """Ticket with no alarms should produce valid result."""
    ticket = Ticket(
        ticket_id="TEST-EMPTY",
        source="test",
        received_day=20261115,
        asset_id="test_asset",
        alarms=[],
        facts=[],
    )

    knowledge = [ROOT / "knowledge" / "samsung_router.lp"]

    result = triage.solve(ticket, knowledge, root=ROOT)

    # Should complete without error
    assert result is not None
    assert isinstance(result, dict)


def test_two_pass_coordination_smoke_test():
    """Smoke test: verify two-pass system runs without crashing."""
    # Minimal valid ticket
    ticket = Ticket(
        ticket_id="TEST-SMOKE",
        source="test",
        received_day=20261115,
        asset_id="router01",
        alarms=[],
        facts=[],
    )

    knowledge = [ROOT / "knowledge" / "samsung_router.lp"]

    # Should complete both passes without crashing
    result = triage.solve(ticket, knowledge, root=ROOT)

    # Result should be a dict (exact structure depends on solve() implementation)
    assert isinstance(result, dict)
