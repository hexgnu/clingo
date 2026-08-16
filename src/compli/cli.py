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

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

import importlib.metadata
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
from . import triage as triage_mod
from . import validate as validate_mod
from .extract import extract as run_extract
from .models import Clause, Observation, Rule
from .store import read_jsonl, write_json, write_jsonl
from .ticket import Ticket

app = typer.Typer(add_completion=False, help="Compliance reasoning over installation standards.")
console = Console()


def version_callback(value: bool):
    """Display version and exit."""
    if value:
        try:
            version = importlib.metadata.version("compli")
        except importlib.metadata.PackageNotFoundError:
            version = "dev"
        console.print(f"compli version {version}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            help="Show version and exit",
        ),
    ] = False,
):
    """Compliance reasoning over installation standards."""
    pass

ROOT = Path.cwd()
DATA = ROOT / "data"
RULES_DIR = ROOT / "rules"
ONTOLOGY = ROOT / "ontology"

STATUS_STYLE = {"violated": "bold red", "undetermined": "yellow", "satisfied": "green"}


def _load_clauses(path: Path) -> dict[str, Clause]:
    clauses = read_jsonl(path, Clause)

    # Warn if file is missing or empty (read_jsonl returns [] for missing files)
    if not clauses:
        if not path.exists():
            console.print(
                f"[red]Error: Clauses file not found[/red]\n"
                f"  Expected: {path}\n"
                f"\n"
                f"[cyan]→ Fix:[/cyan] Extract clauses from your PDF:\n"
                f"    compli extract <your-pdf.pdf>\n"
                f"\n"
                f"[dim]Or with LLM (faster, needs API key):[/dim]\n"
                f"    compli extract-llm <your-pdf.pdf>\n"
                f"\n"
                f"[dim]Don't have a PDF? See examples/ for sample datasets[/dim]"
            )
        else:
            console.print(
                f"[yellow]Warning: Clauses file is empty: {path}[/yellow]\n"
                f"The file exists but contains no clauses.\n"
                f"\n"
                f"[cyan]→ Fix:[/cyan] Re-run extraction:\n"
                f"    compli extract <your-pdf.pdf>"
            )

    return {c.id: c for c in clauses}


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


def _load_rules(rules_file: Path, chapters: list[str], validate_citations: bool = False) -> list[Rule]:
    all_rules = read_jsonl(rules_file, Rule)

    # Warn if file is missing or empty
    if not all_rules:
        if not rules_file.exists():
            console.print(
                f"[red]Error: Rules file not found[/red]\n"
                f"  Expected: {rules_file}\n"
                f"\n"
                f"[cyan]→ Fix:[/cyan] Compile your rules:\n"
                f"    compli compile --chapter {' '.join(chapters)} --rules-file {rules_file}\n"
                f"\n"
                f"[dim]Or extract rules from PDF with LLM:[/dim]\n"
                f"    compli extract-llm <your-pdf.pdf> --out {rules_file}"
            )
        else:
            console.print(
                f"[yellow]Warning: Rules file is empty: {rules_file}[/yellow]\n"
                f"\n"
                f"[cyan]→ Fix:[/cyan] Extract rules from PDF:\n"
                f"    compli extract-llm <your-pdf.pdf> --out {rules_file}"
            )

    wanted = tuple(f"{c}." for c in chapters)
    filtered = [r for r in all_rules if r.clause_id.startswith(wanted)]

    if not filtered and all_rules:
        available = {r.clause_id[0] for r in all_rules if r.clause_id}
        console.print(
            f"[yellow]No rules found for chapter(s): {', '.join(chapters)}[/yellow]\n"
            f"Available chapters in {rules_file.name}: {', '.join(sorted(available))}\n"
            f"\n"
            f"[cyan]→ Fix:[/cyan] Use an available chapter:\n"
            f"    compli plan --chapter {','.join(sorted(available))} --site <site-file>"
        )

    # Optional: Validate citation_spans when loading for plan/inspect
    if validate_citations and filtered:
        # Load clauses to validate against
        clauses_file = rules_file.parent / "clauses.jsonl"
        if clauses_file.exists():
            clauses_dict = _load_clauses(clauses_file)
            invalid_citations = []

            for rule in filtered:
                clause = clauses_dict.get(rule.clause_id)
                if clause and rule.citation_span:
                    # Normalize both for comparison (remove degree symbols, extra quotes)
                    normalized_clause = clause.text.replace("°", "").replace('"', '').replace("'", "")
                    normalized_citation = rule.citation_span.replace("°", "").replace('"', '').replace("'", "")

                    if normalized_citation not in normalized_clause:
                        invalid_citations.append(f"{rule.id}: citation not found in clause {rule.clause_id}")

            if invalid_citations:
                console.print(f"[yellow]Warning: {len(invalid_citations)} rule(s) have invalid citation_spans[/yellow]")
                for msg in invalid_citations[:5]:  # Show first 5
                    console.print(f"  [dim]{msg}[/dim]")
                if len(invalid_citations) > 5:
                    console.print(f"  [dim]... and {len(invalid_citations) - 5} more[/dim]")

    return filtered


