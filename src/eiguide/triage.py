"""Driving a ticket from unsolved to solved.

The loop is the same one the inspection walk uses, with a different question at each step:

    solve  ->  what are the live explanations, and what is the cheapest thing that would
               tell them apart?
    act    ->  run those tests / verify those records
    repeat ->  fold the results back in and re-solve

It terminates when one explanation survives with every fact it rests on established, or
when nothing further can be learned from the tests available -- which is itself an answer,
because it says a truck is required rather than leaving the ticket to age.

Each round is a fresh solve over the accumulated results. Re-deriving everything is cheap
at this size, and it means a late result that overturns an early conclusion is handled with
no special case: the candidate set is always what the full evidence supports, not a
running total that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import clingo

from .ticket import Ticket, TriageResult, asp_id

CORE = ("ontology/trust.lp", "ontology/diagnose.lp")


@dataclass
class Round:
    """One turn of the loop, kept so the path can be replayed and audited."""

    number: int
    candidates: list[str]
    provisional: list[str]
    tests: list[str]
    verifications: list[str]
    cost: int
    solved: bool
    reasons: list[str] = field(default_factory=list)


def _programs(root: Path, knowledge: list[Path]) -> list[Path]:
    return [root / p for p in CORE] + list(knowledge)


def solve(
    ticket: Ticket,
    knowledge: list[Path],
    evidence: str = "",
    root: Path = Path("."),
) -> dict:
    """One solve over the ticket plus everything learned so far."""
    ctl = clingo.Control(["--opt-mode=optN", "--models=0"])
    for path in _programs(root, knowledge):
        ctl.load(str(path))
    ctl.add("base", [], ticket.to_asp())
    if evidence:
        ctl.add("base", [], evidence)
    ctl.ground([("base", [])])

    best: dict = {"cost": [0], "atoms": []}

    def on_model(m: clingo.Model) -> None:
        nonlocal best
        best = {"cost": list(m.cost), "atoms": [(s.name, s.arguments) for s in m.symbols(shown=True)]}

    ctl.solve(on_model=on_model)
    return best


def _collect(model: dict, name: str) -> list[str]:
    out = []
    for atom_name, args in model["atoms"]:
        if atom_name != name:
            continue
        rendered = [a.string if a.type == clingo.SymbolType.String else str(a) for a in args]
        out.append(rendered[0] if len(rendered) == 1 else tuple(rendered))
    return sorted(out)


def to_result(ticket: Ticket, model: dict) -> TriageResult:
    """Shape one solve into the answer that goes back to the originating system."""
    solved = any(name == "solved" for name, _ in model["atoms"])
    unmapped = [
        args[1].string if args[1].type == clingo.SymbolType.String else str(args[1])
        for name, args in model["atoms"]
        if name == "unmapped_code"
    ]
    return TriageResult(
        ticket_id=ticket.ticket_id,
        solved=solved,
        candidates=_collect(model, "candidate"),
        provisional=_collect(model, "provisional"),
        eliminated=_collect(model, "eliminated"),
        next_tests=_collect(model, "do_test"),
        verify_records=_collect(model, "verify"),
        unrecognized_codes=sorted(unmapped),
        indistinguishable=[tuple(p) for p in _collect(model, "indistinguishable")],
        open_reasons=_collect(model, "unsolved_reason"),
        recommended=_collect(model, "recommended"),
        truck_roll=any(name == "truck_roll" for name, _ in model["atoms"]),
        plan_cost=model["cost"][0] if model["cost"] else 0,
    )


def evidence_facts(results: dict[str, str], checks: dict[str, bool]) -> str:
    """Render what has been learned so far as ASP."""
    lines = [f"test_result({asp_id(t)}, {asp_id(v)})." for t, v in sorted(results.items())]
    lines += [
        f"field_check({asp_id(f)}, {'true' if v else 'false'})." for f, v in sorted(checks.items())
    ]
    return "\n".join(lines)


def resolve(
    ticket: Ticket,
    knowledge: list[Path],
    oracle,
    root: Path = Path("."),
    max_rounds: int = 8,
) -> tuple[TriageResult, list[Round]]:
    """Run the loop to completion.

    ``oracle`` supplies outcomes -- a technician, an automated telemetry poll, or a fixture
    in a test. It is called with the test or record the solver asked for, and returns the
    outcome. Keeping it injected is what lets the same loop run headless against live
    telemetry and interactively against a person.
    """
    results: dict[str, str] = {}
    checks: dict[str, bool] = {}
    path: list[Round] = []

    for n in range(1, max_rounds + 1):
        model = solve(ticket, knowledge, evidence_facts(results, checks), root)
        result = to_result(ticket, model)
        path.append(
            Round(
                number=n,
                candidates=result.candidates,
                provisional=result.provisional,
                tests=result.next_tests,
                verifications=result.verify_records,
                cost=result.plan_cost,
                solved=result.solved,
                reasons=result.open_reasons,
            )
        )
        if result.solved:
            return result, path

        asked = list(result.next_tests) + list(result.verify_records)
        if not asked:
            # Nothing left that would change the answer. Stopping here is the honest
            # outcome; looping would just re-derive the same impasse.
            return result, path

        progressed = False
        for test in result.next_tests:
            outcome = oracle(test, "test")
            if outcome is not None:
                results[test] = outcome
                progressed = True
        for record in result.verify_records:
            outcome = oracle(record, "record")
            if outcome is not None:
                checks[record] = bool(outcome)
                progressed = True
        if not progressed:
            return result, path

    return result, path
