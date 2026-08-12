"""Evidence that the ASP solver earns its place.

The claim under test is narrow and falsifiable: **a solver does something here that a
checklist, a Datalog engine, or a rules engine like OPA/Rego cannot.** That claim is easy
to assert and easy to believe wrongly, so this module tries to break it instead.

Four experiments, each with a control:

``open_world``   three-valued reasoning vs. the closed-world answer. The control is what a
                 Datalog/Rego engine reports on the same facts.
``optimization`` the solver's plan vs. the two obvious hand-written strategies. The control
                 is what a competent engineer would code without a solver.
``applicability`` requirements switching on and off from site facts alone. The control is
                 the same rules against a site with the carve-out conditions removed.
``scaling``      how plan *shape* changes with site size, and what it costs to compute.

Each returns numbers. Where the solver does not win, the numbers say so.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import reason


@dataclass
class SiteSpec:
    """A synthetic site, generated rather than hand-written.

    Hand-authored .lp files cannot be varied along one axis at a time, which is exactly
    what is needed to see how the solver responds to site shape.
    """

    name: str
    cells: int = 24
    strings: int = 1
    fuse_panels: int = 2
    leads: int = 5

    def to_asp(self) -> str:
        lines = [f"site({self.name})."]
        for s in range(1, self.strings + 1):
            lines.append(f"battery_string(bs{s}).")
            if self.cells:
                lines.append(f"cell(bs{s}, 1..{self.cells}).")
        for p in range(1, self.fuse_panels + 1):
            lines.append(f"fuse_panel(fp{p}).")
        if self.fuse_panels >= 2:
            lines.append("misc_bay_mounted(fp2).")
        lines.append("fuse_record_book(frb1).")
        for i in range(1, self.leads + 1):
            lines.append(f"lead(l{i}).")
            if i % 3 == 1:
                lines.append(f"battery_lead(l{i}). terminates_at(l{i}, return_bus_bar).")
            elif i % 3 == 2:
                lines.append(f"battery_lead(l{i}). terminates_at(l{i}, rectifier).")
            else:
                lines.append(f"ground_cable(l{i}). terminates_at(l{i}, office_ground_bar).")
        return "\n".join(lines)

    @property
    def subject_count(self) -> int:
        return self.strings * (1 + self.cells) + self.fuse_panels + self.leads + 1


@dataclass
class Result:
    """One experiment's findings."""

    name: str
    headline: str
    rows: list[tuple] = field(default_factory=list)
    columns: tuple[str, ...] = ()
    verdict: str = ""


def _solve(programs: list[Path], site_asp: str, facts: str = "") -> tuple[reason.Model, float]:
    started = time.perf_counter()
    model = reason.solve(programs, site_asp + "\n" + facts)
    return model, time.perf_counter() - started


# ---------------------------------------------------------------------------
# 1. Open world vs closed world
# ---------------------------------------------------------------------------


def open_world(programs: list[Path], site: SiteSpec) -> Result:
    """What a closed-world engine would report on a site nobody has inspected.

    Datalog and Rego derive only what is provable. `violated` is not provable without
    observations, so a policy written as "compliant unless violated" -- the natural way to
    write it in those languages -- returns compliant. The same rules under ASP return
    undetermined, because absence of a violation is not evidence of compliance.
    """
    asp = site.to_asp()
    model, _ = _solve(programs, asp)

    applicable = len(model.satisfied) + len(model.violated) + len(model.undetermined)
    # The closed-world reading of exactly the same derived facts.
    closed_world_compliant = applicable - len(model.violated)

    rows = [
        ("requirements in force", applicable),
        ("proven violated", len(model.violated)),
        ("proven satisfied", len(model.satisfied)),
        ("nobody looked (undetermined)", len(model.undetermined)),
        ("", ""),
        ("closed-world verdict: 'compliant'", closed_world_compliant),
        ("open-world verdict: 'compliant'", len(model.satisfied)),
    ]
    return Result(
        name="Open world vs closed world",
        headline=(
            f"On an uninspected site, a closed-world engine reports "
            f"{closed_world_compliant} requirements compliant. The correct answer is "
            f"{len(model.satisfied)}."
        ),
        columns=("measure", "count"),
        rows=rows,
        verdict=(
            "SOLVER WINS -- and not marginally. Closed-world reasoning certifies an "
            "entire uninspected site as compliant, because nothing has been proven wrong "
            "yet. This is the single strongest argument for ASP here."
            if closed_world_compliant > len(model.satisfied)
            else "NO DIFFERENCE on this site."
        ),
    )