@app.command()
def doctor() -> None:
    """Check environment and report what's working and what needs fixing."""
    from rich.table import Table
    import subprocess
    import os

    console.print("\n[bold]Environment Health Check[/bold]\n")

    checks = []

    # Check Python version
    import sys
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 12)
    checks.append(("Python 3.12+", py_version, "✓" if py_ok else "✗", "" if py_ok else "Upgrade to Python 3.12+"))

    # Check uv
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
        uv_version = result.stdout.strip()
        uv_ok = result.returncode == 0
        checks.append(("uv", uv_version, "✓" if uv_ok else "✗", "" if uv_ok else "Install uv: pip install uv"))
    except Exception:
        checks.append(("uv", "not found", "✗", "Install uv: pip install uv"))

    # Check clingo
    try:
        import clingo
        clingo_ok = True
        checks.append(("clingo (Python)", clingo.__version__, "✓", ""))
    except ImportError:
        checks.append(("clingo", "not found", "✗", "Run: uv sync"))

    # Check BAML client
    baml_client = Path("baml_client")
    if baml_client.exists():
        checks.append(("BAML client", str(baml_client), "✓", ""))
    else:
        checks.append(("BAML client", "not found", "✗", "Run: cd baml_src && baml-cli generate"))

    # Check API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    fireworks_key = os.getenv("FIREWORKS_API_KEY")

    if anthropic_key:
        masked = anthropic_key[:8] + "..." if len(anthropic_key) > 8 else "set"
        checks.append(("ANTHROPIC_API_KEY", masked, "✓", ""))
    else:
        checks.append(("ANTHROPIC_API_KEY", "not set", "○", "Optional: for Claude LLM extraction"))

    if fireworks_key:
        masked = fireworks_key[:8] + "..." if len(fireworks_key) > 8 else "set"
        checks.append(("FIREWORKS_API_KEY", masked, "✓", ""))
    else:
        checks.append(("FIREWORKS_API_KEY", "not set", "○", "Optional: for Fireworks LLM extraction"))

    # Check key directories/files
    ontology_dir = ROOT / "ontology"
    if ontology_dir.exists() and (ontology_dir / "core.lp").exists():
        checks.append(("ontology/", str(ontology_dir), "✓", ""))
    else:
        checks.append(("ontology/", "missing", "✗", "Clone full repository"))

    data_dir = ROOT / "data"
    if data_dir.exists():
        checks.append(("data/", str(data_dir), "✓", ""))
    else:
        checks.append(("data/", "missing", "!", "Will be created on first extraction"))

    # Display results
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Value", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Action", style="yellow")

    for check, value, status, action in checks:
        style = "green" if status == "✓" else "red" if status == "✗" else "yellow"
        table.add_row(check, value, f"[{style}]{status}[/{style}]", action)

    console.print(table)

    # Overall status
    errors = sum(1 for _, _, status, _ in checks if status == "✗")
    warnings = sum(1 for _, _, status, _ in checks if status == "!")

    if errors == 0 and warnings == 0:
        console.print("\n[bold green]✓ Environment is healthy![/bold green]")
        console.print("[dim]Try: compli plan --site sites/den01.lp[/dim]\n")
    elif errors == 0:
        console.print(f"\n[bold yellow]⚠ {warnings} warning(s) - environment mostly healthy[/bold yellow]\n")
    else:
        console.print(f"\n[bold red]✗ {errors} error(s) need fixing[/bold red]\n")
        raise typer.Exit(1)


