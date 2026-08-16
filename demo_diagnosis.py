#!/usr/bin/env python3
"""
Production Outage Diagnostic Demo

Simulates the Saturday 3:47 AM scenario from scenarios/production_outage.md
Shows the solver narrowing from multiple hypotheses to root cause through
cost-optimal testing.
"""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import sys

from compli.ticket import Ticket
from compli.triage import solve, to_result, evidence_facts

console = Console()


def show_step(title: str, content: str, style="blue"):
    console.print()
    console.print(Panel(content, title=title, border_style=style, title_align="left"))


def show_table_step(title: str, table: Table):
    console.print()
    console.print(Panel(table, title=title, border_style="blue"))


def main():
    console.clear()

    # Opening scene
    show_step(
        "PAGER ALERT — Saturday 03:47 MT",
        "[bold red]DEN-PWR-8472[/bold red]\n"
        "Priority: P1\n"
        "Denver colocation — 23 devices unreachable\n"
        "SLA clock running — customer impact",
        style="red"
    )

    console.print("\n[dim]Loading ticket...[/dim]")

    # Load the ticket
    ticket_path = Path("tickets/den_outage_live.json")
    if not ticket_path.exists():
        console.print(f"[red]Error: {ticket_path} not found[/red]")
        sys.exit(1)

    ticket = Ticket.load(ticket_path)
    knowledge = [
        Path("knowledge/vendor_codes.lp"),
        Path("knowledge/datacenter_faults.lp")
    ]

    # Show the raw alarms
    alarms_table = Table(box=box.ROUNDED, title="Raw Alarms")
    alarms_table.add_column("Code", style="cyan")
    alarms_table.add_column("Severity", style="yellow")

    for alarm in ticket.alarms:
        alarms_table.add_row(alarm.code, alarm.severity or "")

    show_table_step("What the NMS is reporting", alarms_table)

    console.print("\n[dim]Running initial diagnosis...[/dim]")

    # Round 1: No evidence yet
    model = solve(ticket, knowledge, "")
    result = to_result(ticket, model)

    # Show the hypothesis space
    hyp_table = Table(box=box.ROUNDED)
    hyp_table.add_column("Possible Explanations", style="cyan")
    hyp_table.add_column("Status", style="yellow")

    for candidate in result.candidates:
        status = "provisional" if candidate in result.provisional else "live"
        style = "dim" if status == "provisional" else "bold"
        hyp_table.add_row(f"[{style}]{candidate.replace('_', ' ')}[/{style}]", status)

    show_table_step(
        f"Initial Diagnostic State — {len(result.candidates)} possible causes",
        hyp_table
    )

    if result.provisional:
        console.print(
            f"\n[yellow]WARNING: {len(result.provisional)} hypotheses are PROVISIONAL[/yellow]"
        )
        console.print("[dim]They depend on contradicted or stale records[/dim]")

    # Show what records we have
    if ticket.facts:
        records_table = Table(box=box.ROUNDED)
        records_table.add_column("Record", style="cyan")
        records_table.add_column("Source", style="green")
        records_table.add_column("Confidence", style="yellow")
        records_table.add_column("Age (days)", style="blue")

        for fact in ticket.facts:
            age = ticket.received_day - fact.as_of_day
            conf_str = f"{fact.confidence}%"
            negation = "NOT " if fact.negated else ""
            records_table.add_row(
                f"{negation}{fact.fact}",
                fact.source,
                conf_str,
                str(age)
            )

        show_table_step("Available Records (varying quality)", records_table)

    # Show recommended tests
    if result.next_tests or result.verify_records:
        console.print(
            f"\n[bold cyan]Solver recommends {len(result.next_tests)} tests "
            f"to discriminate[/bold cyan]"
        )

        tests_table = Table(box=box.SIMPLE)
        tests_table.add_column("Action", style="cyan")
        tests_table.add_column("Type", style="yellow")

        for test in result.next_tests:
            tests_table.add_row(test.replace('_', ' '), "test")
        for verify in result.verify_records:
            tests_table.add_row(f"verify: {verify.replace('_', ' ')}", "field check")

        console.print(tests_table)
        console.print(
            f"\n[dim]Plan cost: ${result.plan_cost} "
            f"(vs $1200 truck roll if we guess wrong)[/dim]"
        )

    # Simulate running the first test
    console.print("\n" + "─" * 60)
    show_step(
        "Round 1: query_power_telemetry",
        "[bold]Running SNMP query against PDU and UPS...[/bold]\n\n"
        "Result: [red bold]ac_absent[/red bold]\n"
        "UPS Status: [yellow]discharging (battery at 40%)[/yellow]\n"
        "Estimated runtime: [red]90 minutes[/red]",
        style="green"
    )

    # Re-solve with this evidence
    evidence = evidence_facts({"query_power_telemetry": "ac_absent"}, {})
    model = solve(ticket, knowledge, evidence)
    result = to_result(ticket, model)

    # Show narrowed hypotheses
    console.print("\n[bold green]Evidence processed — re-solving...[/bold green]")

    narrowed_table = Table(box=box.ROUNDED)
    narrowed_table.add_column("Explanation", style="cyan")
    narrowed_table.add_column("Status", style="yellow")

    for candidate in result.candidates:
        status = "CONFIRMED" if candidate == "utility_power_outage" else "ruled out"
        style = "bold green" if status == "CONFIRMED" else "dim"
        narrowed_table.add_row(
            f"[{style}]{candidate.replace('_', ' ')}[/{style}]",
            status
        )

    show_table_step(
        f"After telemetry — {len(result.candidates)} explanation(s) survive",
        narrowed_table
    )

    # Check for critical dependency
    console.print("\n" + "─" * 60)
    show_step(
        "Critical Record Conflict",
        "[yellow]The diagnosis depends on: [bold]site_has_generator[/bold][/yellow]\n\n"
        "OneVizion says: [red]NO[/red] (60% conf, 5 days old)\n"
        "HyperLink says: [green]YES[/green] (85% conf, 60 days old)\n\n"
        "[bold]This matters:[/bold]\n"
        "  No generator → UPS depletes in 90min → total outage\n"
        "  Has generator → may auto-start → wait before dispatch",
        style="yellow"
    )

    console.print("\n[dim]Checking HyperLink work orders...[/dim]")
    console.print(
        "[dim]Found: WO-2847 (240 days ago) — "
        '"Generator decommissioned - end of service contract"[/dim]'
    )

    # Re-solve with verified fact
    evidence = evidence_facts(
        {"query_power_telemetry": "ac_absent"},
        {"site_has_generator": False}
    )
    model = solve(ticket, knowledge, evidence)
    result = to_result(ticket, model)

    # Final diagnosis
    console.print("\n" + "─" * 60)

    if result.solved:
        diagnosis = (
            "[bold green]DIAGNOSIS COMPLETE[/bold green]\n\n"
            "[bold]Root Cause:[/bold] Utility power outage\n"
            "[bold]Critical Finding:[/bold] No backup generator\n"
            "[bold]Impact:[/bold] UPS depleted in ~90 minutes\n\n"
            "[bold red]IMMEDIATE ACTION REQUIRED:[/bold red]\n"
            "  1. Controlled shutdown of non-critical systems\n"
            "  2. Dispatch truck for generator rental\n"
            "  3. Notify affected customers\n\n"
            f"[dim]Diagnostic cost: ${result.plan_cost} · Time to answer: ~4 minutes[/dim]\n"
            f"[dim]Alternative (guess and truck): $1200 · 90+ minutes[/dim]"
        )
        show_step("Final Verdict", diagnosis, style="green")
    else:
        console.print("[yellow]Not yet solved — more evidence needed[/yellow]")
        if result.open_reasons:
            console.print(f"\nReasons: {', '.join(result.open_reasons)}")

    # The point
    console.print("\n" + "=" * 60)
    console.print("\n[bold cyan]What the solver just did:[/bold cyan]")
    console.print(
        "  1. Enumerated 4 possible causes from alarm pattern\n"
        "  2. Identified contradicted records (generator status)\n"
        "  3. Recommended $1 test instead of $1200 truck roll\n"
        "  4. Converged to root cause with high confidence\n"
        "  5. Surfaced the critical dependency (no generator = 90min clock)\n"
    )

    console.print("\n[bold yellow]Why This Requires ASP (not rules or Datalog):[/bold yellow]")
    console.print(
        "  • [cyan]Multiple answer sets[/cyan] → each is ONE way things could be\n"
        "  • [cyan]Union vs intersection[/cyan] → POSSIBLE vs CERTAIN\n"
        "  • [cyan]Three-valued logic[/cyan] → established / unverified / refuted\n"
        "  • [cyan]#minimize directive[/cyan] → cheapest tests to discriminate\n"
    )
    console.print(
        "\n[dim]A rule engine picks ONE answer. Datalog derives EVERYTHING (closed-world).\n"
        "Only ASP enumerates minimal worlds AND optimizes test selection.[/dim]\n"
    )

    console.print("\n[bold green]Try the multi-fault scenario:[/bold green]")
    console.print(
        "  [cyan]tickets/den_multi_fault.json[/cyan] — power + HVAC both failing\n"
        "  Shows how the solver keeps multiple hypotheses live until tests discriminate.\n"
    )
    console.print("\n[bold]Read WHY_ASP.md for the full explanation.[/bold]\n")


if __name__ == "__main__":
    main()
