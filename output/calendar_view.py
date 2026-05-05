"""Calendar view of all workouts from Fitbit data."""

import calendar
from collections import defaultdict
from datetime import date, datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import DATA_START_DATE
from utils import KM_TO_MILES

console = Console()


def display_calendar(activities: list):
    """Display a month-by-month calendar of all workouts.

    Args:
        activities: List of raw Fitbit activity dicts from cache.
    """
    # Parse activities into day-keyed dict
    day_data = defaultdict(list)
    for act in activities:
        name = act.get("activityName", "").lower()
        start_time = act.get("originalStartTime") or act.get("startTime", "")
        act_date = start_time[:10] if start_time else ""
        if not act_date:
            continue

        distance = act.get("distance", 0)
        distance_unit = act.get("distanceUnit", "")
        if "kilometer" in distance_unit.lower() or "km" in distance_unit.lower():
            distance = distance * KM_TO_MILES

        duration_min = act.get("duration", 0) / 60000
        calories = act.get("calories", 0)
        avg_hr = act.get("averageHeartRate", 0)

        if "run" in name or "jog" in name or "treadmill" in name:
            day_data[act_date].append({
                "type": "run",
                "distance_mi": round(distance, 1),
                "duration_min": round(duration_min),
                "calories": calories,
                "hr": avg_hr,
            })
        elif duration_min >= 5:
            day_data[act_date].append({
                "type": "cross",
                "name": act.get("activityName", "Activity"),
                "duration_min": round(duration_min),
                "calories": calories,
                "hr": avg_hr,
            })

    if not day_data:
        console.print("[yellow]No activities found in cache.[/yellow]")
        return

    # Determine date range
    start = datetime.strptime(DATA_START_DATE, "%Y-%m-%d").date()
    end = date.today()

    console.print()
    console.rule("[bold blue]📅 Activity Calendar[/bold blue]")
    console.print()

    # Stats accumulators
    total_runs = 0
    total_run_miles = 0.0
    total_cross = 0
    total_cross_min = 0

    # Iterate month by month
    current = date(start.year, start.month, 1)
    while current <= end:
        year, month = current.year, current.month
        month_name = calendar.month_name[month]

        # Build calendar grid
        cal = calendar.Calendar(firstweekday=0)  # Monday start
        weeks = cal.monthdayscalendar(year, month)

        table = Table(
            title=f"[bold]{month_name} {year}[/bold]",
            box=box.ROUNDED,
            show_lines=True,
            padding=(0, 1),
        )
        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            table.add_column(day_name, justify="center", width=14, no_wrap=False)

        month_runs = 0
        month_miles = 0.0
        month_cross = 0

        for week in weeks:
            cells = []
            for day_num in week:
                if day_num == 0:
                    cells.append("")
                    continue

                day_str = f"{year}-{month:02d}-{day_num:02d}"
                d = date(year, month, day_num)

                if d < start or d > end:
                    cells.append(f"[dim]{day_num}[/dim]")
                    continue

                entries = day_data.get(day_str, [])
                if not entries:
                    cells.append(f"[dim]{day_num} ·[/dim]")
                    continue

                parts = [str(day_num)]
                for e in entries:
                    if e["type"] == "run":
                        parts.append(f"[green]🏃 {e['distance_mi']}mi[/green]")
                        month_runs += 1
                        month_miles += e["distance_mi"]
                        total_runs += 1
                        total_run_miles += e["distance_mi"]
                    elif e["type"] == "cross":
                        parts.append(f"[blue]🏋️ {e['duration_min']}m[/blue]")
                        month_cross += 1
                        total_cross += 1
                        total_cross_min += e["duration_min"]

                cells.append("\n".join(parts))

            table.add_row(*cells)

        console.print(table)

        # Month summary
        summary_parts = []
        if month_runs > 0:
            summary_parts.append(f"🏃 {month_runs} runs ({month_miles:.1f} mi)")
        if month_cross > 0:
            summary_parts.append(f"🏋️ {month_cross} cross-training")
        if summary_parts:
            console.print(f"  {' | '.join(summary_parts)}")
        console.print()

        # Next month
        if month == 12:
            current = date(year + 1, 1, 1)
        else:
            current = date(year, month + 1, 1)

    # Overall summary
    console.print(Panel(
        f"🏃 Total runs: {total_runs} ({total_run_miles:.1f} mi)\n"
        f"🏋️ Total cross-training: {total_cross} sessions ({total_cross_min} min)\n"
        f"📅 Training period: {DATA_START_DATE} to {date.today().isoformat()}",
        title="[bold]📊 Training Summary[/bold]",
        border_style="green",
    ))
    console.print()

