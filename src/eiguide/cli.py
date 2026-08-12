"""Command line interface.

The pipeline as a sequence of inspectable steps:

    extract    PDF        -> data/clauses.jsonl      verbatim clauses + provenance
    review     rules      -> rules marked reviewed   human check of each interpretation
    compile    rules      -> rules/chapter_<x>.lp    mechanical, no judgement
    plan       site       -> printed manifest        the cheapest set of captures
    inspect    site       -> printed verdict         adaptive walkthrough, re-planned

The first three steps persist their output, because extraction is slow and rule
interpretations are reviewed by hand and reused. The last two do not: a plan and an
inspection are both derived entirely from the rules plus the site, so there is nothing
worth keeping and a stale copy would only mislead.

``data/rules.jsonl`` -- the structured interpretation of each clause -- is currently
hand-authored and reviewed. Generating a first draft of it with a language model is the
obvious next step, but nothing downstream depends on how it was produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import compile as compile_mod
from . import prove as prove_mod
from . import reason
from .extract import extract as run_extract
from .models import Clause, Observation, Rule
from .store import read_jsonl, write_json, write_jsonl

app = typer.Typer(add_completion=False, help="Compliance reasoning over installation standards.")
console = Console()

ROOT = Path.cwd()
DATA = ROOT / "data"
RULES_DIR = ROOT / "rules"
ONTOLOGY = ROOT / "ontology"

STATUS_STYLE = {"violated": "bold red", "undetermined": "yellow", "satisfied": "green"}


def _load_clauses(path: Path) -> dict[str, Clause]:
    return {c.id: c for c in read_jsonl(path, Clause)}


def _short(subject: str) -> str:
    """The part of a subject term an inspector would actually type: cell(bs1,7) -> 7."""
    inner = subject[subject.find("(") + 1 : subject.rfind(")")] if "(" in subject else subject
    return inner.split(",")[-1].strip() if inner else subject


def _clause_for_rule(clauses: dict[str, Clause], rules: list[Rule]) -> dict[str, Clause]:
    """Index clauses by rule id.

    One clause can yield several rules (D.6.6 -> D.6.6a, D.6.6b), so citations have to be
    resolved through the rule's clause_id rather than by assuming the ids match.
    """
    return {r.id: clauses[r.clause_id] for r in rules if r.clause_id in clauses}


def _load_rules(rules_file: Path, chapters: list[str]) -> list[Rule]:
    wanted = tuple(f"{c}." for c in chapters)
    return [r for r in read_jsonl(rules_file, Rule) if r.clause_id.startswith(wanted)]


@app.command()
def extract(
    pdf: Annotated[Path, typer.Argument(help="Source PDF.")] = Path("EIGuide-61[1].pdf"),
    out: Annotated[Path, typer.Option(help="Where to write clauses.")] = DATA / "clauses.jsonl",
    doc: str = "EIGuide",
    version: str = "6.0",
) -> None:
    """Recover clauses, figures and tables from the PDF."""
    clauses, figures, tables = run_extract(pdf, doc_name=doc, doc_version=version)
    n = write_jsonl(out, clauses)
    write_jsonl(out.with_name("figures.jsonl"), figures)
    write_jsonl(out.with_name("tables.jsonl"), tables)

    by_chapter: dict[str, int] = {}
    for c in clauses:
        by_chapter[c.chapter] = by_chapter.get(c.chapter, 0) + 1

    table = Table(title=f"{n} clauses from {pdf.name}")
    table.add_column("Chapter")
    table.add_column("Title")
    table.add_column("Clauses", justify="right")
    table.add_column("Binding", justify="right")
    for ch in sorted(by_chapter):
        binding = sum(
            1 for c in clauses if c.chapter == ch and c.modality in ("shall", "must", "imperative")
        )
        title = next((c.chapter_title for c in clauses if c.chapter == ch), "")
        table.add_row(ch, title, str(by_chapter[ch]), str(binding))
    console.print(table)
    console.print(f"figures: {len(figures)}  tables: {len(tables)}  -> {out}")


@app.command()
def compile(
    chapter: Annotated[str, typer.Option(help="Chapter letter, e.g. D.")],
    rules_file: Annotated[Path, typer.Option(help="Structured rules.")] = DATA / "rules.jsonl",
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    out_dir: Annotated[Path, typer.Option()] = RULES_DIR,
) -> None:
    """Compile structured rules into a clingo program."""
    rules = [r for r in read_jsonl(rules_file, Rule) if r.clause_id.startswith(f"{chapter}.")]
    if not rules:
        console.print(f"[red]No rules for chapter {chapter} in {rules_file}[/red]")
        raise typer.Exit(1)
    clauses = _load_clauses(clauses_file)
    source = compile_mod.compile_rules(rules, clauses, chapter, "EIGuide", "6.0")
    out = out_dir / f"chapter_{chapter.lower()}.lp"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")

    problems = compile_mod.check_exemptions(rules)
    for problem in problems:
        console.print(f"[bold red]exemption not in force:[/bold red] {problem}")

    obligations = sum(1 for r in rules if r.kind == "obligation")
    exemptions = sum(1 for r in rules if r.kind == "exemption")
    unreviewed = sum(1 for r in rules if not r.reviewed)
    console.print(
        f"[green]{out}[/green]  {len(rules)} rules "
        f"({obligations} obligations, {exemptions} exemptions verified)"
    )
    if unreviewed:
        console.print(f"[yellow]{unreviewed} rule(s) not yet reviewed[/yellow]")


def _programs(chapters: list[str]) -> list[Path]:
    files = [ONTOLOGY / "core.lp", ONTOLOGY / "domain.lp"]
    for ch in chapters:
        path = RULES_DIR / f"chapter_{ch.lower()}.lp"
        if not path.exists():
            console.print(f"[red]missing {path}; run `eiguide compile --chapter {ch}` first[/red]")
            raise typer.Exit(1)
        files.append(path)
    return files


@app.command()
def plan(
    site: Annotated[Path, typer.Option(help="Site facts (.lp).")] = Path("sites/den01.lp"),
    chapter: Annotated[list[str], typer.Option(help="Chapters in scope.")] = ["D"],
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    out: Annotated[Path | None, typer.Option(help="Also write the manifest as JSON.")] = None,
) -> None:
    """Work out the cheapest set of captures that would settle every open requirement.

    Read-only. Writes nothing unless asked with --out.
    """
    model = reason.solve(_programs(chapter) + [site], "")

    rules = _load_rules(DATA / "rules.jsonl", chapter)
    clauses = _clause_for_rule(_load_clauses(clauses_file), rules)
    site_name = site.stem
    manifest = reason.build_manifest(
        model,
        site_name,
        clauses,
        {"doc": "EIGuide", "version": "6.0", "chapters": list(chapter)},
        reason.acceptance_index(rules),
    )
    console.print(
        Panel(
            f"[bold]{len(manifest.actions)}[/bold] capture actions "
            f"close [bold]{len(model.gap)}[/bold] evidence gaps "
            f"across [bold]{len({g[0] for g in model.gap})}[/bold] requirements",
            title=f"Evidence plan — {site_name}",
        )
    )
    for i, action in enumerate(manifest.actions, 1):
        rules = ", ".join(sorted({d.rule for d in action.discharges}))
        console.print(f"[bold cyan]{i}. [{action.kind}][/bold cyan] {action.instruction}")
        console.print(f"   [dim]settles {rules} · cost {action.cost} · {action.id}[/dim]")
    if manifest.undetermined_after_plan:
        console.print(
            f"\n[yellow]{len(manifest.undetermined_after_plan)} requirement(s) cannot be "
            f"settled by capture:[/yellow]"
        )
        for item in manifest.undetermined_after_plan[:10]:
            console.print(f"   [yellow]{item.rule} on {item.subject}[/yellow] — {item.reason}")
    if out:
        write_json(out, manifest)
        console.print(f"\n[dim]{out}[/dim]")


@app.command()
def inspect(
    site: Annotated[Path, typer.Option(help="Site facts (.lp).")] = Path("sites/den01.lp"),
    chapter: Annotated[list[str], typer.Option(help="Chapters in scope.")] = ["D"],
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    detail: Annotated[bool, typer.Option(help="List every subject in the verdict.")] = False,
) -> None:
    """Walk the site one action at a time, re-planning after each answer.

    The plan is recomputed against the solver after every action, so the walkthrough
    adapts: a failure surfaces its violation immediately, and evidence that settles several
    requirements at once removes all of them from what is left to do. What you are asked
    next is always what the reasoner currently needs most -- never a fixed checklist.

    One session, start to finish. Answers live in memory and the verdict is printed at the
    end; nothing is written to disk. A half-finished walk left lying around is worse than
    no walk at all, because the next run silently inherits it and reports a site as
    inspected when it was not.
    """
    programs = _programs(chapter) + [site]
    rules = _load_rules(DATA / "rules.jsonl", chapter)
    clauses = _clause_for_rule(_load_clauses(clauses_file), rules)
    acceptance = reason.acceptance_index(rules)
    meta = {"doc": "EIGuide", "version": "6.0", "chapters": list(chapter)}

    recorded: dict[tuple[str, str], Observation] = {}
    # Several rules can come from one clause (D.6.6 -> D.6.6a, D.6.6b), and a sweep and a
    # survey over the same subject cite it again. Quoting it in full every time drowns the
    # instruction, so each clause is shown once and referenced by number afterwards.
    quoted: set[str] = set()
    step = 0
    while True:
        model = reason.solve(programs, reason.observations_to_facts(list(recorded.values())))
        manifest = reason.build_manifest(model, site.stem, clauses, meta, acceptance)

        done = len(model.satisfied)
        failed = len(model.violated)
        open_now = len(model.undetermined)
        console.print(
            f"[green]{done} satisfied[/green] · [bold red]{failed} violated[/bold red] · "
            f"[yellow]{open_now} open[/yellow] · "
            f"[cyan]{len(manifest.actions)} action(s) left[/cyan]"
        )

        if not manifest.actions:
            break

        action = manifest.actions[0]
        step += 1
        body = action.instruction
        fresh_quotes = [c for c in action.citations if c.text not in quoted]
        for citation in fresh_quotes:
            quoted.add(citation.text)
            body += f"\n\n[dim]{citation.page_label} — {_clip(citation.text)}[/dim]"
        if action.citations and not fresh_quotes:
            # Every clause behind this action has already been quoted; a pointer is enough.
            where = sorted({c.page_label for c in action.citations})
            body += f"\n[dim](see {', '.join(where)}, quoted above)[/dim]"
        console.print(
            Panel(
                body,
                title=f"Step {step} · {action.kind} · {action.target}",
                subtitle=f"settles {', '.join(sorted({d.rule for d in action.discharges}))}",
            )
        )

        pairs = sorted(
            {
                (subject, obs)
                for d in action.discharges
                for subject in d.subjects
                for obs in d.observables
            }
        )
        # A sweep covers every member of a group; asking once per member would defeat the
        # point of choosing it, so identical observables are answered once and applied to
        # all subjects the solver said this action covers.
        by_obs: dict[str, list[str]] = {}
        for subject, obs in pairs:
            by_obs.setdefault(obs, []).append(subject)

        quit_now = False
        for obs, subjects in sorted(by_obs.items()):
            scope = subjects[0] if len(subjects) == 1 else f"all {len(subjects)} subjects"
            criterion = action.acceptance.get(obs) or "(no acceptance criterion recorded)"
            console.print(f"  [bold]{obs}[/bold] — {scope}")
            console.print(f"     [dim]accepts: {criterion}[/dim]")
            # Only an explicit, recognized answer is accepted. Treating a typo as a
            # failure would fabricate a violation; treating it as a pass would fabricate
            # compliance. Both are worse than asking again.
            while True:
                answer = (
                    typer.prompt("     [p]ass / [f]ail / [s]kip / [q]uit", default="p")
                    .strip()
                    .lower()
                )
                if answer[:1] in ("p", "f", "s", "q"):
                    break
                console.print("     [yellow]answer p, f, s or q[/yellow]")

            if answer.startswith("q"):
                quit_now = True
                break
            if answer.startswith("s"):
                # Skipping leaves the requirement undetermined, which is the honest
                # outcome: the plan will keep asking rather than assuming the best.
                continue
            value = answer.startswith("p")
            failing = set(subjects)
            if not value and len(subjects) > 1:
                # One pass over a group usually finds a few bad items, not a wholly bad
                # group. Condemning all 24 cells because two are unlabelled would be
                # wrong, and would bury the actual defect.
                console.print(f"     [dim]{', '.join(subjects[:6])}{'...' if len(subjects) > 6 else ''}[/dim]")
                which = typer.prompt(
                    "     which failed? (comma-separated, or 'all')", default="all"
                ).strip()
                if which.lower() != "all":
                    picked = {w.strip() for w in which.split(",") if w.strip()}
                    matched = {s for s in subjects if s in picked or _short(s) in picked}
                    if matched:
                        failing = matched
                    else:
                        console.print("     [yellow]no subject matched; recording all as failed[/yellow]")

            # A failure is worth explaining; a pass is not, so only failures are asked
            # to justify themselves.
            note = typer.prompt("     what was wrong?", default="") if not value else ""
            for subject in subjects:
                failed_here = (not value) and subject in failing
                recorded[(subject, obs)] = Observation(
                    subject=subject,
                    observable=obs,
                    value=not failed_here if not value else True,
                    action=action.id,
                    note=note or None if failed_here else None,
                )

        if quit_now:
            console.print(
                f"\n[yellow]Stopped after {len(recorded)} observation(s).[/yellow] "
                "Everything unanswered stays undetermined."
            )
            break

        # Nothing recorded this round means every observable was skipped; asking the same
        # question forever helps nobody.
        if not any(o.action == action.id for o in recorded.values()):
            console.print("[yellow]nothing recorded for that action; stopping.[/yellow]")
            break

    console.print()
    model = reason.solve(programs, reason.observations_to_facts(list(recorded.values())))
    verdicts = reason.build_verdicts(model, clauses)
    if detail:
        table = Table(title=f"{site.stem} — {len(recorded)} observations")
        for col in ("Status", "Rule", "Subject", "Missing evidence"):
            table.add_column(col)
        for v in verdicts:
            table.add_row(
                f"[{STATUS_STYLE[v.status]}]{v.status}[/{STATUS_STYLE[v.status]}]",
                v.rule,
                v.subject,
                ", ".join(v.missing[:3]) + ("..." if len(v.missing) > 3 else ""),
            )
        console.print(table)
    else:
        _print_rollup(verdicts, clauses, site.stem, len(recorded))
    _print_totals(verdicts)
    if not detail:
        console.print("[dim]Every subject: eiguide inspect --detail[/dim]")


def _clip(text: str, limit: int = 220) -> str:
    """Trim a quotation at a word boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _name_subjects(subjects: list[str], limit: int = 6) -> str:
    """Name the offenders concisely, without hiding how many there are."""
    shown = ", ".join(subjects[:limit])
    extra = len(subjects) - limit
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def _print_rollup(verdicts, clauses, site_name: str, n_obs: int) -> None:
    """One row per requirement, problems named in full and passes counted."""
    by_rule: dict[str, dict[str, list[str]]] = {}
    for v in verdicts:
        by_rule.setdefault(v.rule, {"violated": [], "undetermined": [], "satisfied": []})
        by_rule[v.rule][v.status].append(v.subject)

    table = Table(title=f"{site_name} — {n_obs} observations, {len(by_rule)} requirements")
    # One line per requirement. A verdict table is scanned, not read.
    table.add_column("Rule", no_wrap=True, min_width=6)
    table.add_column("Requirement", width=26, no_wrap=True, overflow="ellipsis")
    table.add_column("n", justify="right", width=3)
    table.add_column("Outcome", no_wrap=True, overflow="ellipsis", width=32)

    def rank(item: tuple[str, dict[str, list[str]]]) -> tuple:
        _, buckets = item
        return (0 if buckets["violated"] else 1 if buckets["undetermined"] else 2,)

    for rule, buckets in sorted(by_rule.items(), key=lambda kv: (rank(kv), kv[0])):
        total = sum(len(v) for v in buckets.values())
        clause = clauses.get(rule)
        summary = clause.text if clause else ""
        if buckets["violated"]:
            outcome = (
                f"[bold red]{len(buckets['violated'])}/{total} violated[/bold red] "
                f"{_name_subjects(sorted(buckets['violated']), 3)}"
            )
        elif buckets["undetermined"]:
            outcome = (
                f"[yellow]{len(buckets['undetermined'])}/{total} unchecked[/yellow] "
                f"{_name_subjects(sorted(buckets['undetermined']), 3)}"
            )
        else:
            outcome = f"[green]{total}/{total} ok[/green]"
        table.add_row(rule, summary, str(total), outcome)
    console.print(table)


