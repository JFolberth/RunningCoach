"""CLI entry point for the Fitbit Race Training Tool."""

import argparse
import sys

from rich.console import Console

console = Console()


def cmd_setup(args):
    """Interactive race goal configuration."""
    import json
    import os
    from datetime import datetime, timedelta
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from config import RACE_CONFIG_FILE, _try_load_race_config

    existing = _try_load_race_config()
    if existing:
        console.print(Panel(
            f"[bold]{existing['race_name']}[/bold]\n"
            f"Date: {existing['race_date']}\n"
            f"Distance: {existing['race_distance_miles']} miles\n"
            f"Target time: {existing.get('target_time') or 'None (completion only)'}",
            title="Current Race Configuration",
        ))
        if not Confirm.ask("Overwrite existing configuration?", default=False):
            console.print("[yellow]Setup cancelled.[/yellow]")
            return

    console.print("\n[bold blue]🏃 Race Goal Setup[/bold blue]")
    console.print("━" * 40)

    race_name = Prompt.ask("What is the name of your race?")

    while True:
        race_date = Prompt.ask("What is the race date? (YYYY-MM-DD)")
        try:
            datetime.strptime(race_date, "%Y-%m-%d")
            break
        except ValueError:
            console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")

    while True:
        distance_str = Prompt.ask("What is the race distance in miles?")
        try:
            race_distance = float(distance_str)
            if race_distance <= 0:
                raise ValueError
            break
        except ValueError:
            console.print("[red]Enter a positive number (e.g., 13.1, 26.2, 3.1).[/red]")

    target_time = Prompt.ask(
        "What is your target completion time? (HH:MM:SS or press Enter to skip)",
        default="",
    )
    if target_time.strip() == "":
        target_time = None

    training_start = Prompt.ask(
        "When did you start training? (YYYY-MM-DD or press Enter for auto-calculate)",
        default="",
    )
    if training_start.strip() == "":
        race_dt = datetime.strptime(race_date, "%Y-%m-%d")
        start_dt = race_dt - timedelta(weeks=20)
        training_start = start_dt.strftime("%Y-%m-%d")
        console.print(f"  [dim]Auto-calculated: {training_start} (20 weeks before race)[/dim]")
    else:
        try:
            datetime.strptime(training_start, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Invalid date. Using auto-calculate.[/red]")
            race_dt = datetime.strptime(race_date, "%Y-%m-%d")
            start_dt = race_dt - timedelta(weeks=20)
            training_start = start_dt.strftime("%Y-%m-%d")

    config = {
        "race_name": race_name,
        "race_date": race_date,
        "race_distance_miles": race_distance,
        "target_time": target_time,
        "data_start_date": training_start,
    }

    with open(RACE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    console.print(f"\n[green bold]✅ Configuration saved to race_config.json[/green bold]")
    console.print(Panel(
        f"[bold]{race_name}[/bold]\n"
        f"Date: {race_date}\n"
        f"Distance: {race_distance} miles\n"
        f"Target time: {target_time or 'None (completion only)'}\n"
        f"Training start: {training_start}",
        title="Your Race Goal",
    ))


def cmd_auth(args):
    """Run OAuth 2.0 authorization flow."""
    from core.auth import authorize
    authorize()


def cmd_assess(args):
    """Fetch Fitbit data and display fitness assessment."""
    from config import require_race_config, DATA_START_DATE
    require_race_config()
    from core.data_fetcher import fetch_all_data
    from analysis.analyzer import analyze
    from output.report_generator import display_assessment

    console.print(f"[bold]Fetching your Fitbit data (from {DATA_START_DATE})...[/bold]\n")
    data = fetch_all_data()
    analysis = analyze(data)
    display_assessment(analysis)


def cmd_plan(args):
    """Generate and display personalized training plan."""
    from config import require_race_config, DATA_START_DATE
    require_race_config()
    from core.data_fetcher import fetch_all_data
    from analysis.analyzer import analyze
    from analysis.training_plan import generate_plan
    from output.report_generator import display_plan

    console.print(f"[bold]Fetching your Fitbit data (from {DATA_START_DATE})...[/bold]\n")
    data = fetch_all_data()
    analysis = analyze(data)
    plan = generate_plan(analysis)
    display_plan(plan)


def cmd_progress(args):
    """Show weekly progress summary."""
    from config import require_race_config
    require_race_config()
    from core.data_fetcher import fetch_all_data
    from analysis.analyzer import analyze
    from output.report_generator import display_assessment

    console.print("[bold]Fetching recent data for progress check...[/bold]\n")
    data = fetch_all_data()
    analysis = analyze(data)
    display_assessment(analysis)


def cmd_report(args):
    """Generate and save full report."""
    from config import require_race_config, DATA_START_DATE
    require_race_config()
    from core.data_fetcher import fetch_all_data
    from analysis.analyzer import analyze
    from analysis.training_plan import generate_plan
    from output.report_generator import (
        display_assessment, display_plan,
        save_assessment_report, save_training_plan_report,
    )

    console.print(f"[bold]Fetching your Fitbit data (from {DATA_START_DATE})...[/bold]\n")
    data = fetch_all_data()
    analysis = analyze(data)
    plan = generate_plan(analysis)

    display_assessment(analysis)
    display_plan(plan)

    console.print("\n[bold]Saving reports...[/bold]")
    save_assessment_report(analysis)
    save_training_plan_report(plan)
    console.print("\n[green bold]✅ All reports saved to reports/ directory[/green bold]")


def cmd_calendar(args):
    """Show calendar view of all workouts."""
    from config import require_race_config, DATA_START_DATE
    require_race_config()
    from core.data_fetcher import fetch_all_data
    from output.calendar_view import display_calendar

    console.print(f"[bold]Fetching your Fitbit data (from {DATA_START_DATE})...[/bold]\n")
    data = fetch_all_data()
    display_calendar(data.get("activities", []))


def cmd_dashboard(args):
    """Generate interactive HTML dashboard with charts."""
    from config import require_race_config
    require_race_config()
    from output.dashboard import generate_dashboard

    console.print("[bold]Generating dashboard from cached data...[/bold]\n")
    generate_dashboard()


def main():
    parser = argparse.ArgumentParser(
        description="🏃 Fitbit Race Training Tool — Track your training and race readiness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    setup_parser = subparsers.add_parser("setup", help="Configure your race goal")
    setup_parser.set_defaults(func=cmd_setup)

    # auth
    auth_parser = subparsers.add_parser("auth", help="Authorize with Fitbit (OAuth 2.0)")
    auth_parser.set_defaults(func=cmd_auth)

    # assess
    assess_parser = subparsers.add_parser("assess", help="Fetch data & show fitness assessment")
    assess_parser.set_defaults(func=cmd_assess)

    # plan
    plan_parser = subparsers.add_parser("plan", help="Generate training plan")
    plan_parser.set_defaults(func=cmd_plan)

    # progress
    progress_parser = subparsers.add_parser("progress", help="Show recent progress")
    progress_parser.set_defaults(func=cmd_progress)

    # report
    report_parser = subparsers.add_parser("report", help="Generate & save full report")
    report_parser.set_defaults(func=cmd_report)

    # calendar
    calendar_parser = subparsers.add_parser("calendar", help="Show workout calendar")
    calendar_parser.set_defaults(func=cmd_calendar)

    # dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Open interactive chart dashboard")
    dashboard_parser.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red bold]Error:[/red bold] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
