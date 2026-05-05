"""Formats and displays fitness data and training plans for CLI and saved reports."""

import os
from datetime import date

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from rich import box

from config import RACE_NAME, RACE_DATE, RACE_DISTANCE_MILES

console = Console()
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")


def display_assessment(analysis: dict):
    """Display fitness assessment in the terminal using rich."""
    console.print()
    console.rule("[bold blue]🏃 Fitness Assessment for Half Marathon[/bold blue]")
    console.print()

    _display_profile(analysis.get("profile", {}))
    _display_body(analysis.get("body", {}))
    _display_running(analysis.get("running", {}))
    _display_cross_training(analysis.get("cross_training", {}))
    _display_heart_rate(analysis.get("heart_rate", {}))
    _display_vo2_max(analysis.get("vo2_max", {}))
    _display_sleep(analysis.get("sleep", {}))
    _display_hydration(analysis.get("hydration", {}))
    _display_daily_activity(analysis.get("daily_activity", {}))
    _display_spo2(analysis.get("spo2", {}))
    _display_weekly_calories(analysis.get("weekly_calories", {}))
    _display_readiness(analysis.get("readiness", {}))
    _display_run_weather(analysis.get("running", {}))


def _display_profile(profile: dict):
    table = Table(title="👤 Profile", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Name", str(profile.get("name", "N/A")))
    table.add_row("Age", str(profile.get("age", "N/A")))
    table.add_row("Height", f"{profile.get('height_in', 0)}\" ({profile.get('height_cm', 0)} cm)")
    table.add_row("Weight", f"{profile.get('weight_lbs', 0)} lbs ({profile.get('weight_kg', 0)} kg)")
    table.add_row("BMI", str(profile.get("bmi", "N/A")))
    console.print(table)
    console.print()


def _display_body(body: dict):
    if body.get("weight_entries", 0) == 0:
        return
    table = Table(title="⚖️  Body Metrics", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    if body.get("current_weight_lbs"):
        table.add_row("Current Weight", f"{body['current_weight_lbs']} lbs")
    table.add_row("Weight Trend", body.get("weight_trend", "N/A"))
    if body.get("weight_change_kg") is not None:
        lbs = round(body["weight_change_kg"] * 2.205, 1)
        table.add_row("Weight Change", f"{lbs:+.1f} lbs ({body['weight_change_kg']:+.2f} kg)")
    if body.get("avg_body_fat"):
        table.add_row("Avg Body Fat", f"{body['avg_body_fat']}%")
    console.print(table)
    console.print()


def _display_running(running: dict):
    table = Table(title="🏃 Running Summary", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Total Runs", str(running.get("total_runs", 0)))
    table.add_row("Total Distance", f"{running.get('total_distance_mi', 0)} mi")
    table.add_row("Avg Weekly Mileage", f"{running.get('avg_weekly_mileage', 0)} mi")
    table.add_row("Avg Run Distance", f"{running.get('avg_run_distance_mi', 0)} mi")
    table.add_row("Longest Run", f"{running.get('longest_run_mi', 0)} mi")

    pace = running.get("avg_pace_per_mile", 0)
    if pace > 0:
        mins = int(pace)
        secs = int((pace - mins) * 60)
        table.add_row("Avg Pace", f"{mins}:{secs:02d}/mi")

    console.print(table)
    console.print()


def _display_run_weather(running: dict):
    """Display weather conditions for outdoor runs."""
    from core.weather import weather_icon

    runs = running.get("runs", [])
    outdoor_with_weather = [r for r in runs if r.get("weather")]
    if not outdoor_with_weather:
        return

    # Per-run weather table
    table = Table(title="🌤️ Outdoor Run Weather", box=box.ROUNDED)
    table.add_column("Date", style="cyan")
    table.add_column("Distance", style="white", justify="right")
    table.add_column("Pace", style="white", justify="right")
    table.add_column("Temp", style="yellow", justify="right")
    table.add_column("Weather", justify="center")
    table.add_column("Location", style="dim")

    for r in sorted(outdoor_with_weather, key=lambda x: x.get("date", "")):
        w = r["weather"]
        pace = r.get("pace_per_mile", 0)
        pace_str = ""
        if pace > 0:
            mins = int(pace)
            secs = int((pace - mins) * 60)
            pace_str = f"{mins}:{secs:02d}/mi"

        temp_str = f"{w['temp_f']:.0f}°F" if w.get("temp_f") is not None else "N/A"
        icon = weather_icon(w.get("sky", ""), w.get("precip") if w.get("precip") != "None" else None)
        # Build tooltip-style description
        desc_parts = [w.get("sky", "")]
        if w.get("precip") and w["precip"] != "None":
            desc_parts.append(w["precip"])
        weather_str = f"{icon} {', '.join(desc_parts)}"
        location = w.get("location", "") or ""

        table.add_row(
            r.get("date", ""),
            f"{r.get('distance_mi', 0):.1f} mi",
            pace_str,
            temp_str,
            weather_str,
            location,
        )

    console.print(table)

    # Weather summary
    ws = running.get("weather_summary")
    if ws:
        summary = Table(title="📊 Weather Summary", box=box.ROUNDED, show_header=False)
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="white")
        summary.add_row("Runs with Weather", str(ws.get("runs_with_weather", 0)))
        if ws.get("avg_temp_f") is not None:
            summary.add_row("Avg Temperature", f"{ws['avg_temp_f']:.0f}°F")
            summary.add_row("Temp Range", f"{ws['min_temp_f']:.0f}°F – {ws['max_temp_f']:.0f}°F")
        sky_dist = ws.get("sky_distribution", {})
        if sky_dist:
            from core.weather import weather_icon as _wi
            sky_str = ", ".join(f"{_wi(k)} {k}: {v}" for k, v in sorted(sky_dist.items(), key=lambda x: -x[1]))
            summary.add_row("Sky Conditions", sky_str)
        summary.add_row("Runs with Precipitation", str(ws.get("runs_with_precip", 0)))
        console.print(summary)

    # Footnote if any locations have asterisk (fallback)
    has_fallback = any("*" in (r.get("weather", {}).get("location", "") or "") for r in outdoor_with_weather)
    if has_fallback:
        console.print("[dim]* Location estimated from default training location[/dim]")

    console.print()


def _display_cross_training(cross: dict):
    if cross.get("total_sessions", 0) == 0:
        return
    table = Table(title="🏋️ Cross-Training", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Total Sessions", str(cross.get("total_sessions", 0)))
    table.add_row("Avg Weekly Sessions", str(cross.get("avg_weekly_sessions", 0)))
    table.add_row("Avg Duration", f"{cross.get('avg_duration_min', 0)} min")
    table.add_row("Avg Calories", str(int(cross.get("avg_calories", 0))))
    if cross.get("avg_heart_rate", 0) > 0:
        table.add_row("Avg Heart Rate", f"{int(cross['avg_heart_rate'])} bpm")
    activity_types = cross.get("activity_types", {})
    if activity_types:
        types_str = ", ".join(f"{k} ({v})" for k, v in sorted(activity_types.items(), key=lambda x: -x[1]))
        table.add_row("Activities", types_str)
    console.print(table)
    console.print()


def _display_heart_rate(hr: dict):
    table = Table(title="❤️  Heart Rate", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Avg Resting HR", f"{hr.get('avg_resting_hr', 'N/A')} bpm")
    table.add_row("Min Resting HR", f"{hr.get('min_resting_hr', 'N/A')} bpm")
    table.add_row("Max Resting HR", f"{hr.get('max_resting_hr', 'N/A')} bpm")
    table.add_row("Trend", hr.get("resting_hr_trend", "N/A"))
    console.print(table)

    zones = hr.get("hr_zones", {})
    if zones:
        zt = Table(title="HR Zone Distribution", box=box.SIMPLE)
        zt.add_column("Zone", style="cyan")
        zt.add_column("Total Min", justify="right")
        zt.add_column("Avg Daily Min", justify="right")
        for name, data in zones.items():
            zt.add_row(name, str(data["total_minutes"]), str(data["avg_daily_minutes"]))
        console.print(zt)
    console.print()


def _display_vo2_max(vo2: dict):
    if not vo2.get("latest_vo2_max"):
        return
    table = Table(title="🫁 VO2 Max (Cardio Fitness)", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Latest VO2 Max", str(vo2.get("latest_vo2_max", "N/A")))
    table.add_row("Average", str(vo2.get("avg_vo2_max", "N/A")))
    table.add_row("Classification", vo2.get("classification", "N/A"))
    console.print(table)
    console.print()


def _display_sleep(sleep: dict):
    table = Table(title="💤 Sleep", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Avg Duration", f"{sleep.get('avg_duration_hrs', 0)} hrs")
    table.add_row("Avg Efficiency", f"{sleep.get('avg_efficiency', 0)}%")
    table.add_row("Avg Deep Sleep", f"{sleep.get('avg_deep_pct', 0)}%")
    table.add_row("Avg REM Sleep", f"{sleep.get('avg_rem_pct', 0)}%")
    table.add_row("Quality", sleep.get("sleep_quality", "N/A"))
    console.print(table)
    console.print()


def _display_hydration(hydration: dict):
    if hydration.get("days_tracked", 0) == 0:
        return
    table = Table(title="💧 Hydration", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Days Tracked", str(hydration.get("days_tracked", 0)))
    table.add_row("Daily Goal", f"{hydration.get('goal_ml', 0)} ml")
    table.add_row("Avg Daily Intake", f"{hydration.get('avg_daily_oz', 0)} oz ({hydration.get('avg_daily_ml', 0)} ml)")
    table.add_row("Days Meeting Goal", str(hydration.get("days_meeting_goal", 0)))
    table.add_row("Score", hydration.get("hydration_score", "N/A"))
    console.print(table)
    console.print()


def _display_daily_activity(activity: dict):
    table = Table(title="📊 Daily Activity Averages", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Steps", f"{activity.get('avg_daily_steps', 0):,.0f}")
    table.add_row("Distance", f"{activity.get('avg_daily_distance_mi', 0)} mi")
    table.add_row("Floors", str(activity.get("avg_daily_floors", 0)))
    table.add_row("Very Active", f"{activity.get('avg_very_active_min', 0)} min")
    table.add_row("Fairly Active", f"{activity.get('avg_fairly_active_min', 0)} min")
    table.add_row("Lightly Active", f"{activity.get('avg_lightly_active_min', 0)} min")
    table.add_row("Sedentary", f"{activity.get('avg_sedentary_min', 0)} min")
    table.add_row("Activity Level", activity.get("activity_level", "N/A"))
    console.print(table)
    console.print()


def _display_spo2(spo2: dict):
    if not spo2.get("avg_spo2"):
        return
    table = Table(title="🩸 SpO2 (Blood Oxygen)", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Avg SpO2", f"{spo2.get('avg_spo2', 'N/A')}%")
    table.add_row("Min SpO2", f"{spo2.get('min_spo2', 'N/A')}%")
    table.add_row("Assessment", spo2.get("assessment", "N/A"))
    console.print(table)
    console.print()


def _display_weekly_calories(cal_data: dict):
    weeks = cal_data.get("weeks", [])
    if not weeks:
        return
    table = Table(title="🔥 Calorie Burn by Week", box=box.ROUNDED)
    table.add_column("Week", style="cyan")
    table.add_column("Sessions", justify="right")
    table.add_column("Total Cal", justify="right", style="bold")
    table.add_column("Breakdown", style="dim")

    for w in weeks:
        breakdown = ", ".join(
            f"{name}: {cal:,}" for name, cal in
            sorted(w["by_type"].items(), key=lambda x: x[1], reverse=True)[:3]
        )
        table.add_row(
            w["week_start"],
            str(w["sessions"]),
            f"{w['total_calories']:,}",
            breakdown,
        )

    table.add_section()
    table.add_row(
        "[bold]Average[/bold]", "", f"[bold]{cal_data.get('avg_weekly_calories', 0):,.0f}[/bold]", ""
    )
    console.print(table)
    console.print()


def _display_readiness(readiness: dict):
    panel_content = []
    panel_content.append(f"Race: {RACE_NAME} ({RACE_DISTANCE_MILES} mi)")
    panel_content.append(f"Date: {RACE_DATE}")
    panel_content.append(f"Weeks Remaining: {readiness.get('weeks_remaining', '?')}")
    panel_content.append(f"Estimated Finish: {readiness.get('estimated_finish_time', 'N/A')}")
    panel_content.append(f"\nOverall: {readiness.get('overall_readiness', 'N/A')}")

    strengths = readiness.get("strengths", [])
    if strengths:
        panel_content.append("\n✅ Strengths:")
        for s in strengths:
            panel_content.append(f"  • {s}")

    areas = readiness.get("areas_to_improve", [])
    if areas:
        panel_content.append("\n⚠️  Areas to Improve:")
        for a in areas:
            panel_content.append(f"  • {a}")

    console.print(Panel(
        "\n".join(panel_content),
        title="[bold green]🎯 Half Marathon Readiness[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def display_plan(plan: dict):
    """Display the training plan in the terminal."""
    console.print()
    console.rule("[bold blue]📋 Half Marathon Training Plan[/bold blue]")
    console.print()

    race = plan.get("race", {})
    console.print(f"[bold]{race.get('name', RACE_NAME)}[/bold] — {race.get('date', RACE_DATE)}")
    console.print(f"Distance: {race.get('distance_miles', RACE_DISTANCE_MILES)} miles")
    console.print(f"Weeks remaining: {race.get('weeks_remaining', '?')}")
    console.print()

    # Training History
    history = plan.get("training_history", {})
    if history.get("weeks_trained", 0) > 0:
        hist_lines = [
            f"📅 Training since: {history.get('start_date', 'N/A')} ({history.get('weeks_trained', 0)} weeks of base building)",
            f"🏃 Runs completed: {history.get('total_runs', 0)} ({history.get('total_miles', 0)} mi total)",
            f"🏆 Longest run: {history.get('longest_run', 0)} mi",
            f"📊 Avg weekly mileage: {history.get('avg_weekly_mileage', 0)} mi",
            f"🏋️ Cross-training sessions: {history.get('cross_training_sessions', 0)}",
            f"✅ Phase completed: {history.get('phase_completed', 'Base Building')}",
        ]
        console.print(Panel(
            "\n".join(hist_lines),
            title="[bold]📈 Training History (Completed)[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))
        console.print()

    # Guardrails
    guardrails = plan.get("guardrails", {})
    if guardrails:
        gr_lines = [
            "❌ No back-to-back running days",
            f"📈 Max weekly mileage increase: {guardrails.get('max_weekly_increase', '10%')}",
            f"🏃 Long run: {guardrails.get('long_run_progression', '+1 mi/week to 12 mi peak')}",
            f"🏋️ Cross-training: {guardrails.get('cross_training', 'On non-run days')}",
            f"😴 Rest days: {guardrails.get('rest_days', 'As needed')}",
            f"🏁 Taper: {guardrails.get('taper', '2 weeks')}",
        ]
        console.print(Panel(
            "\n".join(gr_lines),
            title="[bold]📏 Training Guardrails[/bold]",
            border_style="blue",
            padding=(1, 2),
        ))
        console.print()

    # HR Zones
    zones = plan.get("hr_zones", {})
    if zones:
        zt = Table(title="❤️  Your Training HR Zones", box=box.ROUNDED)
        zt.add_column("Zone", style="cyan")
        zt.add_column("Range", justify="center")
        zt.add_column("BPM", justify="center", style="bold")
        zt.add_column("Purpose", style="dim")
        for key in ["zone_1_recovery", "zone_2_aerobic", "zone_3_tempo",
                     "zone_4_threshold", "zone_5_max"]:
            z = zones.get(key, {})
            if z:
                zt.add_row(z["name"], z["pct"], f"{z['bpm_low']}-{z['bpm_high']}",
                           z["purpose"])
        console.print(zt)
        console.print()

    # Weekly plan
    for week in plan.get("weekly_plan", []):
        week_title = f"Week {week['week']} — {week.get('dates', '')} [{week.get('type', '')}]"
        wt = Table(title=week_title, box=box.SIMPLE_HEAVY)
        wt.add_column("Day", style="cyan", width=5)
        wt.add_column("Workout", style="bold", width=18)
        wt.add_column("Miles", justify="right", width=6)
        wt.add_column("Pace", justify="center", width=10)
        wt.add_column("HR Zone", justify="center", width=10)
        wt.add_column("Notes", style="dim")

        for run in week.get("runs", []):
            dist = f"{run['distance_mi']}" if run["distance_mi"] > 0 else "—"
            wt.add_row(
                run["day"], run["type"], dist,
                run["target_pace"], run["hr_zone"], run["notes"]
            )

        total = week.get("total_miles", 0)
        wt.add_row("", "[bold]TOTAL[/bold]", f"[bold]{total}[/bold]", "", "", "")
        console.print(wt)
        console.print()

    # Race day
    rd = plan.get("race_day", {})
    if rd:
        _display_race_day(rd)

    # Tips
    tips = plan.get("general_tips", [])
    if tips:
        console.print("[bold]💡 Training Tips:[/bold]")
        for tip in tips:
            console.print(f"  {tip}")
        console.print()


def _display_race_day(rd: dict):
    """Display race day recommendations."""
    lines = [f"🎯 Target Finish: {rd.get('target_finish', 'N/A')}"]

    pacing = rd.get("pacing_strategy", {})
    lines.append(f"\n📏 Pacing: {pacing.get('strategy', '')}")
    lines.append(f"  First half: {pacing.get('first_half_pace', 'N/A')}")
    lines.append(f"  Second half: {pacing.get('second_half_pace', 'N/A')}")
    lines.append(f"\n❤️  HR: {rd.get('hr_strategy', '')}")

    hydration = rd.get("hydration", {})
    lines.append("\n💧 Hydration:")
    lines.append(f"  Before: {hydration.get('pre_race', '')}")
    lines.append(f"  During: {hydration.get('during_race', '')}")
    lines.append(f"  After: {hydration.get('post_race', '')}")

    nutrition = rd.get("nutrition_tips", {})
    lines.append("\n🍝 Nutrition:")
    lines.append(f"  Week before: {nutrition.get('week_before', '')}")
    lines.append(f"  Night before: {nutrition.get('night_before', '')}")
    lines.append(f"  Morning of: {nutrition.get('morning_of', '')}")
    lines.append(f"  During: {nutrition.get('during_race', '')}")
    lines.append(f"  ⚠️  {nutrition.get('important', '')}")

    gear = rd.get("gear_checklist", [])
    if gear:
        lines.append("\n🎒 Gear Checklist:")
        for item in gear:
            lines.append(f"  ☐ {item}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold yellow]🏁 Race Day — May 3, 2026[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    ))
    console.print()


def save_assessment_report(analysis: dict):
    """Save fitness assessment as a Markdown file."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"fitness_assessment_{date.today().isoformat()}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    lines = [f"# Fitness Assessment — {date.today().isoformat()}\n"]
    lines.append(f"**Goal:** {RACE_NAME} ({RACE_DISTANCE_MILES} mi) on {RACE_DATE}\n")

    profile = analysis.get("profile", {})
    lines.append("## Profile\n")
    lines.append(f"- **Name:** {profile.get('name', 'N/A')}")
    lines.append(f"- **Age:** {profile.get('age', 'N/A')}")
    lines.append(f"- **Height:** {profile.get('height_in', 0)}\" ({profile.get('height_cm', 0)} cm)")
    lines.append(f"- **Weight:** {profile.get('weight_lbs', 0)} lbs ({profile.get('weight_kg', 0)} kg)")
    lines.append(f"- **BMI:** {profile.get('bmi', 'N/A')}\n")

    running = analysis.get("running", {})
    lines.append("## Running\n")
    lines.append(f"- **Total Runs:** {running.get('total_runs', 0)}")
    lines.append(f"- **Avg Weekly Mileage:** {running.get('avg_weekly_mileage', 0)} mi")
    lines.append(f"- **Longest Run:** {running.get('longest_run_mi', 0)} mi")
    pace = running.get("avg_pace_per_mile", 0)
    if pace > 0:
        mins = int(pace)
        secs = int((pace - mins) * 60)
        lines.append(f"- **Avg Pace:** {mins}:{secs:02d}/mi\n")

    readiness = analysis.get("readiness", {})
    lines.append("## Readiness\n")
    lines.append(f"- **Overall:** {readiness.get('overall_readiness', 'N/A')}")
    lines.append(f"- **Estimated Finish:** {readiness.get('estimated_finish_time', 'N/A')}")
    lines.append(f"- **Weeks Remaining:** {readiness.get('weeks_remaining', '?')}\n")

    strengths = readiness.get("strengths", [])
    if strengths:
        lines.append("### Strengths\n")
        for s in strengths:
            lines.append(f"- ✅ {s}")
        lines.append("")

    areas = readiness.get("areas_to_improve", [])
    if areas:
        lines.append("### Areas to Improve\n")
        for a in areas:
            lines.append(f"- ⚠️ {a}")
        lines.append("")

    weekly_cal = analysis.get("weekly_calories", {})
    weeks = weekly_cal.get("weeks", [])
    if weeks:
        lines.append("## Calorie Burn by Week\n")
        lines.append("| Week | Sessions | Total Cal | Top Activities |")
        lines.append("|---|---|---|---|")
        for w in weeks:
            breakdown = ", ".join(
                f"{name}: {cal:,}" for name, cal in
                sorted(w["by_type"].items(), key=lambda x: x[1], reverse=True)[:3]
            )
            lines.append(f"| {w['week_start']} | {w['sessions']} | {w['total_calories']:,} | {breakdown} |")
        lines.append(f"\n**Avg Weekly Calories:** {weekly_cal.get('avg_weekly_calories', 0):,.0f}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    console.print(f"[green]Report saved to {filepath}[/green]")
    return filepath


def save_training_plan_report(plan: dict):
    """Save training plan as an HTML file."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, "training_plan.html")

    race = plan.get("race", {})
    race_name = race.get("name", RACE_NAME)
    race_date = race.get("date", RACE_DATE)
    race_dist = race.get("distance_miles", RACE_DISTANCE_MILES)
    weeks_remaining = race.get("weeks_remaining", "?")

    # --- HR Zones table rows ---
    zone_rows = ""
    zones = plan.get("hr_zones", {})
    zone_colors = {
        "zone_1_recovery": "#238636",
        "zone_2_aerobic": "#1f6feb",
        "zone_3_tempo": "#f0883e",
        "zone_4_threshold": "#f85149",
        "zone_5_max": "#a371f7",
    }
    for key in ["zone_1_recovery", "zone_2_aerobic", "zone_3_tempo",
                 "zone_4_threshold", "zone_5_max"]:
        z = zones.get(key, {})
        if z:
            color = zone_colors.get(key, "#58a6ff")
            zone_rows += (
                f'<tr><td><span style="color:{color}">●</span> {z["name"]}</td>'
                f'<td>{z["pct"]}</td><td>{z["bpm_low"]}-{z["bpm_high"]}</td>'
                f'<td>{z["purpose"]}</td></tr>\n'
            )

    # --- Guardrails ---
    guardrails = plan.get("guardrails", {})
    guardrails_html = ""
    if guardrails:
        gr_items = [
            f"❌ No back-to-back running days",
            f"📈 Max weekly mileage increase: {guardrails.get('max_weekly_increase', '10%')}",
            f"🏃 Long run: {guardrails.get('long_run_progression', '+1 mi/week to 12 mi peak')}",
            f"🏋️ Cross-training: {guardrails.get('cross_training', 'On non-run days')}",
            f"😴 Rest days: {guardrails.get('rest_days', 'As needed')}",
            f"🏁 Taper: {guardrails.get('taper', '2 weeks')}",
        ]
        guardrails_html = '<div class="card"><h2>📏 Training Guardrails</h2><ul>'
        for item in gr_items:
            guardrails_html += f"<li>{item}</li>"
        guardrails_html += "</ul></div>"

    # --- Training History ---
    history = plan.get("training_history", {})
    history_html = ""
    if history.get("weeks_trained", 0) > 0:
        history_html = f"""<div class="card">
            <h2>📈 Training History</h2>
            <div class="stats-row">
                <div class="stat-box"><div class="value">{history.get('total_runs', 0)}</div><div class="label">Runs</div></div>
                <div class="stat-box"><div class="value">{history.get('total_miles', 0)}</div><div class="label">Total Miles</div></div>
                <div class="stat-box"><div class="value">{history.get('longest_run', 0)}</div><div class="label">Longest Run (mi)</div></div>
                <div class="stat-box"><div class="value">{history.get('avg_weekly_mileage', 0)}</div><div class="label">Avg Mi/Week</div></div>
                <div class="stat-box"><div class="value">{history.get('cross_training_sessions', 0)}</div><div class="label">Cross-Training</div></div>
            </div>
        </div>"""

    # --- Weekly plan tables ---
    weeks_html = ""
    phase_colors = {
        "Build": "#238636", "Peak": "#f0883e", "Recovery": "#1f6feb",
        "Taper": "#a371f7", "Race Week": "#f85149",
    }
    for week in plan.get("weekly_plan", []):
        phase = week.get("type", "Build")
        phase_color = phase_colors.get(phase, "#58a6ff")
        total = week.get("total_miles", 0)

        run_rows = ""
        for run in week.get("runs", []):
            dist = f"{run['distance_mi']}" if run["distance_mi"] > 0 else "—"
            row_class = ""
            if "🚣" in run["type"]:
                row_class = ' class="row-cross"'
            elif "Long Run" in run["type"]:
                row_class = ' class="row-long"'
            elif "🏁" in run["type"]:
                row_class = ' class="row-race"'
            run_rows += (
                f"<tr{row_class}><td>{run['day']}</td><td>{run['type']}</td>"
                f"<td>{dist}</td><td>{run['target_pace']}</td>"
                f"<td>{run['hr_zone']}</td><td>{run['notes']}</td></tr>\n"
            )

        weeks_html += f"""
        <div class="card week-card">
            <h3>Week {week['week']} — {week.get('dates', '')}
                <span class="phase-badge" style="background:{phase_color}">{phase}</span>
            </h3>
            <table class="week-table">
                <thead><tr><th>Day</th><th>Workout</th><th>Miles</th><th>Pace</th><th>HR Zone</th><th>Notes</th></tr></thead>
                <tbody>{run_rows}</tbody>
                <tfoot><tr><td></td><td><strong>TOTAL</strong></td><td><strong>{total}</strong></td><td></td><td></td><td></td></tr></tfoot>
            </table>
        </div>"""

    # --- Race Day ---
    rd = plan.get("race_day", {})
    race_day_html = ""
    if rd:
        pacing = rd.get("pacing_strategy", {})
        hydration = rd.get("hydration", {})
        nutrition = rd.get("nutrition_tips", {})
        gear = rd.get("gear_checklist", [])
        gear_items = "".join(f"<li>{item}</li>" for item in gear)
        race_day_html = f"""<div class="card race-day-card">
            <h2>🏁 Race Day — {race_date}</h2>
            <div class="stats-row">
                <div class="stat-box"><div class="value">{rd.get('target_finish', 'N/A')}</div><div class="label">Target Finish</div></div>
                <div class="stat-box"><div class="value">{pacing.get('first_half_pace', 'N/A')}</div><div class="label">1st Half Pace</div></div>
                <div class="stat-box"><div class="value">{pacing.get('second_half_pace', 'N/A')}</div><div class="label">2nd Half Pace</div></div>
            </div>
            <p><strong>Strategy:</strong> {pacing.get('strategy', '')}</p>
            <p><strong>HR:</strong> {rd.get('hr_strategy', '')}</p>
            <div class="two-col">
                <div>
                    <h4>💧 Hydration</h4>
                    <ul><li><strong>Before:</strong> {hydration.get('pre_race', '')}</li>
                    <li><strong>During:</strong> {hydration.get('during_race', '')}</li>
                    <li><strong>After:</strong> {hydration.get('post_race', '')}</li></ul>
                </div>
                <div>
                    <h4>🍝 Nutrition</h4>
                    <ul><li><strong>Week before:</strong> {nutrition.get('week_before', '')}</li>
                    <li><strong>Night before:</strong> {nutrition.get('night_before', '')}</li>
                    <li><strong>Morning of:</strong> {nutrition.get('morning_of', '')}</li>
                    <li><strong>During:</strong> {nutrition.get('during_race', '')}</li></ul>
                </div>
            </div>
            <h4>🎒 Gear Checklist</h4>
            <ul class="gear-list">{gear_items}</ul>
        </div>"""

    # --- Tips ---
    tips = plan.get("general_tips", [])
    tips_html = ""
    if tips:
        tips_items = "".join(f"<li>{tip}</li>" for tip in tips)
        tips_html = f'<div class="card"><h2>💡 Training Tips</h2><ul>{tips_items}</ul></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏃 {race_name} Training Plan</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 20px;
        }}
        h1 {{ text-align: center; color: #58a6ff; margin-bottom: 4px; font-size: 1.8rem; }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 24px; font-size: 0.95rem; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .card {{
            background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 20px; margin-bottom: 20px;
        }}
        .card h2 {{ color: #58a6ff; margin-bottom: 12px; font-size: 1.2rem; }}
        .card h3 {{ color: #c9d1d9; margin-bottom: 12px; font-size: 1.05rem; }}
        .card h4 {{ color: #8b949e; margin: 12px 0 6px; }}
        .card ul {{ padding-left: 20px; }}
        .card li {{ margin-bottom: 4px; }}
        .stats-row {{
            display: flex; justify-content: space-around; text-align: center; padding: 12px 0;
        }}
        .stat-box .value {{ font-size: 1.6rem; font-weight: bold; color: #58a6ff; }}
        .stat-box .label {{ color: #8b949e; font-size: 0.8rem; }}
        .phase-badge {{
            display: inline-block; font-size: 0.75rem; font-weight: 600; color: #fff;
            padding: 2px 10px; border-radius: 12px; margin-left: 8px; vertical-align: middle;
        }}
        .week-table {{
            width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 8px;
        }}
        .week-table th {{
            background: #21262d; color: #8b949e; text-align: left;
            padding: 8px 10px; border-bottom: 2px solid #30363d; font-weight: 600;
        }}
        .week-table td {{ padding: 7px 10px; border-bottom: 1px solid #21262d; }}
        .week-table tfoot td {{ border-top: 2px solid #30363d; font-weight: bold; }}
        .row-cross td {{ color: #1f6feb; }}
        .row-long td {{ color: #f0883e; }}
        .row-race td {{ color: #f85149; font-weight: bold; }}
        table.zone-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        table.zone-table th {{
            background: #21262d; color: #8b949e; text-align: left;
            padding: 8px 10px; border-bottom: 2px solid #30363d;
        }}
        table.zone-table td {{ padding: 7px 10px; border-bottom: 1px solid #21262d; }}
        .race-day-card {{ border-color: #f0883e; }}
        .race-day-card h2 {{ color: #f0883e; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }}
        .gear-list {{ columns: 2; }}
        @media (max-width: 600px) {{
            .two-col {{ grid-template-columns: 1fr; }}
            .gear-list {{ columns: 1; }}
            .stats-row {{ flex-wrap: wrap; gap: 12px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏃 {race_name} Training Plan</h1>
        <p class="subtitle">{race_date} · {race_dist} miles · {weeks_remaining} weeks remaining · Generated {date.today().isoformat()}</p>

        {history_html}
        {guardrails_html}

        <div class="card">
            <h2>❤️ Training HR Zones</h2>
            <table class="zone-table">
                <thead><tr><th>Zone</th><th>Range</th><th>BPM</th><th>Purpose</th></tr></thead>
                <tbody>{zone_rows}</tbody>
            </table>
        </div>

        {weeks_html}
        {race_day_html}
        {tips_html}
    </div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"[green]Training plan saved to {filepath}[/green]")
    return filepath