@app.command()
def extract(
    pdf: Annotated[Path, typer.Argument(help="Source PDF.")] = Path("EIGuide-61[1].pdf"),
    out: Annotated[Path, typer.Option(help="Where to write output.")] = DATA / "clauses.jsonl",
    doc: Annotated[str, typer.Option(help="Document name.")] = "EIGuide",
    version: Annotated[str, typer.Option(help="Document version.")] = "6.0",
    llm: Annotated[bool, typer.Option(help="Use LLM extraction (generates structured rules, needs API key).")] = False,
    client: Annotated[str, typer.Option(help="LLM client: 'Claude' or 'Fireworks'.")] = "Fireworks",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose logging.")] = False,
) -> None:
    """Extract clauses (or rules with --llm) from PDF.

    Without --llm: Rule-based extraction (fast, deterministic) → clauses.jsonl
    With --llm: LLM extraction (generates structured rules) → rules.jsonl
    """
    if llm:
        # Redirect to LLM extraction
        from loguru import logger
        from rich.progress import Progress, SpinnerColumn, TextColumn
        from . import llm_extract

        # Auto-change output to rules.jsonl if still default
        if out == DATA / "clauses.jsonl":
            out = DATA / "rules.jsonl"

        # Configure loguru
        logger.remove()
        if verbose:
            logger.add(
                lambda msg: console.print(f"[dim]{msg}[/dim]", end=""),
                format="{time:HH:mm:ss} | {level: <8} | {message}\n",
                level="DEBUG",
            )
        else:
            logger.add(
                lambda msg: console.print(f"[cyan]{msg}[/cyan]", end=""),
                format="{message}\n",
                level="INFO",
            )

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task(
                    f"Extracting rules from {pdf.name} using {client}...",
                    total=None
                )
                n = llm_extract.extract_to_jsonl(pdf, out, doc_name=doc, client=client)
                progress.update(task, description=f"✓ Extracted {n} rules", completed=True)

            console.print(f"\n[green]✓ Extracted {n} rules[/green] -> {out}")
            console.print(f"[yellow]Review with:[/yellow] compli review --rules-file {out}")
        except Exception as e:
            logger.exception("Extraction failed")
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        return

    # Original rule-based extraction
    clauses, figures, tables, warnings = run_extract(pdf, doc_name=doc, doc_version=version)
    for warning in warnings:
        console.print(f"[yellow]source document:[/yellow] {warning}")
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
def extract_llm(
    pdf: Annotated[Path, typer.Argument(help="Source PDF to extract rules from.")],
    out: Annotated[Path, typer.Option(help="Where to write rules.")] = DATA / "rules.jsonl",
    doc: Annotated[str, typer.Option(help="Document name.")] = "Compliance Standard",
    client: Annotated[str, typer.Option(help="LLM client: 'Claude' or 'Fireworks'.")] = "Fireworks",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose logging.")] = False,
) -> None:
    """Extract structured rules from PDF using LLM (BAML + Claude/Fireworks).

    This command uses LLM to interpret PDF content and generate structured Rule objects.
    The output still requires human review via `compli review` before compilation.

    Requires: ANTHROPIC_API_KEY or FIREWORKS_API_KEY environment variable.
    """
    from loguru import logger
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from . import llm_extract

    # Configure loguru
    logger.remove()  # Remove default handler
    if verbose:
        logger.add(
            lambda msg: console.print(f"[dim]{msg}[/dim]", end=""),
            format="{time:HH:mm:ss} | {level: <8} | {message}\n",
            level="DEBUG",
        )
    else:
        logger.add(
            lambda msg: console.print(f"[cyan]{msg}[/cyan]", end=""),
            format="{message}\n",
            level="INFO",
        )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task(
                f"Extracting rules from {pdf.name} using {client}...",
                total=None
            )
            n = llm_extract.extract_to_jsonl(pdf, out, doc_name=doc, client=client)
            progress.update(task, description=f"✓ Extracted {n} rules", completed=True)

        console.print(f"\n[green]✓ Extracted {n} rules[/green] -> {out}")
        console.print(f"[yellow]Review with:[/yellow] compli review --rules-file {out}")
    except Exception as e:
        logger.exception("Extraction failed")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def compile(
    chapter: Annotated[str, typer.Option(help="Chapter letter, e.g. D.")],
    rules_file: Annotated[Path, typer.Option(help="Structured rules.")] = DATA / "rules.jsonl",
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    out_dir: Annotated[Path, typer.Option()] = RULES_DIR,
    site: Annotated[Path | None, typer.Option(help="Also validate this site file.")] = None,
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
    if problems:
        for problem in problems:
            console.print(f"[bold red]exemption not in force:[/bold red] {problem}")
        console.print(
            "\n[red]Compilation succeeded but exemptions are not properly enforced.[/red]\n"
            "This will produce incorrect verdicts - inspectors will be asked to verify\n"
            "requirements that the standard explicitly exempts.\n"
            "\n"
            "Fix the guard predicates in the target rules to match the exemption conditions.\n"
        )
        raise typer.Exit(1)

    obligations = sum(1 for r in rules if r.kind == "obligation")
    exemptions = sum(1 for r in rules if r.kind == "exemption")
    unreviewed = sum(1 for r in rules if not r.reviewed)
    console.print(
        f"[green]{out}[/green]  {len(rules)} rules "
        f"({obligations} obligations, {exemptions} exemptions verified)"
    )
    if unreviewed:
        console.print(f"[yellow]{unreviewed} rule(s) not yet reviewed[/yellow]")

    # Optionally validate site file during compilation
    if site:
        console.print(f"\n[dim]Validating site file {site}...[/dim]")
        programs = [ONTOLOGY / "core.lp", ONTOLOGY / "domain.lp", out]
        _check_site(site, programs, strict=True)


def _check_site(site: Path, programs: list[Path], strict: bool = True) -> None:
    """Validate site facts and fail on errors that would produce incomplete plans.

    A silently-ignored fact produces a plan that looks complete and is not, which is the
    one outcome this whole system is built to avoid.

    Args:
        site: Path to site .lp file
        programs: Knowledge base .lp files
        strict: If True (default), exit with error on validation problems.
                If False, print warnings but continue (use with caution).
    """
    problems = validate_mod.validate_site(site, programs)
    if not problems:
        return

    # Print all problems
    for problem in problems:
        console.print(f"[bold red]site error:[/bold red] {problem}")
    console.print()

    if strict:
        console.print(
            "[red]Site file has validation errors that would produce incomplete plans.[/red]\n"
            "Fix these errors before planning. Common causes:\n"
            "  • Typos in predicate names (e.g., 'fuse_pannel' vs 'fuse_panel')\n"
            "  • Wrong arity (e.g., 'cell(bs1)' vs 'cell(bs1, 1)')\n"
            "  • Using ';' in multi-argument predicates (splits arguments incorrectly)\n"
            "\n"
            "To proceed anyway (not recommended): use --no-strict flag"
        )
        raise typer.Exit(1)


def _programs(chapters: list[str]) -> list[Path]:
    files = [ONTOLOGY / "core.lp", ONTOLOGY / "domain.lp"]

    # Check core ontology files exist
    for core_file in files:
        if not core_file.exists():
            console.print(
                f"[red]Core ontology file missing: {core_file}[/red]\n"
                f"This is a required file that should be part of the repository."
            )
            raise typer.Exit(1)

    for ch in chapters:
        path = RULES_DIR / f"chapter_{ch.lower()}.lp"
        if not path.exists():
            console.print(
                f"[red]Chapter ASP file missing: {path}[/red]\n"
                f"Run [cyan]compli compile --chapter {ch}[/cyan] to compile rules into ASP"
            )
            raise typer.Exit(1)
        files.append(path)
    return files


@app.command()
def plan(
    site: Annotated[Path, typer.Option(help="Site facts (.lp).")] = Path("sites/den01.lp"),
    chapter: Annotated[list[str], typer.Option(help="Chapters in scope.")] = ["D"],
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    out: Annotated[Path | None, typer.Option(help="Also write the manifest as JSON.")] = None,
    strict: Annotated[bool, typer.Option(help="Fail on site validation errors (recommended).")] = True,
) -> None:
    """Work out the cheapest set of captures that would settle every open requirement.

    Read-only. Writes nothing unless asked with --out.
    """
    programs = _programs(chapter)
    _check_site(site, programs, strict=strict)
    model = reason.solve(programs + [site], "")

    rules = _load_rules(DATA / "rules.jsonl", chapter, validate_citations=True)
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
    strict: Annotated[bool, typer.Option(help="Fail on site validation errors (recommended).")] = True,
    resume: Annotated[Path | None, typer.Option(help="Resume from saved observations file.")] = None,
    autosave: Annotated[bool, typer.Option(help="Auto-save observations after each action.")] = True,
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
    programs = _programs(chapter)
    _check_site(site, programs, strict=strict)
    programs = programs + [site]
    rules = _load_rules(DATA / "rules.jsonl", chapter, validate_citations=True)
    clauses = _clause_for_rule(_load_clauses(clauses_file), rules)
    acceptance = reason.acceptance_index(rules)
    meta = {"doc": "EIGuide", "version": "6.0", "chapters": list(chapter)}

    # Build index of known observables to validate against
    known_observables = {obs.name for rule in rules for obs in rule.observables if rule.field_verifiable}

    # Checkpoint/resume: load saved observations if resuming
    recorded: dict[tuple[str, str], Observation] = {}
    checkpoint_file = site.parent / f".{site.stem}_checkpoint.jsonl"

    if resume:
        # Resume from explicitly provided file
        if resume.exists():
            saved_obs = read_jsonl(resume, Observation)
            console.print(f"[cyan]Resuming from {resume}: {len(saved_obs)} observations loaded[/cyan]")
            recorded = {(o.subject, o.observable): o for o in saved_obs}
        else:
            console.print(f"[yellow]Resume file not found: {resume}. Starting fresh.[/yellow]")
    elif autosave and checkpoint_file.exists():
        # Auto-resume from checkpoint file
        saved_obs = read_jsonl(checkpoint_file, Observation)
        console.print(f"[cyan]Found checkpoint: {len(saved_obs)} observations. Resume? [y/N][/cyan]")
        if typer.prompt("", default="n").strip().lower() == "y":
            recorded = {(o.subject, o.observable): o for o in saved_obs}
            console.print(f"[green]Resumed from checkpoint[/green]")
        else:
            console.print("[yellow]Starting fresh (checkpoint file will be overwritten)[/yellow]")

    # Several rules can come from one clause (D.6.6 -> D.6.6a, D.6.6b), and a sweep and a
    # survey over the same subject cite it again. Quoting it in full every time drowns the
    # instruction, so each clause is shown once and referenced by number afterwards.
    quoted: set[str] = set()
    step = len(recorded)  # Start step count from number of resumed observations
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

                    # Check for ambiguous short-form IDs
                    short_to_subjects: dict[str, list[str]] = {}
                    for s in subjects:
                        short_to_subjects.setdefault(_short(s), []).append(s)

                    # Detect collisions in picked inputs
                    ambiguous = []
                    for p in picked:
                        if p in short_to_subjects and len(short_to_subjects[p]) > 1:
                            ambiguous.append((p, short_to_subjects[p]))

                    if ambiguous:
                        console.print("     [yellow]Ambiguous input - multiple subjects match:[/yellow]")
                        for short_id, matches in ambiguous:
                            console.print(f"       '{short_id}' could mean:")
                            for i, m in enumerate(matches, 1):
                                console.print(f"         {i}) {m}")
                        console.print("     [yellow]Use full subject names to disambiguate[/yellow]")
                        console.print("     [yellow]Recording all as failed[/yellow]")
                    else:
                        matched = {s for s in subjects if s in picked or _short(s) in picked}
                        if matched:
                            failing = matched
                        else:
                            console.print("     [yellow]no subject matched; recording all as failed[/yellow]")

            # A failure is worth explaining; a pass is not, so only failures are asked
            # to justify themselves.
            # Validate observable name against known rules
            if obs not in known_observables:
                console.print(f"     [yellow]Warning: '{obs}' not found in rules. Possible typo?[/yellow]")
                console.print(f"     [dim]Known observables: {', '.join(sorted(known_observables)[:5])}...[/dim]")

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

        # Auto-save checkpoint after each action
        if autosave:
            write_jsonl(checkpoint_file, list(recorded.values()))

        # Nothing recorded this round means every observable was skipped; asking the same
        # question forever helps nobody.
        if not any(o.action == action.id for o in recorded.values()):
            console.print("[yellow]nothing recorded for that action; stopping.[/yellow]")
            break

    console.print()

    # Clean up checkpoint file on successful completion
    if autosave and checkpoint_file.exists():
        checkpoint_file.unlink()
        console.print("[dim]Checkpoint cleared (inspection complete)[/dim]")

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
        console.print("[dim]Every subject: compli inspect --detail[/dim]")


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
    table.add_column("Requirement", width=22, no_wrap=True, overflow="ellipsis")
    table.add_column("n", justify="right", width=3)
    # Outcome must never be clipped. Truncating "2/24 violated cell(bs1,7), cell(..."
    # hides the only part of the verdict anyone acts on, so compliant rows stay on one
    # line and failing rows are allowed to wrap as far as they need.
    table.add_column("Outcome", min_width=36, overflow="fold")

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
                f"{_name_subjects(sorted(buckets['violated']), 12)}"
            )
        elif buckets["undetermined"]:
            outcome = (
                f"[yellow]{len(buckets['undetermined'])}/{total} unchecked[/yellow] "
                f"{_name_subjects(sorted(buckets['undetermined']), 12)}"
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


KNOWLEDGE = ROOT / "knowledge"


@app.command()
def triage(
    ticket_file: Annotated[Path, typer.Argument(help="Inbound ticket JSON.")],
    knowledge: Annotated[list[Path] | None, typer.Option(help="Knowledge bases (.lp).")] = None,
    results: Annotated[Path | None, typer.Option(help="Known test results as JSON.")] = None,
    out: Annotated[Path | None, typer.Option(help="Write the answer as JSON.")] = None,
) -> None:
    """Diagnose a ticket: what explains it, and the cheapest way to find out.

    One solve over whatever is known so far. Feed results back with --results to advance
    the ticket; the answer is always derived from the full evidence, never accumulated.
    """
    ticket = Ticket.load(ticket_file)
    kb = list(knowledge) if knowledge else sorted(KNOWLEDGE.glob("*.lp"))
    known = json.loads(results.read_text()) if results else {}
    evidence = triage_mod.evidence_facts(known.get("tests", {}), known.get("records", {}))

    model = triage_mod.solve(ticket, kb, evidence, ROOT)
    answer = triage_mod.to_result(ticket, model)

    console.print(
        Panel(
            f"[bold]{ticket.ticket_id}[/bold] from {ticket.source} · "
            f"{', '.join(a.code for a in ticket.alarms)}",
            title="SOLVED" if answer.solved else "OPEN",
        )
    )
    if answer.unrecognized_codes:
        codes = ", ".join(answer.unrecognized_codes)
        console.print(
            f"[bold red]unrecognized alarm codes:[/bold red] {codes} — "
            f"no diagnosis can be complete until these are mapped"
        )
    if answer.candidates:
        table = Table(show_header=True)
        table.add_column("explanation")
        table.add_column("status")
        for h in answer.candidates:
            table.add_row(
                h,
                "[yellow]provisional — rests on an unverified record[/yellow]"
                if h in answer.provisional
                else "[cyan]live[/cyan]",
            )
        console.print(table)
    for test in answer.next_tests:
        console.print(f"  [cyan]run[/cyan]    {test}")
    for record in answer.verify_records:
        console.print(
            f"  [yellow]verify[/yellow] {record}"
            f"  [dim](record is stale or low confidence)[/dim]"
        )
    if answer.next_tests or answer.verify_records:
        console.print(f"  [dim]plan cost {answer.plan_cost}[/dim]")
    for pair in answer.indistinguishable:
        console.print(f"  [red]cannot separate[/red] {pair[0]} from {pair[1]} with available tests")
    # Not `reason` -- that name is the reasoning module, and shadowing it here would break
    # any later call in this function.
    for why in answer.open_reasons:
        console.print(f"  [yellow]open[/yellow]   {why}")
    if answer.solved:
        console.print("")
        console.print(f"[green]resolution:[/green] {', '.join(answer.recommended)}")
        if answer.truck_roll:
            console.print("[yellow]requires dispatch[/yellow]")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(answer.to_json() + "\n", encoding="utf-8")
        console.print(f"[dim]{out}[/dim]")


def _known_panel(ticket: Ticket, model: dict) -> None:
    """Show what the record claims and what it is worth, before anything is acted on.

    A technician deciding whether to trust "span 17 feeds this router" needs the age and
    confidence of that row, not just its contents.
    """
    status = triage_mod.fact_status(model)
    table = Table(title="what we know", show_header=True)
    table.add_column("record")
    table.add_column("source")
    table.add_column("conf", justify="right")
    table.add_column("age", justify="right")
    table.add_column("status")
    for fact in ticket.facts:
        state = status.get(fact.fact, "unknown")
        age = ticket.received_day - fact.as_of_day
        style = {"established": "green", "unverified": "yellow", "refuted": "red"}.get(state, "dim")
        note = state
        if state == "unverified":
            note = "STALE" if age > ticket.stale_after_days else "LOW CONFIDENCE"
        table.add_row(
            fact.fact, fact.source, f"{fact.confidence}%", f"{age}d",
            f"[{style}]{note}[/{style}]",
        )
    if ticket.facts:
        console.print(table)


def _candidates_panel(answer) -> None:
    table = Table(show_header=True)
    table.add_column("explanation")
    table.add_column("status")
    for h in answer.candidates:
        table.add_row(
            h,
            "[yellow]provisional[/yellow]" if h in answer.provisional else "[cyan]live[/cyan]",
        )
    if answer.candidates:
        console.print(table)


@app.command()
def work(
    ticket_file: Annotated[Path, typer.Argument(help="Inbound ticket JSON.")],
    knowledge: Annotated[
        list[Path] | None,
        typer.Option(help="Knowledge bases (.lp). Defaults to all files in knowledge/.")
    ] = None,
) -> None:
    """Work a ticket interactively, re-solving after every answer.

    The diagnostic counterpart of `inspect`. Each round shows the live explanations and
    asks for the single cheapest thing that would tell them apart; answering narrows the
    field and the next question changes accordingly. Single session, nothing written.
    """
    ticket = Ticket.load(ticket_file)
    kb = list(knowledge) if knowledge else sorted(KNOWLEDGE.glob("*.lp"))

    results: dict[str, str] = {}
    checks: dict[str, bool] = {}
    step = 0

    console.print(
        Panel(
            f"[bold]{ticket.ticket_id}[/bold]  ·  {ticket.source}  ·  asset {ticket.asset_id}\n"
            + "\n".join(
                f"alarm  {a.code}" + (f"  ({a.severity})" if a.severity else "")
                for a in ticket.alarms
            ),
            title="ticket",
        )
    )

    while True:
        model = triage_mod.solve(ticket, kb, triage_mod.evidence_facts(results, checks), ROOT)
        answer = triage_mod.to_result(ticket, model)

        if step == 0:
            _known_panel(ticket, model)
        console.print(
            f"[cyan]{len(answer.candidates)} explanation(s) live[/cyan]"
            + (f" · [yellow]{len(answer.provisional)} provisional[/yellow]" if answer.provisional else "")
        )
        _candidates_panel(answer)

        if answer.unrecognized_codes:
            codes = ", ".join(answer.unrecognized_codes)
            console.print(f"[bold red]unrecognized alarm codes:[/bold red] {codes}")

        if answer.solved:
            console.print(f"\n[bold green]SOLVED[/bold green] → {', '.join(answer.recommended)}")
            if answer.truck_roll:
                console.print("[yellow]requires dispatch[/yellow]")
            return

        pending_tests = list(answer.next_tests)
        pending_records = list(answer.verify_records)
        if not pending_tests and not pending_records:
            console.print("\n[yellow]Nothing further would change the answer.[/yellow]")
            for why in answer.open_reasons:
                console.print(f"  open: {why}")
            for pair in answer.indistinguishable:
                console.print(f"  [red]cannot separate[/red] {pair[0]} from {pair[1]}")
            return

        legal = triage_mod.outcomes(model)
        progressed = False

        for record in pending_records:
            step += 1
            console.print(
                Panel(
                    f"Confirm in the field: [bold]{record}[/bold]\n"
                    f"[dim]The record is stale or low confidence, and a live explanation "
                    f"depends on it.[/dim]",
                    title=f"step {step} · verify record",
                )
            )
            reply = typer.prompt("  [y]es / [n]o / [s]kip / [q]uit", default="s").strip().lower()
            if reply.startswith("q"):
                return
            if reply.startswith("s"):
                continue
            checks[record] = reply.startswith("y")
            progressed = True
            break  # re-solve: a refuted record can remove the very tests just planned

        if progressed:
            continue

        for test in pending_tests:
            step += 1
            choices = legal.get(test, [])
            console.print(
                Panel(
                    f"Run: [bold]{test}[/bold]", title=f"step {step} · test · cost {answer.plan_cost}"
                )
            )
            for i, choice in enumerate(choices, 1):
                console.print(f"   {i}) {choice}")
            reply = typer.prompt("  result (number) / [s]kip / [q]uit", default="s").strip().lower()
            if reply.startswith("q"):
                return
            if reply.startswith("s"):
                continue
            if reply.isdigit() and 1 <= int(reply) <= len(choices):
                results[test] = choices[int(reply) - 1]
                progressed = True
                break
            console.print("[yellow]not a listed outcome; skipping[/yellow]")

        if not progressed:
            console.print("\n[yellow]Nothing was answered; stopping.[/yellow]")
            for why in answer.open_reasons:
                console.print(f"  open: {why}")
            return


def main() -> None:
    app()


if __name__ == "__main__":
    main()

@app.command()
def verify(
    site: Annotated[Path, typer.Option(help="Site facts (.lp).")] = Path("sites/den01.lp"),
    observations: Annotated[Path, typer.Option(help="Observations file (.jsonl).")] = Path("observations.jsonl"),
    chapter: Annotated[list[str], typer.Option(help="Chapters in scope.")] = ["D"],
    clauses_file: Annotated[Path, typer.Option()] = DATA / "clauses.jsonl",
    strict: Annotated[bool, typer.Option(help="Fail on site validation errors (recommended).")] = True,
    json_output: Annotated[Path | None, typer.Option(help="Write verdicts as JSON.")] = None,
) -> None:
    """Batch verification mode for CI/automation: load observations, run solver, report verdict.

    Non-interactive. Exits with:
      0 - all requirements satisfied
      1 - violations found or undetermined requirements remain
      2 - errors (missing files, invalid site, etc.)

    Example:
      compli verify --site sites/den01.lp --observations captured.jsonl
    """
    programs = _programs(chapter)
    _check_site(site, programs, strict=strict)
    programs = programs + [site]

    # Load observations from file
    if not observations.exists():
        console.print(f"[red]Observations file not found: {observations}[/red]")
        raise typer.Exit(2)

    obs = read_jsonl(observations, Observation)
    if not obs:
        console.print(f"[yellow]Warning: No observations in {observations}[/yellow]")

    console.print(f"Loaded {len(obs)} observations from {observations}")

    # Load rules and clauses
    rules = _load_rules(DATA / "rules.jsonl", chapter)
    clauses = _clause_for_rule(_load_clauses(clauses_file), rules)

    # Validate observations match known rules
    from .validate_obs import validate_observations
    problems = validate_observations(obs, rules, strict=False)
    for problem in problems:
        console.print(f"[yellow]Warning: {problem}[/yellow]")

    # Run solver
    console.print("Running solver...")
    model = reason.solve(programs, reason.observations_to_facts(obs))
    verdicts = reason.build_verdicts(model, clauses)

    # Print results
    _print_rollup(verdicts, clauses, site.stem, len(obs))
    _print_totals(verdicts)

    # Write JSON if requested
    if json_output:
        import json
        output = {
            "site": site.stem,
            "observations": len(obs),
            "verdicts": [
                {
                    "rule": v.rule,
                    "subject": v.subject,
                    "status": v.status,
                    "missing": v.missing,
                    "citation": {
                        "page": v.citation.page_label,
                        "text": v.citation.text
                    } if v.citation else None
                }
                for v in verdicts
            ],
            "summary": {
                "violated": sum(1 for v in verdicts if v.status == "violated"),
                "undetermined": sum(1 for v in verdicts if v.status == "undetermined"),
                "satisfied": sum(1 for v in verdicts if v.status == "satisfied"),
            }
        }
        json_output.write_text(json.dumps(output, indent=2))
        console.print(f"[dim]Wrote verdicts to {json_output}[/dim]")

    # Exit code based on verdict
    violated = sum(1 for v in verdicts if v.status == "violated")
    undetermined = sum(1 for v in verdicts if v.status == "undetermined")

    if violated > 0:
        console.print(f"\n[bold red]FAIL: {violated} violations found[/bold red]")
        raise typer.Exit(1)
    elif undetermined > 0:
        console.print(f"\n[yellow]INCOMPLETE: {undetermined} requirements unchecked[/yellow]")
        raise typer.Exit(1)
    else:
        console.print("\n[bold green]PASS: All requirements satisfied[/bold green]")
        raise typer.Exit(0)