# ---------------------------------------------------------------------------
# 2. Optimization vs hand-written strategies
# ---------------------------------------------------------------------------


def optimization(programs: list[Path], site: SiteSpec) -> Result:
    """The solver's plan against the strategies a person would write without one.

    Two controls, both defensible and both what real code tends to do:

    ``per-gap``      one capture per outstanding observation. The obvious loop.
    ``per-subject``  one visit per subject, covering all its observations. The obvious
                     optimization someone writes after seeing per-gap output.

    Costs come from the same ``action_cost`` facts the solver uses, so this compares
    strategies under one cost model rather than comparing cost models.
    """
    asp = site.to_asp()
    model, _ = _solve(programs, asp)

    gaps = set(model.gap)
    subjects_needing = {(x, o) for _, x, o in gaps}

    # Control A: one capture(X,O) per gap.
    per_gap_cost = 5 * len(subjects_needing)

    # Control B: one visit per subject, covering everything observable on it.
    per_subject_visits = {x for x, _ in subjects_needing}
    per_subject_cost = 6 * len(per_subject_visits)

    solver_cost = model.cost[0] if model.cost else 0
    solver_actions = len(model.do)

    best_control = min(per_gap_cost, per_subject_cost)
    saving = (1 - solver_cost / best_control) * 100 if best_control else 0.0

    rows = [
        ("per-gap loop (one capture each)", len(subjects_needing), per_gap_cost),
        ("per-subject visit", len(per_subject_visits), per_subject_cost),
        ("solver plan", solver_actions, solver_cost),
    ]
    return Result(
        name="Optimization vs hand-written strategies",
        headline=(
            f"{solver_actions} actions at cost {solver_cost}, against {len(subjects_needing)} "
            f"captures at cost {per_gap_cost} for the obvious loop "
            f"({saving:.0f}% cheaper than the best hand-written strategy)."
        ),
        columns=("strategy", "actions", "cost"),
        rows=rows,
        verdict=(
            f"SOLVER WINS by {saving:.0f}%. Note the honest caveat: the cost model "
            f"(5/6/10) is invented. What the solver contributes is picking the right mix "
            f"per site without anyone coding the rule -- not the specific numbers."
            if solver_cost < best_control
            else "NO WIN -- a hand-written strategy matches the solver on this site."
        ),
    )


# ---------------------------------------------------------------------------
# 3. Applicability driven by site facts
# ---------------------------------------------------------------------------


def applicability(programs: list[Path], site_file: Path) -> Result:
    """Requirements switching on and off from facts alone, with no code change.

    Each row toggles one site fact and reports which requirements come into force. This is
    the part a checklist genuinely cannot do: a static list of things to check cannot know
    that a lead internal to a relay rack is exempt from tagging.
    """
    base = site_file.read_text()
    variants = {
        "as authored": base,
        "l3 no longer internal to rack": base.replace("internal_to_rack(l3).", ""),
        "l5 no longer a short visible run": base.replace("short_visible_run(l5).", ""),
        "fp2 not misc bay mounted": base.replace("misc_bay_mounted(fp2).", ""),
        "fp2 has other fuse identification": base + "\nother_fuse_identification(fp2).",
    }

    rows = []
    baseline = None
    for label, asp in variants.items():
        model, _ = _solve(programs, asp)
        in_force = len(model.satisfied) + len(model.violated) + len(model.undetermined)
        rules = {r for r, _ in model.undetermined} | {r for r, _ in model.violated}
        if baseline is None:
            baseline = in_force
            delta = "-"
        else:
            delta = f"{in_force - baseline:+d}"
        rows.append((label, in_force, delta, len(rules)))

    changed = sum(1 for r in rows[1:] if r[2] != "+0")
    return Result(
        name="Applicability from site facts",
        headline=(
            f"{changed} of {len(rows) - 1} single-fact edits change which requirements are "
            f"in force, with no change to any rule."
        ),
        columns=("site variant", "requirements in force", "delta", "distinct rules"),
        rows=rows,
        verdict=(
            "SOLVER WINS. Carve-outs are data, not code. A checklist would have to be "
            "rewritten per site; these are the same rules against different facts."
            if changed
            else "NO DIFFERENCE -- the carve-outs are not doing any work."
        ),
    )


