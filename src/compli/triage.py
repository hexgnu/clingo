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

from .compile import asp_constant
from .ticket import Ticket, TriageResult

CORE = ("ontology/trust.lp", "ontology/x733.lp", "ontology/diagnose.lp")


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


def _run(
    ticket: Ticket,
    knowledge: list[Path],
    root: Path,
    extra: str,
    opts: tuple[str, ...] = ("--opt-mode=optN", "--models=0"),
) -> list[dict]:
    """Ground and solve once, returning every cost-optimal answer set.

    Raises:
        RuntimeError: If knowledge base files contain errors or solver fails.
    """
    try:
        ctl = clingo.Control(list(opts))
        for path in _programs(root, knowledge):
            ctl.load(str(path))
        ctl.add("base", [], ticket.to_asp())
        if extra:
            ctl.add("base", [], extra)
        ctl.ground([("base", [])])
    except RuntimeError as e:
        raise RuntimeError(
            f"Failed to load/ground triage knowledge base:\n"
            f"  Ticket: {ticket.ticket_id}\n"
            f"  Knowledge: {[k.stem for k in knowledge]}\n"
            f"  Error: {e}"
        ) from e

    found: list[dict] = []

    def on_model(m: clingo.Model) -> None:
        found.append(
            {"cost": list(m.cost), "atoms": [(s.name, s.arguments) for s in m.symbols(shown=True)]}
        )

    try:
        ctl.solve(on_model=on_model)
    except RuntimeError as e:
        raise RuntimeError(f"Triage solver execution failed: {e}") from e

    if not found:
        return []
    best = min(m["cost"] for m in found)
    return [m for m in found if m["cost"] == best]


def _atoms(model: dict, name: str) -> set[str]:
    return {str(a[0]) for n, a in model["atoms"] if n == name and a}


def solve(
    ticket: Ticket,
    knowledge: list[Path],
    evidence: str = "",
    root: Path = Path("."),
) -> dict:
    """Two passes over the ticket plus everything learned so far.

    **Pass 1 enumerates the incident world.** Each answer set is one way things could be:
    a minimal set of faults accounting for the reported alarms and surviving every reading
    taken so far. The union of those worlds is what is *possible*; the intersection is what
    is *certain*. Neither is visible from inside a single world, which is why this cannot be
    one solve -- a world knows what it contains, not what the alternatives contain.

    **Pass 2 plans against them.** With the possible and certain sets supplied as facts, the
    solver picks the cheapest evidence that would tell the surviving worlds apart, and
    decides whether they already agree well enough to act.

    A cost-optimal plan is rarely unique -- this ticket has four at cost 6 -- and returning
    whichever the solver reported last hands a technician different work on two identical
    runs. The optima are collected and one is chosen by a fixed rule. Only the plan varies;
    the union and intersection above are computed over *all* the optima, so the verdict does
    not depend on which one is displayed.
    """
    # What is POSSIBLE is asked over every world, with optimization off. Occam decides what
    # to act on; it must not decide what could be true. config_drift explains one of two
    # alarms and so needs a partner -- less parsimonious, but not impossible, and a record it
    # rests on is still worth checking.
    reach = _run(
        ticket, knowledge, root, evidence,
        opts=("--opt-mode=ignore", "--models=0", "--enum-mode=brave"),
    )
    possible = _atoms(reach[-1], "fault") if reach else set()

    # What is CERTAIN, and what the incident would have you do, are asked over the minimal
    # worlds only.
    worlds = _run(ticket, knowledge, root, evidence)
    if not worlds:
        return {"cost": [0], "atoms": [], "worlds": 0}

    # Cache atom extraction — iterate worlds once per predicate instead of 2n times
    faults_by_world = [_atoms(w, "fault") for w in worlds]
    resolves_by_world = [_atoms(w, "resolves_to") for w in worlds]

    live = set().union(*faults_by_world)
    certain = set.intersection(*faults_by_world)
    may_do = set().union(*resolves_by_world)
    will_do = set.intersection(*resolves_by_world)

    supplied = "\n".join(
        [f"candidate({h})." for h in sorted(possible)]
        + [f"certain({h})." for h in sorted(certain)]
        + [f"possible_action({r})." for r in sorted(may_do)]
        + [f"certain_action({r})." for r in sorted(will_do)]
    )

    plans = _run(ticket, knowledge, root, f"{evidence}\n{supplied}")
    if not plans:
        return {"cost": [0], "atoms": [], "worlds": len(worlds)}

    def key(model: dict) -> tuple:
        tests = sorted(str(a[0]) for n, a in model["atoms"] if n == "do_test")
        return (len(tests), tests)

    chosen = min(plans, key=key)
    chosen["worlds"] = len(worlds)
    # Two different sets, and the difference matters. `live` is what the minimal worlds still
    # hold open -- the explanations actually in play, and what a person is shown. `possible`
    # is wider: anything not ruled out, however unparsimonious. Verification planning uses the
    # wider one deliberately, because a record worth checking is worth checking even if the
    # explanation resting on it is the less economical reading.
    chosen["atoms"] = chosen["atoms"] + [
        ("live", [clingo.Function(h)]) for h in sorted(live)
    ]
    return chosen


def outcomes(model: dict) -> dict[str, list[str]]:
    """Legal results per test, read out of the knowledge base.

    Offering these rather than a free-text box keeps a technician from entering a value no
    rule responds to, which would look like an answer and change nothing.
    """
    found: dict[str, list[str]] = {}
    for name, args in model["atoms"]:
        if name == "outcome":
            found.setdefault(str(args[0]), []).append(str(args[1]))
    return {k: sorted(v) for k, v in found.items()}


def fact_status(model: dict) -> dict[str, str]:
    """Trust state per fact, for showing what the record is worth before acting on it."""
    status: dict[str, str] = {}
    for name, args in model["atoms"]:
        if name in ("established", "refuted", "unverified") and args:
            status[str(args[0])] = name
    return status


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
        candidates=_collect(model, "live"),
        provisional=_collect(model, "provisional"),
        eliminated=_collect(model, "eliminated"),
        next_tests=_collect(model, "do_test"),
        verify_records=_collect(model, "verify"),
        unrecognized_codes=sorted(unmapped),
        indistinguishable=[tuple(p) for p in _collect(model, "indistinguishable")],
        open_reasons=_collect(model, "unsolved_reason"),
        recommended=_collect(model, "advised"),
        truck_roll=any(name == "truck_roll" for name, _ in model["atoms"]),
        plan_cost=model["cost"][0] if model["cost"] else 0,
    )


def evidence_facts(results: dict[str, str], checks: dict[str, bool]) -> str:
    """Render what has been learned so far as ASP."""
    lines = [f"test_result({asp_constant(t)}, {asp_constant(v)})." for t, v in sorted(results.items())]
    lines += [
        f"field_check({asp_constant(f)}, {'true' if v else 'false'})." for f, v in sorted(checks.items())
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