def _print_totals(verdicts) -> None:
    counts = {"violated": 0, "undetermined": 0, "satisfied": 0}
    for v in verdicts:
        counts[v.status] += 1
    console.print(
        f"[bold red]{counts['violated']} violated[/bold red] · "
        f"[yellow]{counts['undetermined']} undetermined[/yellow] · "
        f"[green]{counts['satisfied']} satisfied[/green]"
    )
    if counts["undetermined"]:
        console.print(
            "[dim]Undetermined is not compliant -- it means nobody looked.[/dim]"
        )


@app.command()
def review(
    rules_file: Annotated[Path, typer.Option()] = DATA / "rules.jsonl",
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    threshold: Annotated[float, typer.Option(help="Auto-queue rules below this confidence.")] = 1.0,
) -> None:
    """Step through unreviewed rules beside their source clause."""
    rules = read_jsonl(rules_file, Rule)
    clauses = _load_clauses(clauses_file)
    queue = [r for r in rules if not r.reviewed or r.confidence < threshold]
    if not queue:
        console.print("[green]Nothing to review.[/green]")
        return

    for rule in queue:
        clause = clauses.get(rule.clause_id)
        console.print(
            Panel(
                clause.text if clause else "[dim]source clause not found[/dim]",
                title=f"{rule.clause_id} [{clause.page_label if clause else '?'}]",
            )
        )
        console.print(
            Panel(
                json.dumps(rule.model_dump(exclude={"reviewed"}), indent=2),
                title=f"extracted rule {rule.id} (confidence {rule.confidence:.2f})",
            )
        )
        if clause and rule.citation_span not in clause.text:
            console.print("[bold red]citation_span is not verbatim in the source clause[/bold red]")
        answer = typer.prompt("accept / reject / quit [a/r/q]", default="a").strip().lower()
        if answer.startswith("q"):
            break
        rule.reviewed = answer.startswith("a")
    write_jsonl(rules_file, rules)
    console.print(f"[green]saved[/green] -> {rules_file}")


@app.command()
def prove(
    site: Annotated[Path, typer.Option(help="Site facts (.lp).")] = Path("sites/den01.lp"),
    chapter: Annotated[list[str], typer.Option()] = ["D"],
) -> None:
    """Test whether the ASP solver actually earns its place.

    Runs each claim against a control -- a closed-world engine, hand-written capture
    strategies, sites with the carve-outs removed -- and reports the numbers either way.
    """
    programs = _programs(chapter)
    results = prove_mod.run_all(programs, site)

    for r in results:
        console.print()
        console.print(Panel(r.headline, title=r.name))
        table = Table(show_header=bool(r.columns))
        for col in r.columns:
            table.add_column(col)
        for row in r.rows:
            table.add_row(*[str(c) for c in row])
        console.print(table)
        style = (
            "green" if r.verdict.startswith(("SOLVER WINS", "PASS"))
            else "red" if r.verdict.startswith("FAIL")
            else "yellow"
        )
        console.print(f"[{style}]{r.verdict}[/{style}]")

    wins = sum(1 for r in results if r.verdict.startswith(("SOLVER WINS", "PASS")))
    console.print()
    console.print(f"[bold]{wins}/{len(results)} claims hold up.[/bold]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