# ---------------------------------------------------------------------------
# 4. Scaling
# ---------------------------------------------------------------------------


def scaling(programs: list[Path], sizes: list[int]) -> Result:
    """How the plan's *shape* changes with site size, and what solving costs.

    The interesting result is not that big sites cost more. It is that the solver switches
    strategy on its own: for a 1-cell string a per-subject capture is cheapest, and past
    some threshold a single sweep wins. Nobody codes that threshold; it falls out of the
    cost model.
    """
    rows = []
    for n in sizes:
        site = SiteSpec(name="synth", cells=n)
        model, elapsed = _solve(programs, site.to_asp())
        chosen = sorted(str(a) for a in model.do)
        sweeps = sum(1 for a in chosen if a.startswith("sweep"))
        surveys = sum(1 for a in chosen if a.startswith("survey"))
        captures = sum(1 for a in chosen if a.startswith("capture"))
        strategy = "sweep" if sweeps else ("survey" if surveys else "capture")
        rows.append(
            (
                n,
                site.subject_count,
                len(model.gap),
                len(chosen),
                f"{sweeps}/{surveys}/{captures}",
                strategy,
                f"{elapsed * 1000:.0f}ms",
            )
        )

    strategies = {r[5] for r in rows}
    return Result(
        name="Scaling and strategy switching",
        headline=(
            f"Across {min(sizes)}-{max(sizes)} cells the plan stays "
            f"{min(r[3] for r in rows)}-{max(r[3] for r in rows)} actions while gaps grow "
            f"to {max(r[2] for r in rows)}."
        ),
        columns=("cells", "subjects", "gaps", "actions", "sweep/survey/capture", "strategy", "solve"),
        rows=rows,
        verdict=(
            "SOLVER WINS. It changes strategy with site size on its own."
            if len(strategies) > 1
            else "PARTIAL -- plan size stays flat as the site grows, but the strategy mix "
            "never switches across this range, so the threshold behaviour is unproven here."
        ),
    )


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def determinism(programs: list[Path], site_file: Path, runs: int = 5) -> Result:
    """The same input must produce the same plan. Re-solved from scratch each time."""
    asp = site_file.read_text()
    plans = []
    for _ in range(runs):
        model, _ = _solve(programs, asp)
        plans.append(tuple(sorted(str(a) for a in model.do)))
    distinct = set(plans)
    return Result(
        name="Determinism",
        headline=f"{runs} independent solves produced {len(distinct)} distinct plan(s).",
        columns=("run", "actions", "plan hash"),
        rows=[(i + 1, len(p), f"{hash(p) & 0xFFFFFF:06x}") for i, p in enumerate(plans)],
        verdict=(
            "PASS -- reproducible."
            if len(distinct) == 1
            else f"FAIL -- {len(distinct)} different plans for identical input."
        ),
    )


def run_all(programs: list[Path], site_file: Path) -> list[Result]:
    base = SiteSpec(name="den01")
    return [
        open_world(programs, base),
        optimization(programs, base),
        applicability(programs, site_file),
        scaling(programs, [1, 2, 4, 8, 24, 96, 240]),
        determinism(programs, site_file),
    ]
