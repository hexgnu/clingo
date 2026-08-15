"""Stage 4: run the solver, and turn its answer set into a plan or a verdict.

Two entry points, both over the same logic program:

``plan``    what should be captured next, and in what order
``verify``  given what has been captured, what is the compliance position

They are the same reasoning run read two different ways, which is what keeps the plan and
the verdict from ever disagreeing about which requirements are in force.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import clingo

from .models import (
    Action,
    Evidence,
    EvidenceSource,
    Citation,
    Clause,
    Discharge,
    Manifest,
    Observation,
    OpenItem,
    Rule,
    Verdict,
)

# Effort ordering used to sequence a plan. Sweeps come first because they knock out the
# most, and instrumented checks last because they need kit set up.
KIND_ORDER = {"video": 0, "photo": 1, "document": 2, "measurement": 3}


class Model:
    """The atoms of interest from one answer set."""

    def __init__(self) -> None:
        self.do: list[clingo.Symbol] = []
        self.closes: list[tuple[str, str, str, str]] = []
        self.action_cost: dict[str, int] = {}
        self.gap: list[tuple[str, str, str]] = []
        self.unreachable: list[tuple[str, str, str]] = []
        self.violated: list[tuple[str, str]] = []
        self.satisfied: list[tuple[str, str]] = []
        self.undetermined: list[tuple[str, str]] = []
        self.action_kind: dict[str, str] = {}
        self.cost: list[int] = []


def _plain(sym: clingo.Symbol) -> str:
    """Render a symbol the way a human refers to it."""
    if sym.type == clingo.SymbolType.String:
        return sym.string
    return str(sym)


def solve(program_files: list[Path], facts: str = "") -> Model:
    """Run clingo over the given files plus inline facts, returning the optimal model.

    A cost-optimal plan is rarely unique -- the example site has two distinct plans at
    cost 51. Taking whichever the solver happened to report last makes the tool
    non-reproducible: the same site could be told to photograph different things on two
    consecutive runs, which is indefensible for anything that produces an audit finding.

    So all optima are collected and one is chosen by a stable rule: fewest actions first,
    then lexicographic order. Arbitrary, but *fixed*.

    Raises:
        RuntimeError: If ASP files contain syntax errors, grounding fails, or solver crashes.
    """
    try:
        ctl = clingo.Control(["--opt-mode=optN", "--models=0"])
    except Exception as e:
        raise RuntimeError(f"Failed to initialize clingo solver: {e}") from e

    try:
        for path in program_files:
            ctl.load(str(path))
    except RuntimeError as e:
        raise RuntimeError(
            f"Failed to load ASP program files. This usually means:\n"
            f"  • Syntax error in one of the .lp files\n"
            f"  • File not found or not readable\n"
            f"  • Invalid ASP structure\n"
            f"Files: {', '.join(str(p) for p in program_files)}\n"
            f"Error: {e}"
        ) from e

    if facts:
        try:
            ctl.add("base", [], facts)
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to add inline facts to ASP program. Check for:\n"
                f"  • Invalid ASP syntax in generated facts\n"
                f"  • Special characters not properly escaped\n"
                f"Facts:\n{facts}\n"
                f"Error: {e}"
            ) from e

    try:
        from rich.console import Console
        console = Console(stderr=True)
        console.print("[dim]Grounding program...[/dim]")
        ctl.ground([("base", [])])
        console.print("[dim]Solving...[/dim]")
    except RuntimeError as e:
        raise RuntimeError(
            f"ASP grounding failed. This usually means:\n"
            f"  • Contradictory facts in site file\n"
            f"  • Undefined predicates referenced\n"
            f"  • Infinite grounding (unbounded variables)\n"
            f"Error: {e}"
        ) from e

    candidates: list[Model] = []
    best = Model()

    def on_model(m: clingo.Model) -> None:
        found = Model()
        found.cost = list(m.cost)
        for sym in m.symbols(shown=True):
            args = sym.arguments
            if sym.name == "do":
                found.do.append(args[0])
            elif sym.name == "closes":
                found.closes.append(
                    (str(args[0]), _plain(args[1]), _plain(args[2]), _plain(args[3]))
                )
            elif sym.name == "action_cost":
                found.action_cost[str(args[0])] = args[1].number
            elif sym.name == "gap":
                found.gap.append((_plain(args[0]), _plain(args[1]), _plain(args[2])))
            elif sym.name == "unreachable":
                found.unreachable.append((_plain(args[0]), _plain(args[1]), _plain(args[2])))
            elif sym.name == "violated":
                found.violated.append((_plain(args[0]), _plain(args[1])))
            elif sym.name == "satisfied":
                found.satisfied.append((_plain(args[0]), _plain(args[1])))
            elif sym.name == "undetermined":
                found.undetermined.append((_plain(args[0]), _plain(args[1])))
            elif sym.name == "action_kind":
                found.action_kind[str(args[0])] = str(args[1])
        candidates.append(found)

    try:
        result = ctl.solve(on_model=on_model)
    except RuntimeError as e:
        raise RuntimeError(f"Solver execution failed: {e}") from e

    # Check for UNSATISFIABLE - happens when constraints are contradictory
    if result.unsatisfiable:
        raise RuntimeError(
            "Solver determined the constraints are UNSATISFIABLE. This means:\n"
            "  • Site facts are contradictory (e.g., declared 24 cells but site has 50)\n"
            "  • Impossible combination of requirements and site state\n"
            "  • Conflicting declarations in the knowledge base\n"
            "\n"
            "Check your site file for:\n"
            "  • Duplicate or conflicting facts about the same entity\n"
            "  • Cell counts, IDs, or relationships that don't match reality\n"
            "  • Facts that violate integrity constraints"
        )

    if not candidates:
        return best

    cheapest = min(m.cost[0] if m.cost else 0 for m in candidates)
    optimal = [m for m in candidates if (m.cost[0] if m.cost else 0) == cheapest]
    return min(optimal, key=lambda m: (len(m.do), sorted(str(a) for a in m.do)))


def observations_to_facts(observations: list[Observation], source: EvidenceSource | None = None) -> str:
    """Render captured observations as ASP facts.

    Generates both legacy obs/3 facts and new evidence/8 facts for gradual migration.
    New evidence/8 facts include identity, provenance, and temporal ordering.

    Args:
        observations: List of observations to convert
        source: Evidence source (defaults to anonymous inspector)
    """
    from .models import EvidenceSource, Evidence
    import time

    if source is None:
        source = EvidenceSource(type="human", id="inspector", system=None)

    lines = []
    timestamp = int(time.time())

    for i, o in enumerate(observations):
        # Legacy obs/3 format - backward compatibility
        value = "true" if o.value else "false"
        lines.append(f"obs({o.subject}, {o.observable}, {value}).")

        # New evidence/8 format - rich metadata
        ev = o.to_evidence(f"evidence_{i}", source, timestamp + i)  # Sequence timestamps
        lines.append(ev.to_asp())

    return "\n".join(lines)


def _instruction(kind: str, target: str, observables: list[str], clause: Clause | None) -> str:
    """Write the sentence the tech actually reads.

    Deliberately built from the rule's own observables and the clause's own words rather
    than from a generic template, so the instruction says what this requirement needs and
    the citation backs it up.
    """
    what = ", ".join(o.replace("_", " ") for o in sorted(set(observables)))
    verb = {
        "video": f"Record a continuous pass over {target}",
        "photo": f"Photograph {target}",
        "measurement": f"Measure {target}",
        "document": f"Obtain the record covering {target}",
    }.get(kind, f"Capture {target}")
    return f"{verb}. Must clearly establish: {what}."


def acceptance_index(rules: list[Rule]) -> dict[str, str]:
    """Map each observable name to the criterion that decides it.

    Built from the reviewed rules rather than restated in the manifest, so the wording an
    inspector is judged against is the same wording a reviewer signed off on.
    """
    from .compile import asp_constant

    index: dict[str, str] = {}
    for rule in rules:
        for obs in rule.observables:
            index.setdefault(asp_constant(obs.name), obs.accepts or obs.method)
    return index


def build_manifest(
    model: Model,
    site: str,
    clauses: dict[str, Clause],
    generated_from: dict[str, object],
    acceptance: dict[str, str] | None = None,
) -> Manifest:
    """Turn the solver's chosen actions into an ordered, citable capture plan."""
    # The solver reports which gaps each chosen action closes, so nothing has to be
    # re-derived here.
    by_action: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for aid, rule, subject, obs in model.closes:
        by_action[aid].append((rule, subject, obs))

    actions: list[Action] = []
    for aid in sorted({str(a) for a in model.do}):
        entries = by_action.get(aid, [])
        kind = model.action_kind.get(aid, "photo")
        target = _plain(clingo.parse_term(aid).arguments[0])
        per_rule: dict[str, tuple[set[str], set[str]]] = defaultdict(lambda: (set(), set()))
        for rule, subject, obs in entries:
            per_rule[rule][0].add(subject)
            per_rule[rule][1].add(obs)
        discharges = [
            Discharge(rule=r, subjects=sorted(subs), observables=sorted(obs))
            for r, (subs, obs) in sorted(per_rule.items())
        ]
        citations = [
            Citation(page_label=clauses[r].page_label, text=clauses[r].text)
            for r in sorted(per_rule)
            if r in clauses
        ]
        all_obs = sorted({o for _, obs in per_rule.values() for o in obs})
        first_clause = next((clauses[r] for r in sorted(per_rule) if r in clauses), None)
        actions.append(
            Action(
                id=aid,
                kind=kind if kind in ("photo", "video", "measurement", "document") else "photo",
                target=target,
                cost=model.action_cost.get(aid, 0),
                instruction=_instruction(kind, target, all_obs, first_clause),
                discharges=discharges,
                citations=citations,
                acceptance={o: (acceptance or {}).get(o, "") for o in all_obs},
            )
        )

    actions.sort(key=lambda a: (KIND_ORDER.get(a.kind, 9), a.target, a.id))

    open_items = [
        OpenItem(
            rule=r,
            subject=s,
            observable=o,
            reason="no available capture action can produce this observation",
        )
        for r, s, o in sorted(model.unreachable)
    ]
    # Requirements that no observation can ever settle (process obligations) surface here
    # too, so a clean-looking plan never hides them.
    planned_rules = {d.rule for a in actions for d in a.discharges}
    for rule, subject in sorted(model.undetermined):
        if rule in planned_rules or any(o.rule == rule and o.subject == subject for o in open_items):
            continue
        open_items.append(
            OpenItem(
                rule=rule,
                subject=subject,
                observable="-",
                reason="requirement is not field-verifiable; settle by document or process review",
            )
        )

    return Manifest(
        site=site,
        generated_from=generated_from,
        actions=actions,
        undetermined_after_plan=open_items,
    )


def build_verdicts(model: Model, clauses: dict[str, Clause]) -> list[Verdict]:
    """Report every applicable requirement in one of three states."""
    missing: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rule, subject, obs in model.gap:
        missing[(rule, subject)].append(obs)

    verdicts: list[Verdict] = []
    for status, pairs in (
        ("violated", model.violated),
        ("undetermined", model.undetermined),
        ("satisfied", model.satisfied),
    ):
        for rule, subject in pairs:
            clause = clauses.get(rule)
            verdicts.append(
                Verdict(
                    rule=rule,
                    subject=subject,
                    status=status,  # type: ignore[arg-type]
                    citation=Citation(page_label=clause.page_label, text=clause.text)
                    if clause
                    else None,
                    missing=sorted(missing.get((rule, subject), [])),
                )
            )
    order = {"violated": 0, "undetermined": 1, "satisfied": 2}
    verdicts.sort(key=lambda v: (order[v.status], v.rule, v.subject))
    return verdicts
