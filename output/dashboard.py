"""Generates an interactive HTML dashboard with Chart.js graphs from Fitbit SQLite cache."""

import json
import os
import sqlite3
import webbrowser
from datetime import date, datetime
from collections import defaultdict

from rich.console import Console

from core.cache import DB_PATH
from config import DATA_START_DATE, RACE_DATE, RACE_NAME
from utils import KM_TO_MILES
from utils import get_week_start

console = Console()
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")


def _get_dashboard_end_date():
    """Return the dashboard end date: today or race day, whichever is earlier."""
    today = date.today()
    race = datetime.strptime(RACE_DATE, "%Y-%m-%d").date() if isinstance(RACE_DATE, str) else RACE_DATE
    return min(today, race).isoformat()


def _pad_labels_values(labels, values, end_date, weekly=False, start_date=None):
    """Extend labels/values so the chart spans from start_date to end_date.

    For weekly charts, pads to the Monday (week start) of the respective dates.
    For daily charts, pads to the exact dates.
    Missing values are filled with None so Chart.js skips them.
    """
    if not labels:
        return labels, values

    if weekly:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        target_end = get_week_start(end_dt).strftime("%Y-%m-%d")
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            target_start = get_week_start(start_dt).strftime("%Y-%m-%d")
        else:
            target_start = None
    else:
        target_end = end_date
        target_start = start_date

    # Prepend start date if chart data begins after it
    if target_start and labels[0] > target_start:
        labels.insert(0, target_start)
        values.insert(0, None)

    # Append end date if chart data ends before it
    if labels[-1] < target_end:
        labels.append(target_end)
        values.append(None)
    return labels, values


def _pad_multi_series(labels, series_dict, end_date, weekly=False, start_date=None):
    """Pad a multi-series dataset (shared labels, multiple value lists)."""
    if not labels:
        return labels, series_dict

    if weekly:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        target_end = get_week_start(end_dt).strftime("%Y-%m-%d")
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            target_start = get_week_start(start_dt).strftime("%Y-%m-%d")
        else:
            target_start = None
    else:
        target_end = end_date
        target_start = start_date

    # Prepend start date
    if target_start and labels[0] > target_start:
        labels.insert(0, target_start)
        for key in series_dict:
            if isinstance(series_dict[key], list):
                series_dict[key].insert(0, None)

    # Append end date
    if labels[-1] < target_end:
        labels.append(target_end)
        for key in series_dict:
            if isinstance(series_dict[key], list):
                series_dict[key].append(None)
    return labels, series_dict


def _align_chart_dates(data, end_date):
    """Pad all chart datasets so they span from DATA_START_DATE to end_date."""
    start = DATA_START_DATE

    # Weekly charts — pad from DATA_START_DATE to end_date's week
    for key in ("weekly_mileage", "long_runs", "weekly_calories"):
        if key in data and "labels" in data[key]:
            data[key]["labels"], data[key]["values"] = _pad_labels_values(
                data[key]["labels"], data[key]["values"], end_date, weekly=True, start_date=start
            )

    # Cross-training has two series sharing labels
    if "cross_training" in data and "labels" in data["cross_training"]:
        labels = data["cross_training"]["labels"]
        if labels:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            target_end = get_week_start(end_dt).strftime("%Y-%m-%d")
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            target_start = get_week_start(start_dt).strftime("%Y-%m-%d")
            if labels[0] > target_start:
                labels.insert(0, target_start)
                data["cross_training"]["cross_training"].insert(0, None)
                data["cross_training"]["running"].insert(0, None)
            if labels[-1] < target_end:
                labels.append(target_end)
                data["cross_training"]["cross_training"].append(None)
                data["cross_training"]["running"].append(None)

    # HR zones — multi-series with datasets dict
    if "hr_zones" in data and "labels" in data["hr_zones"]:
        data["hr_zones"]["labels"], data["hr_zones"]["datasets"] = _pad_multi_series(
            data["hr_zones"]["labels"], data["hr_zones"]["datasets"], end_date, weekly=True, start_date=start
        )

    # Daily charts — pad from DATA_START_DATE to exact end_date
    for key in ("resting_hr", "run_pace"):
        if key in data and "labels" in data[key]:
            data[key]["labels"], data[key]["values"] = _pad_labels_values(
                data[key]["labels"], data[key]["values"], end_date, weekly=False, start_date=start
            )

    # Weight
    if "weight" in data and "labels" in data["weight"]:
        data["weight"]["labels"], data["weight"]["values"] = _pad_labels_values(
            data["weight"]["labels"], data["weight"]["values"], end_date, weekly=False, start_date=start
        )

    # Sleep has two series sharing labels
    if "sleep" in data and "labels" in data["sleep"]:
        labels = data["sleep"]["labels"]
        if labels:
            if labels[0] > start:
                labels.insert(0, start)
                data["sleep"]["duration_hrs"].insert(0, None)
                data["sleep"]["efficiency"].insert(0, None)
            if labels[-1] < end_date:
                labels.append(end_date)
                data["sleep"]["duration_hrs"].append(None)
                data["sleep"]["efficiency"].append(None)

    return data


def generate_dashboard():
    """Read all data from SQLite cache and generate an HTML dashboard."""
    if not os.path.exists(DB_PATH):
        console.print("[red]No cache database found. Run 'python main.py assess' first.[/red]")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    data = {
        "weekly_mileage": _get_weekly_mileage(conn),
        "long_runs": _get_long_runs(conn),
        "resting_hr": _get_resting_hr(conn),
        "weight": _get_weight(conn),
        "sleep": _get_sleep(conn),
        "run_pace": _get_run_pace(conn),
        "hr_zones": _get_hr_zones(conn),
        "activity_heatmap": _get_activity_heatmap(conn),
        "cross_training": _get_cross_training(conn),
        "weekly_calories": _get_weekly_calories(conn),
        "workout_splits": _get_workout_splits(conn),
        "run_weather": _get_run_weather(conn),
        "confidence": _get_confidence_trajectory(conn),
    }

    conn.close()

    end_date = _get_dashboard_end_date()
    data = _align_chart_dates(data, end_date)

    html = _build_html(data)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, "dashboard.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    # Generate activities page
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    activities_data = _get_activities_page_data(conn)
    conn.close()

    activities_html = _build_activities_html(activities_data)
    activities_path = os.path.join(REPORTS_DIR, "activities.html")
    with open(activities_path, "w", encoding="utf-8") as f:
        f.write(activities_html)

    # Generate confidence reasoning page
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    reasoning_data = _get_confidence_reasoning(conn)
    conn.close()

    if reasoning_data["has_data"]:
        reasoning_html = _build_confidence_reasoning_html(reasoning_data)
        reasoning_path = os.path.join(REPORTS_DIR, "confidence_reasoning.html")
        with open(reasoning_path, "w", encoding="utf-8") as f:
            f.write(reasoning_html)
        console.print(f"[green]Confidence reasoning saved to {reasoning_path}[/green]")

    console.print(f"[green]Dashboard saved to {filepath}[/green]")
    console.print(f"[green]Activities page saved to {activities_path}[/green]")
    console.print("[bold]Opening in browser...[/bold]")
    webbrowser.open(f"file:///{filepath.replace(os.sep, '/')}")


def _get_weekly_mileage(conn):
    """Get weekly running mileage from activities."""
    rows = conn.execute(
        "SELECT date, data FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    weekly = defaultdict(float)
    for r in rows:
        act = json.loads(r["data"])
        name = act.get("activityName", "").lower()
        if "run" not in name and "jog" not in name:
            continue
        dist = act.get("distance", 0)
        unit = act.get("distanceUnit", "")
        if "kilometer" in unit.lower() or "km" in unit.lower():
            dist *= KM_TO_MILES

        d = datetime.strptime(r["date"], "%Y-%m-%d")
        week_start = get_week_start(d)
        week_key = week_start.strftime("%Y-%m-%d")
        weekly[week_key] += dist

    sorted_weeks = sorted(weekly.items())
    return {
        "labels": [w[0] for w in sorted_weeks],
        "values": [round(w[1], 1) for w in sorted_weeks],
    }


def _get_long_runs(conn):
    """Get longest run per week."""
    rows = conn.execute(
        "SELECT date, data FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    weekly_max = defaultdict(float)
    for r in rows:
        act = json.loads(r["data"])
        name = act.get("activityName", "").lower()
        if "run" not in name and "jog" not in name:
            continue
        dist = act.get("distance", 0)
        unit = act.get("distanceUnit", "")
        if "kilometer" in unit.lower() or "km" in unit.lower():
            dist *= KM_TO_MILES

        d = datetime.strptime(r["date"], "%Y-%m-%d")
        week_start = get_week_start(d)
        week_key = week_start.strftime("%Y-%m-%d")
        weekly_max[week_key] = max(weekly_max[week_key], dist)

    sorted_weeks = sorted(weekly_max.items())
    return {
        "labels": [w[0] for w in sorted_weeks],
        "values": [round(w[1], 1) for w in sorted_weeks],
    }


def _get_resting_hr(conn):
    """Get resting heart rate trend."""
    rows = conn.execute(
        "SELECT date, resting_hr FROM heart_rate WHERE date >= ? AND resting_hr IS NOT NULL ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()
    return {
        "labels": [r["date"] for r in rows],
        "values": [r["resting_hr"] for r in rows],
    }


def _get_weight(conn):
    """Get weight trend."""
    rows = conn.execute(
        "SELECT date, weight_kg FROM weight_log WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()
    return {
        "labels": [r["date"] for r in rows],
        "values": [round(r["weight_kg"] * 2.205, 1) for r in rows if r["weight_kg"]],
    }


def _get_sleep(conn):
    """Get sleep duration and efficiency."""
    rows = conn.execute(
        "SELECT date, duration_ms, efficiency FROM sleep_log WHERE date >= ? AND is_main_sleep = 1 ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()
    return {
        "labels": [r["date"] for r in rows],
        "duration_hrs": [round(r["duration_ms"] / 3600000, 1) for r in rows if r["duration_ms"]],
        "efficiency": [r["efficiency"] for r in rows if r["efficiency"]],
    }


def _get_run_pace(conn):
    """Get pace trend for runs."""
    rows = conn.execute(
        "SELECT date, data FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    paces = []
    for r in rows:
        act = json.loads(r["data"])
        name = act.get("activityName", "").lower()
        if "run" not in name and "jog" not in name:
            continue
        dist = act.get("distance", 0)
        unit = act.get("distanceUnit", "")
        if "kilometer" in unit.lower() or "km" in unit.lower():
            dist *= KM_TO_MILES
        dur_min = act.get("duration", 0) / 60000
        if dist > 0:
            pace = dur_min / dist
            paces.append({"date": r["date"], "pace": round(pace, 2)})

    return {
        "labels": [p["date"] for p in paces],
        "values": [p["pace"] for p in paces],
    }


def _get_hr_zones(conn):
    """Get weekly HR zone distribution from running workouts only."""
    rows = conn.execute(
        "SELECT date, data, activity_name FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    weekly_zones = defaultdict(lambda: defaultdict(int))
    for r in rows:
        name = (r["activity_name"] or "").lower()
        if "run" not in name and "jog" not in name:
            continue
        act = json.loads(r["data"])
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        week_start = get_week_start(d)
        week_key = week_start.strftime("%Y-%m-%d")
        for zone in act.get("heartRateZones", []):
            zname = zone.get("name", "Unknown")
            minutes = zone.get("minutes", 0)
            if minutes > 0:
                weekly_zones[week_key][zname] += minutes

    # Get BPM ranges from heart_rate daily data
    zone_ranges = {}
    try:
        hr_row = conn.execute("SELECT data FROM heart_rate LIMIT 1").fetchone()
        if hr_row:
            hr_data = json.loads(hr_row["data"])
            for z in hr_data.get("value", {}).get("heartRateZones", []):
                zone_ranges[z["name"]] = f"{z.get('min', '?')}-{z.get('max', '?')} bpm"
    except Exception:
        pass

    zone_order = ["Out of Range", "Fat Burn", "Cardio", "Peak"]
    zone_display = {"Out of Range": "Warm Up", "Fat Burn": "Fat Burn", "Cardio": "Cardio", "Peak": "Peak"}
    weeks = sorted(weekly_zones.keys())

    datasets = {}
    for z in zone_order:
        bpm = zone_ranges.get(z, "")
        display = zone_display.get(z, z)
        label = f"{display} ({bpm})" if bpm else display
        datasets[label] = [weekly_zones[w].get(z, 0) for w in weeks]

    return {
        "labels": weeks,
        "datasets": datasets,
    }


def _get_activity_heatmap(conn):
    """Get daily activity count for heatmap."""
    rows = conn.execute(
        "SELECT date, activity_name FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    daily = defaultdict(lambda: {"runs": 0, "rows": 0, "other": 0})
    for r in rows:
        name = (r["activity_name"] or "").lower()
        if "run" in name or "jog" in name:
            daily[r["date"]]["runs"] += 1
        elif "row" in name:
            daily[r["date"]]["rows"] += 1
        else:
            daily[r["date"]]["other"] += 1

    return dict(daily)


def _get_cross_training(conn):
    """Get weekly cross-training and running duration."""
    rows = conn.execute(
        "SELECT date, data FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    running_keywords = ["run", "treadmill"]
    weekly_cross = defaultdict(float)
    weekly_running = defaultdict(float)
    for r in rows:
        act = json.loads(r["data"])
        name = act.get("activityName", "").lower()
        dur_min = act.get("duration", 0) / 60000
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        week_start = get_week_start(d)
        week_key = week_start.strftime("%Y-%m-%d")
        if any(kw in name for kw in running_keywords):
            weekly_running[week_key] += dur_min
        elif dur_min >= 5:
            weekly_cross[week_key] += dur_min

    all_weeks = sorted(set(weekly_cross.keys()) | set(weekly_running.keys()))
    return {
        "labels": all_weeks,
        "cross_training": [round(weekly_cross.get(w, 0)) for w in all_weeks],
        "running": [round(weekly_running.get(w, 0)) for w in all_weeks],
    }


def _get_weekly_calories(conn):
    """Get weekly calorie burn across all activity types."""
    rows = conn.execute(
        "SELECT date, data FROM activities WHERE date >= ? ORDER BY date",
        (DATA_START_DATE,)
    ).fetchall()

    weekly = defaultdict(float)
    for r in rows:
        act = json.loads(r["data"])
        calories = act.get("calories", 0)
        if calories <= 0:
            continue
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        week_start = get_week_start(d)
        week_key = week_start.strftime("%Y-%m-%d")
        weekly[week_key] += calories

    sorted_weeks = sorted(weekly.items())
    return {
        "labels": [w[0] for w in sorted_weeks],
        "values": [round(w[1]) for w in sorted_weeks],
    }


def _get_workout_splits(conn):
    """Get per-mile split data for dashboard charts.

    Returns data for 4 charts:
    - recent_splits: bar chart data for latest run's mile splits
    - split_comparison: line chart comparing pacing across recent runs
    - hr_drift: HR progression per mile across recent runs
    - consistency_trend: pace consistency (CV%) over time
    """
    # Check if tables exist
    try:
        conn.execute("SELECT 1 FROM workout_splits LIMIT 1")
    except Exception:
        return {"has_data": False}

    # Get all splits joined with activity dates
    rows = conn.execute("""
        SELECT ws.log_id, ws.mile_number, ws.split_time_sec, ws.pace_per_mile,
               ws.avg_hr, ws.avg_cadence, ws.cumulative_distance, a.date, a.activity_name
        FROM workout_splits ws
        JOIN activities a ON ws.log_id = a.log_id
        WHERE a.date >= ?
        ORDER BY a.date, ws.mile_number
    """, (DATA_START_DATE,)).fetchall()

    if not rows:
        return {"has_data": False}

    # Group by run
    runs = defaultdict(list)
    run_dates = {}
    for r in rows:
        lid = r["log_id"]
        runs[lid].append({
            "mile": r["mile_number"],
            "pace": r["pace_per_mile"],
            "hr": r["avg_hr"],
            "cadence": r["avg_cadence"],
        })
        run_dates[lid] = r["date"]

    # Sort runs by date
    sorted_runs = sorted(runs.items(), key=lambda x: run_dates.get(x[0], ""))

    # --- Recent splits (latest run bar chart) ---
    latest_lid, latest_splits = sorted_runs[-1]
    latest_date = run_dates[latest_lid]
    avg_pace = sum(s["pace"] for s in latest_splits if s["pace"]) / max(1, len(latest_splits))
    recent_splits = {
        "date": latest_date,
        "labels": [f"Mile {s['mile']}" for s in latest_splits],
        "paces": [round(s["pace"], 2) if s["pace"] else None for s in latest_splits],
        "avg_pace": round(avg_pace, 2),
        "hrs": [round(s["hr"], 1) if s["hr"] else None for s in latest_splits],
    }

    # --- Split comparison (last 8 runs, pace per mile) ---
    comparison_runs = sorted_runs[-8:]
    max_miles = max(len(splits) for _, splits in comparison_runs)
    split_comparison = {
        "mile_labels": [f"Mile {i+1}" for i in range(max_miles)],
        "runs": [],
    }
    for lid, splits in comparison_runs:
        run_paces = [None] * max_miles
        for s in splits:
            if s["mile"] <= max_miles:
                run_paces[s["mile"] - 1] = round(s["pace"], 2) if s["pace"] else None
        split_comparison["runs"].append({
            "date": run_dates[lid],
            "paces": run_paces,
        })

    # --- HR drift (last 8 runs, HR per mile) ---
    hr_drift = {
        "mile_labels": [f"Mile {i+1}" for i in range(max_miles)],
        "runs": [],
    }
    for lid, splits in comparison_runs:
        run_hrs = [None] * max_miles
        for s in splits:
            if s["mile"] <= max_miles and s["hr"]:
                run_hrs[s["mile"] - 1] = round(s["hr"], 1)
        hr_drift["runs"].append({
            "date": run_dates[lid],
            "hrs": run_hrs,
        })

    # --- Consistency trend (CV% over time) ---
    consistency_trend = {"labels": [], "values": []}
    for lid, splits in sorted_runs:
        paces = [s["pace"] for s in splits if s["pace"] and len(splits) >= 2]
        if len(paces) < 2:
            continue
        mean_p = sum(paces) / len(paces)
        variance = sum((p - mean_p) ** 2 for p in paces) / len(paces)
        cv = round((variance ** 0.5 / mean_p) * 100, 1) if mean_p > 0 else 0
        consistency_trend["labels"].append(run_dates[lid])
        consistency_trend["values"].append(cv)

    return {
        "has_data": True,
        "recent_splits": recent_splits,
        "split_comparison": split_comparison,
        "hr_drift": hr_drift,
        "consistency_trend": consistency_trend,
    }


def _get_run_weather(conn):
    """Get weather data for outdoor runs, joined with run details."""
    try:
        conn.execute("SELECT 1 FROM run_weather LIMIT 1")
    except Exception:
        return {"has_data": False}

    rows = conn.execute("""
        SELECT rw.log_id, rw.date, rw.avg_temp_f, rw.total_precip_in,
               rw.precip_type, rw.sky_condition, rw.cloud_cover_pct,
               a.data as activity_data, a.avg_heart_rate
        FROM run_weather rw
        JOIN activities a ON rw.log_id = a.log_id
        WHERE rw.date >= ?
        ORDER BY rw.date
    """, (DATA_START_DATE,)).fetchall()

    if not rows:
        return {"has_data": False}

    dates = []
    temps = []
    distances = []
    paces = []
    sky_conditions = []
    precip_types = []
    avg_heart_rates = []

    for r in rows:
        act = json.loads(r["activity_data"])
        dist = act.get("distance", 0)
        unit = act.get("distanceUnit", "")
        if "kilometer" in unit.lower() or "km" in unit.lower():
            dist *= KM_TO_MILES
        dur_min = act.get("duration", 0) / 60000
        pace = dur_min / dist if dist > 0 else 0

        dates.append(r["date"])
        temps.append(r["avg_temp_f"])
        distances.append(round(dist, 2))
        paces.append(round(pace, 2))
        sky_conditions.append(r["sky_condition"])
        precip_types.append(r["precip_type"] or "None")
        avg_heart_rates.append(r["avg_heart_rate"] or 0)

    return {
        "has_data": True,
        "dates": dates,
        "temps": temps,
        "distances": distances,
        "paces": paces,
        "sky_conditions": sky_conditions,
        "precip_types": precip_types,
        "avg_heart_rates": avg_heart_rates,
    }


def _get_confidence_trajectory(conn):
    """Get AI confidence scores over time from the confidence_scores table."""
    try:
        conn.execute("SELECT 1 FROM confidence_scores LIMIT 1")
    except Exception:
        return {"has_data": False}

    rows = conn.execute(
        "SELECT date, model, score FROM confidence_scores ORDER BY date, model"
    ).fetchall()

    if not rows:
        return {"has_data": False}

    from collections import defaultdict
    by_date = defaultdict(dict)
    models = set()
    for r in rows:
        by_date[r["date"]][r["model"]] = r["score"]
        models.add(r["model"])

    dates = sorted(by_date.keys())
    models = sorted(models)
    consensus = []
    model_series = {m: [] for m in models}

    for d in dates:
        scores = by_date[d]
        vals = [scores.get(m, 0) for m in models]
        consensus.append(round(sum(vals) / len(vals), 1))
        for m in models:
            model_series[m].append(scores.get(m, None))

    return {
        "has_data": True,
        "dates": dates,
        "consensus": consensus,
        "models": models,
        "model_series": model_series,
    }


def _get_confidence_reasoning(conn):
    """Get AI confidence reasoning from the confidence_scores table."""
    try:
        conn.execute("SELECT reasoning FROM confidence_scores LIMIT 1")
    except Exception:
        return {"has_data": False, "rows": []}

    rows = conn.execute(
        "SELECT date, model, score, reasoning FROM confidence_scores "
        "ORDER BY date DESC, model"
    ).fetchall()

    if not rows:
        return {"has_data": False, "rows": []}

    return {
        "has_data": True,
        "rows": [
            {
                "date": r["date"],
                "model": r["model"],
                "score": r["score"],
                "reasoning": r["reasoning"] or "—",
            }
            for r in rows
        ],
    }


def _build_confidence_reasoning_html(data):
    """Build a standalone HTML page with the confidence reasoning table."""
    rows = data.get("rows", [])
    models = sorted(set(r["model"] for r in rows))

    # Build table rows
    table_rows = []
    for r in rows:
        score = r["score"]
        if score >= 7:
            color = "#3fb950"
        elif score >= 5:
            color = "#d29922"
        else:
            color = "#f85149"
        table_rows.append(
            f'<tr data-model="{r["model"]}">'
            f'<td>{r["date"]}</td>'
            f'<td>{r["model"]}</td>'
            f'<td style="color:{color};font-weight:bold">{score}</td>'
            f'<td class="reasoning">{r["reasoning"]}</td>'
            f"</tr>"
        )
    table_body = "\n".join(table_rows)

    model_options = "".join(
        f'<option value="{m}">{m}</option>' for m in models
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🧠 Confidence Reasoning — {RACE_NAME}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 20px;
        }}
        h1 {{ text-align: center; color: #58a6ff; margin-bottom: 4px; font-size: 1.8rem; }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 8px; font-size: 0.95rem; }}
        nav {{ text-align: center; margin-bottom: 20px; }}
        nav a {{ color: #58a6ff; text-decoration: none; font-size: 0.95rem; }}
        nav a:hover {{ text-decoration: underline; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .card {{
            background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px;
            margin-bottom: 20px;
        }}
        .card h3 {{ color: #58a6ff; margin-bottom: 12px; font-size: 1.1rem; }}
        .filter-bar {{
            display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
        }}
        .filter-bar select {{
            background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
            border-radius: 6px; padding: 6px 12px; font-size: 0.85rem;
        }}
        .table-wrap {{
            max-height: 700px; overflow-y: auto; border-radius: 8px;
            border: 1px solid #30363d;
        }}
        table.reasoning-log {{
            width: 100%; border-collapse: collapse; font-size: 0.85rem;
        }}
        table.reasoning-log th {{
            background: #21262d; color: #8b949e; text-align: left;
            padding: 8px 10px; border-bottom: 2px solid #30363d;
            position: sticky; top: 0; cursor: pointer;
        }}
        table.reasoning-log th:hover {{ color: #58a6ff; }}
        table.reasoning-log td {{
            padding: 8px 10px; border-bottom: 1px solid #21262d;
            vertical-align: top;
        }}
        table.reasoning-log td.reasoning {{
            max-width: 700px; line-height: 1.5;
        }}
        table.reasoning-log tbody tr:hover {{ background: #1c2128; }}
        @media (max-width: 768px) {{
            table.reasoning-log td.reasoning {{ max-width: 300px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 Confidence Reasoning</h1>
        <p class="subtitle">{RACE_NAME} Training · Why each model scored the way it did · Generated {date.today().isoformat()}</p>
        <nav><a href="dashboard.html">← Back to Dashboard</a></nav>

        <div class="card">
            <h3>Filter by Model</h3>
            <div class="filter-bar">
                <select id="modelFilter" onchange="filterTable()">
                    <option value="all">All Models</option>
                    {model_options}
                </select>
            </div>
        </div>

        <div class="card">
            <div class="table-wrap">
                <table class="reasoning-log" id="reasoningTable">
                    <thead>
                        <tr>
                            <th onclick="sortTable(0)" style="width:100px">Date ↕</th>
                            <th onclick="sortTable(1)" style="width:120px">Model ↕</th>
                            <th onclick="sortTable(2)" style="width:60px">Score ↕</th>
                            <th>Reasoning</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_body}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
    function filterTable() {{
        const model = document.getElementById('modelFilter').value;
        const rows = document.querySelectorAll('#reasoningTable tbody tr');
        rows.forEach(row => {{
            if (model === 'all' || row.dataset.model === model) {{
                row.style.display = '';
            }} else {{
                row.style.display = 'none';
            }}
        }});
    }}

    let sortDir = [false, false, false, false];
    function sortTable(col) {{
        const table = document.getElementById('reasoningTable');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        sortDir[col] = !sortDir[col];
        rows.sort((a, b) => {{
            let aVal = a.cells[col].textContent.trim();
            let bVal = b.cells[col].textContent.trim();
            if (col === 2) {{ aVal = parseFloat(aVal); bVal = parseFloat(bVal); }}
            if (aVal < bVal) return sortDir[col] ? -1 : 1;
            if (aVal > bVal) return sortDir[col] ? 1 : -1;
            return 0;
        }});
        rows.forEach(row => tbody.appendChild(row));
    }}
    </script>
</body>
</html>"""


def _build_html(data):
    """Build the complete HTML dashboard."""
    data_json = json.dumps(data, default=str)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏃 {RACE_NAME} Training Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }}
        h1 {{
            text-align: center;
            color: #58a6ff;
            margin-bottom: 8px;
            font-size: 1.8rem;
        }}
        .subtitle {{
            text-align: center;
            color: #8b949e;
            margin-bottom: 24px;
            font-size: 0.95rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
        }}
        .card h3 {{
            color: #58a6ff;
            margin-bottom: 12px;
            font-size: 1.1rem;
        }}
        .card.wide {{
            grid-column: span 2;
        }}
        canvas {{
            width: 100% !important;
            max-height: 300px;
        }}
        .stats-row {{
            display: flex;
            justify-content: space-around;
            text-align: center;
            padding: 16px 0;
        }}
        .stat-box {{
            padding: 8px 16px;
        }}
        .stat-box .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #58a6ff;
        }}
        .stat-box .label {{
            color: #8b949e;
            font-size: 0.85rem;
        }}
        .heatmap {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 3px;
        }}
        .heatmap-day {{
            aspect-ratio: 1;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.65rem;
            color: #c9d1d9;
        }}
        .heatmap-header {{
            font-size: 0.7rem;
            color: #8b949e;
            text-align: center;
            padding: 2px;
        }}
        @media (max-width: 768px) {{
            .grid {{ grid-template-columns: 1fr; }}
            .card.wide {{ grid-column: span 1; }}
        }}
    </style>
</head>
<body>
    <h1>🏃 {RACE_NAME} Training Dashboard</h1>
    <p class="subtitle">Race Day: {RACE_DATE} | Data from {DATA_START_DATE} | Generated {date.today().isoformat()}</p>
    <nav style="text-align:center;margin-bottom:20px"><a href="activities.html" style="color:#58a6ff;text-decoration:none;font-size:0.95rem">📋 View All Activities →</a> &nbsp;|&nbsp; <a href="confidence_reasoning.html" style="color:#58a6ff;text-decoration:none;font-size:0.95rem">🧠 Confidence Reasoning →</a></nav>

    <div class="grid">
        <div class="card wide">
            <div class="stats-row" id="summary-stats"></div>
        </div>

        <div class="card wide" id="confidenceCard" style="display:none">
            <h3>🎯 Race Readiness Confidence Trajectory (5-Model AI Consensus)</h3>
            <canvas id="confidenceChart"></canvas>
        </div>

        <div class="card">
            <h3>📊 Weekly Running Mileage</h3>
            <canvas id="weeklyMileage"></canvas>
        </div>

        <div class="card">
            <h3>🏃 Long Run Progression</h3>
            <canvas id="longRuns"></canvas>
        </div>

        <div class="card">
            <h3>❤️ Resting Heart Rate</h3>
            <canvas id="restingHR"></canvas>
        </div>

        <div class="card">
            <h3>⏱️ Run Pace Trend</h3>
            <canvas id="runPace"></canvas>
        </div>

        <div class="card" id="weatherCard" style="display:none">
            <h3>🌤️ Run Weather & Temperature</h3>
            <canvas id="runWeather"></canvas>
        </div>

        <div class="card" id="tempHrCard" style="display:none">
            <h3>🌡️❤️ Temperature vs Avg Heart Rate Over Training</h3>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:0.8rem;color:#8b949e">
                <span>Early training</span>
                <div style="width:120px;height:10px;border-radius:5px;background:linear-gradient(to right,#3b82f6,#8b5cf6,#ec4899,#f97316)"></div>
                <span>Race week</span>
                <span style="margin-left:12px">● Size = distance</span>
            </div>
            <canvas id="tempHrScatter"></canvas>
        </div>

        <div class="card">
            <h3>💤 Sleep Duration & Efficiency</h3>
            <canvas id="sleep"></canvas>
        </div>

        <div class="card">
            <h3>🏃🏋️ Weekly Running & Cross-Training (minutes)</h3>
            <canvas id="crossTraining"></canvas>
        </div>

        <div class="card">
            <h3>❤️ Running HR Zones</h3>
            <canvas id="hrZones"></canvas>
        </div>

        <div class="card">
            <h3>⚖️ Weight Trend (lbs)</h3>
            <canvas id="weight"></canvas>
        </div>

        <div class="card">
            <h3>🔥 Weekly Calorie Burn (all activities)</h3>
            <canvas id="weeklyCalories"></canvas>
        </div>

        <div class="card wide" id="splits-section" style="display:none">
            <h3>⏱️ Mile Splits — Latest Run</h3>
            <canvas id="recentSplits"></canvas>
        </div>

        <div class="card" id="comparison-section" style="display:none">
            <h3>📊 Pace by Mile (Recent Runs)</h3>
            <canvas id="splitComparison"></canvas>
        </div>

        <div class="card" id="hrdrift-section" style="display:none">
            <h3>❤️ HR Drift by Mile (Recent Runs)</h3>
            <canvas id="hrDrift"></canvas>
        </div>

        <div class="card wide" id="consistency-section" style="display:none">
            <h3>🎯 Pace Consistency Trend (lower = more consistent)</h3>
            <canvas id="consistencyTrend"></canvas>
        </div>
    </div>

    <script>
    const data = {data_json};

    Chart.defaults.color = '#8b949e';
    Chart.defaults.borderColor = '#30363d';
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';

    // Pace formatting helper: converts decimal min/mi (e.g., 12.78) to MM:SS string
    function fmtPace(v) {{
        if (v == null || typeof v !== 'number' || !Number.isFinite(v) || v < 0) return '';
        const totalSeconds = Math.round(v * 60);
        const m = Math.floor(totalSeconds / 60);
        const s = totalSeconds % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }}

    // Summary stats
    const totalMiles = data.weekly_mileage.values.reduce((a, b) => a + b, 0);
    const totalRuns = data.run_pace.labels.length;
    const totalXTMin = data.cross_training.cross_training.reduce((a, b) => (a || 0) + (b || 0), 0);
    const longestRun = Math.max(...(data.long_runs.values.length ? data.long_runs.values : [0]));
    const avgPace = data.run_pace.values.length ? data.run_pace.values.reduce((a, b) => a + b, 0) / data.run_pace.values.length : 0;

    document.getElementById('summary-stats').innerHTML = `
        <div class="stat-box"><div class="value">${{totalRuns}}</div><div class="label">Total Runs</div></div>
        <div class="stat-box"><div class="value">${{totalMiles.toFixed(1)}}</div><div class="label">Total Miles</div></div>
        <div class="stat-box"><div class="value">${{longestRun.toFixed(1)}}</div><div class="label">Longest Run (mi)</div></div>
        <div class="stat-box"><div class="value">${{fmtPace(avgPace)}}</div><div class="label">Avg Pace/mi</div></div>
        <div class="stat-box"><div class="value">${{Math.round(totalXTMin)}}</div><div class="label">Cross-Training (min)</div></div>
    `;

    function shortLabel(dateStr) {{
        const d = new Date(dateStr + 'T00:00:00');
        return d.toLocaleDateString('en-US', {{ month: 'short', day: 'numeric' }});
    }}

    // Confidence Trajectory
    if (data.confidence && data.confidence.has_data) {{
        document.getElementById('confidenceCard').style.display = '';
        const confColors = ['#58a6ff', '#f0883e', '#a371f7', '#7ee787', '#f85149'];
        const confDatasets = data.confidence.models.map((model, i) => ({{
            label: model,
            data: data.confidence.model_series[model],
            borderColor: confColors[i % confColors.length],
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 2,
            tension: 0.3,
            fill: false,
        }}));
        confDatasets.unshift({{
            label: 'Consensus',
            data: data.confidence.consensus,
            borderColor: '#ffffff',
            borderWidth: 3,
            pointRadius: 5,
            pointBackgroundColor: data.confidence.consensus.map(v =>
                v >= 7 ? '#7ee787' : v >= 5 ? '#ffa657' : '#f85149'),
            tension: 0.3,
            fill: false,
        }});
        new Chart(document.getElementById('confidenceChart'), {{
            type: 'line',
            data: {{
                labels: data.confidence.dates.map(shortLabel),
                datasets: confDatasets,
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 10 }} }} }},
                    tooltip: {{
                        callbacks: {{
                            label: function(ctx) {{
                                return ctx.dataset.label + ': ' + ctx.raw + '/10';
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        min: 0, max: 10,
                        title: {{ display: true, text: 'Confidence (1-10)' }},
                        ticks: {{ stepSize: 1 }},
                    }}
                }}
            }}
        }});
    }}

    // Weekly Mileage
    new Chart(document.getElementById('weeklyMileage'), {{
        type: 'bar',
        data: {{
            labels: data.weekly_mileage.labels.map(shortLabel),
            datasets: [{{
                label: 'Miles',
                data: data.weekly_mileage.values,
                backgroundColor: '#238636',
                borderRadius: 4,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Miles' }} }} }}
        }}
    }});

    // Long Runs
    new Chart(document.getElementById('longRuns'), {{
        type: 'line',
        data: {{
            labels: data.long_runs.labels.map(shortLabel),
            datasets: [{{
                label: 'Longest Run (mi)',
                data: data.long_runs.values,
                borderColor: '#f0883e',
                backgroundColor: 'rgba(240,136,62,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 5,
                pointBackgroundColor: '#f0883e',
            }},
            {{
                label: 'Race Distance (13.1)',
                data: Array(data.long_runs.labels.length).fill(13.1),
                borderColor: '#f85149',
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
            }}]
        }},
        options: {{
            responsive: true,
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Miles' }}, max: 14 }} }}
        }}
    }});

    // Resting HR
    new Chart(document.getElementById('restingHR'), {{
        type: 'line',
        data: {{
            labels: data.resting_hr.labels.map(shortLabel),
            datasets: [{{
                label: 'Resting HR (bpm)',
                data: data.resting_hr.values,
                borderColor: '#f85149',
                backgroundColor: 'rgba(248,81,73,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ title: {{ display: true, text: 'BPM' }} }} }}
        }}
    }});

    // Run Pace
    new Chart(document.getElementById('runPace'), {{
        type: 'line',
        data: {{
            labels: data.run_pace.labels.map(shortLabel),
            datasets: [{{
                label: 'Pace (min/mi)',
                data: data.run_pace.values,
                borderColor: '#a371f7',
                backgroundColor: 'rgba(163,113,247,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: '#a371f7',
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    callbacks: {{
                        label: function(ctx) {{
                            return fmtPace(ctx.raw) + '/mi';
                        }}
                    }}
                }}
            }},
            scales: {{
                y: {{
                    title: {{ display: true, text: 'min/mi (lower is faster)' }},
                    ticks: {{
                        callback: function(v) {{
                            return fmtPace(v);
                        }}
                    }}
                }}
            }}
        }}
    }});

    // Sleep
    new Chart(document.getElementById('sleep'), {{
        type: 'line',
        data: {{
            labels: data.sleep.labels.map(shortLabel),
            datasets: [{{
                label: 'Duration (hrs)',
                data: data.sleep.duration_hrs,
                borderColor: '#79c0ff',
                tension: 0.3,
                pointRadius: 2,
                yAxisID: 'y',
            }},
            {{
                label: 'Efficiency (%)',
                data: data.sleep.efficiency,
                borderColor: '#7ee787',
                tension: 0.3,
                pointRadius: 2,
                yAxisID: 'y1',
            }}]
        }},
        options: {{
            responsive: true,
            interaction: {{ mode: 'index', intersect: false }},
            scales: {{
                y: {{ type: 'linear', position: 'left', title: {{ display: true, text: 'Hours' }} }},
                y1: {{ type: 'linear', position: 'right', title: {{ display: true, text: '%' }}, min: 70, max: 100, grid: {{ drawOnChartArea: false }} }}
            }}
        }}
    }});

    // Cross-Training & Running
    new Chart(document.getElementById('crossTraining'), {{
        type: 'bar',
        data: {{
            labels: data.cross_training.labels.map(shortLabel),
            datasets: [
                {{
                    label: 'Running',
                    data: data.cross_training.running,
                    backgroundColor: '#238636',
                    borderRadius: 4,
                }},
                {{
                    label: 'Cross-Training',
                    data: data.cross_training.cross_training,
                    backgroundColor: '#1f6feb',
                    borderRadius: 4,
                }}
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 12 }} }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Minutes' }} }} }}
        }}
    }});

    // HR Zones (weekly stacked bar)
    const hrZoneColors = ['#58a6ff', '#f0c33e', '#f0883e', '#f85149'];
    const hrZoneDatasets = Object.entries(data.hr_zones.datasets).map(([label, values], i) => ({{
        label: label,
        data: values,
        backgroundColor: hrZoneColors[i % hrZoneColors.length],
        borderRadius: 2,
    }}));
    new Chart(document.getElementById('hrZones'), {{
        type: 'bar',
        data: {{
            labels: data.hr_zones.labels.map(shortLabel),
            datasets: hrZoneDatasets,
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }},
                tooltip: {{
                    callbacks: {{
                        label: function(ctx) {{
                            return ctx.dataset.label + ': ' + ctx.raw + ' min';
                        }}
                    }}
                }}
            }},
            scales: {{
                x: {{ stacked: true }},
                y: {{ stacked: true, beginAtZero: true, title: {{ display: true, text: 'Minutes' }} }}
            }}
        }}
    }});

    // Weight
    if (data.weight.values.length > 0) {{
        new Chart(document.getElementById('weight'), {{
            type: 'line',
            data: {{
                labels: data.weight.labels.map(shortLabel),
                datasets: [{{
                    label: 'Weight (lbs)',
                    data: data.weight.values,
                    borderColor: '#d2a8ff',
                    backgroundColor: 'rgba(210,168,255,0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointBackgroundColor: '#d2a8ff',
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ title: {{ display: true, text: 'lbs' }} }} }}
            }}
        }});
    }} else {{
        document.getElementById('weight').parentElement.innerHTML += '<p style="text-align:center;color:#8b949e;padding:40px;">No weight data available</p>';
    }}

    // Weekly Calories
    new Chart(document.getElementById('weeklyCalories'), {{
        type: 'bar',
        data: {{
            labels: data.weekly_calories.labels.map(shortLabel),
            datasets: [{{
                label: 'Calories',
                data: data.weekly_calories.values,
                backgroundColor: '#f0883e',
                borderRadius: 4,
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Calories' }} }} }}
        }}
    }});

    // --- Workout Splits Charts ---
    if (data.workout_splits && data.workout_splits.has_data) {{

        // Recent Splits bar chart
        const rs = data.workout_splits.recent_splits;
        if (rs) {{
            document.getElementById('splits-section').style.display = '';
            const barColors = rs.paces.map(p => p !== null && p < rs.avg_pace ? '#7ee787' : '#f85149');
            new Chart(document.getElementById('recentSplits'), {{
                type: 'bar',
                data: {{
                    labels: rs.labels,
                    datasets: [{{
                        label: 'Pace (min/mi)',
                        data: rs.paces,
                        backgroundColor: barColors,
                        borderRadius: 4,
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{ display: false }},
                        title: {{ display: true, text: 'Run on ' + rs.date + ' | Avg: ' + fmtPace(rs.avg_pace) + '/mi', color: '#8b949e' }},
                        tooltip: {{
                            callbacks: {{
                                label: function(ctx) {{
                                    return fmtPace(ctx.raw) + '/mi';
                                }}
                            }}
                        }}
                    }},
                    scales: {{ y: {{
                        title: {{ display: true, text: 'min/mi' }},
                        ticks: {{ callback: function(v) {{ return fmtPace(v); }} }}
                    }} }}
                }}
            }});
        }}

        // Split Comparison line chart
        const sc = data.workout_splits.split_comparison;
        if (sc && sc.runs.length > 0) {{
            document.getElementById('comparison-section').style.display = '';
            const colors = ['#58a6ff','#f0883e','#7ee787','#d2a8ff','#f85149','#79c0ff','#ffa657','#a5d6ff'];
            new Chart(document.getElementById('splitComparison'), {{
                type: 'line',
                data: {{
                    labels: sc.mile_labels,
                    datasets: sc.runs.map((run, i) => ({{
                        label: run.date,
                        data: run.paces,
                        borderColor: colors[i % colors.length],
                        tension: 0.3,
                        pointRadius: 4,
                        spanGaps: true,
                    }}))
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }},
                        tooltip: {{
                            callbacks: {{
                                label: function(ctx) {{
                                    return ctx.dataset.label + ': ' + fmtPace(ctx.raw) + '/mi';
                                }}
                            }}
                        }}
                    }},
                    scales: {{ y: {{
                        title: {{ display: true, text: 'min/mi' }},
                        ticks: {{ callback: function(v) {{ return fmtPace(v); }} }}
                    }} }}
                }}
            }});
        }}

        // HR Drift line chart
        const hd = data.workout_splits.hr_drift;
        if (hd && hd.runs.length > 0) {{
            document.getElementById('hrdrift-section').style.display = '';
            const colors = ['#58a6ff','#f0883e','#7ee787','#d2a8ff','#f85149','#79c0ff','#ffa657','#a5d6ff'];
            new Chart(document.getElementById('hrDrift'), {{
                type: 'line',
                data: {{
                    labels: hd.mile_labels,
                    datasets: hd.runs.map((run, i) => ({{
                        label: run.date,
                        data: run.hrs,
                        borderColor: colors[i % colors.length],
                        tension: 0.3,
                        pointRadius: 4,
                        spanGaps: true,
                    }}))
                }},
                options: {{
                    responsive: true,
                    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }} }},
                    scales: {{ y: {{ title: {{ display: true, text: 'BPM' }} }} }}
                }}
            }});
        }}

        // Consistency Trend line chart
        const ct = data.workout_splits.consistency_trend;
        if (ct && ct.labels.length > 0) {{
            document.getElementById('consistency-section').style.display = '';
            new Chart(document.getElementById('consistencyTrend'), {{
                type: 'line',
                data: {{
                    labels: ct.labels.map(shortLabel),
                    datasets: [{{
                        label: 'Pace CV%',
                        data: ct.values,
                        borderColor: '#d2a8ff',
                        backgroundColor: 'rgba(210,168,255,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 5,
                        pointBackgroundColor: '#d2a8ff',
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'CV% (lower = more consistent)' }} }} }}
                }}
            }});
        }}
    }}

    // Run Weather chart
    if (data.run_weather && data.run_weather.has_data) {{
        document.getElementById('weatherCard').style.display = '';
        const skyColors = data.run_weather.sky_conditions.map(s => {{
            if (s === 'Sunny') return '#f0c040';
            if (s === 'Partly Cloudy') return '#90cdf4';
            if (s === 'Mostly Cloudy') return '#718096';
            return '#4a5568';
        }});
        const precipBorders = data.run_weather.precip_types.map(p => {{
            if (p === 'None') return 'rgba(0,0,0,0)';
            return '#3182ce';
        }});
        new Chart(document.getElementById('runWeather'), {{
            type: 'bar',
            data: {{
                labels: data.run_weather.dates.map(shortLabel),
                datasets: [
                    {{
                        type: 'line',
                        label: 'Temperature (°F)',
                        data: data.run_weather.temps,
                        borderColor: '#e53e3e',
                        backgroundColor: 'rgba(229,62,62,0.1)',
                        fill: false,
                        tension: 0.3,
                        yAxisID: 'y',
                        pointRadius: 5,
                        pointBackgroundColor: skyColors,
                        pointBorderColor: precipBorders,
                        pointBorderWidth: 2,
                        order: 1,
                    }},
                    {{
                        type: 'bar',
                        label: 'Distance (mi)',
                        data: data.run_weather.distances,
                        backgroundColor: skyColors.map(c => c + '80'),
                        borderColor: precipBorders,
                        borderWidth: 1,
                        yAxisID: 'y1',
                        order: 2,
                    }}
                ]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    tooltip: {{
                        callbacks: {{
                            afterLabel: function(ctx) {{
                                const i = ctx.dataIndex;
                                const sky = data.run_weather.sky_conditions[i];
                                const precip = data.run_weather.precip_types[i];
                                return sky + (precip !== 'None' ? ' / ' + precip : '');
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        position: 'left',
                        title: {{ display: true, text: 'Temperature (°F)' }},
                    }},
                    y1: {{
                        position: 'right',
                        title: {{ display: true, text: 'Distance (mi)' }},
                        grid: {{ drawOnChartArea: false }},
                    }}
                }}
            }}
        }});
    }}

    // Temperature vs Avg Heart Rate scatter chart (color = training timeline)
    if (data.run_weather && data.run_weather.has_data && data.run_weather.avg_heart_rates) {{
        const hrPoints = [];
        for (let i = 0; i < data.run_weather.temps.length; i++) {{
            if (data.run_weather.avg_heart_rates[i] > 0) {{
                hrPoints.push({{
                    x: data.run_weather.temps[i],
                    y: data.run_weather.avg_heart_rates[i],
                    date: data.run_weather.dates[i],
                    distance: data.run_weather.distances[i],
                    sky: data.run_weather.sky_conditions[i],
                }});
            }}
        }}
        if (hrPoints.length > 0) {{
            document.getElementById('tempHrCard').style.display = '';

            // Compute time progression (0 = earliest run, 1 = latest run)
            const timestamps = hrPoints.map(p => new Date(p.date).getTime());
            const minTs = Math.min(...timestamps);
            const maxTs = Math.max(...timestamps);
            const tsRange = maxTs - minTs || 1;
            const progress = timestamps.map(t => (t - minTs) / tsRange);

            // Color gradient: blue (#3b82f6) → purple (#8b5cf6) → pink (#ec4899) → orange (#f97316)
            function timeColor(t) {{
                const stops = [
                    [0.0, [59, 130, 246]],
                    [0.33, [139, 92, 246]],
                    [0.66, [236, 72, 153]],
                    [1.0, [249, 115, 22]],
                ];
                let lo = stops[0], hi = stops[stops.length - 1];
                for (let s = 0; s < stops.length - 1; s++) {{
                    if (t >= stops[s][0] && t <= stops[s + 1][0]) {{
                        lo = stops[s]; hi = stops[s + 1]; break;
                    }}
                }}
                const f = (hi[0] - lo[0]) > 0 ? (t - lo[0]) / (hi[0] - lo[0]) : 0;
                const r = Math.round(lo[1][0] + f * (hi[1][0] - lo[1][0]));
                const g = Math.round(lo[1][1] + f * (hi[1][1] - lo[1][1]));
                const b = Math.round(lo[1][2] + f * (hi[1][2] - lo[1][2]));
                return `rgb(${{r}},${{g}},${{b}})`;
            }}

            const timeColors = progress.map(t => timeColor(t));
            // Point size scaled by distance (min 5, max 16)
            const dists = hrPoints.map(p => p.distance);
            const minDist = Math.min(...dists);
            const maxDist = Math.max(...dists);
            const distRange = maxDist - minDist || 1;
            const pointSizes = dists.map(d => 5 + 11 * ((d - minDist) / distRange));

            // Trend line via simple linear regression
            const n = hrPoints.length;
            const sumX = hrPoints.reduce((s, p) => s + p.x, 0);
            const sumY = hrPoints.reduce((s, p) => s + p.y, 0);
            const sumXY = hrPoints.reduce((s, p) => s + p.x * p.y, 0);
            const sumX2 = hrPoints.reduce((s, p) => s + p.x * p.x, 0);
            const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
            const intercept = (sumY - slope * sumX) / n;
            const minTemp = Math.min(...hrPoints.map(p => p.x));
            const maxTemp = Math.max(...hrPoints.map(p => p.x));
            const trendData = [
                {{ x: minTemp, y: slope * minTemp + intercept }},
                {{ x: maxTemp, y: slope * maxTemp + intercept }},
            ];

            // Week label helper
            function weekLabel(dateStr) {{
                const d = new Date(dateStr);
                return d.toLocaleDateString('en-US', {{ month: 'short', day: 'numeric' }});
            }}

            new Chart(document.getElementById('tempHrScatter'), {{
                type: 'scatter',
                data: {{
                    datasets: [
                        {{
                            label: 'Avg HR (bpm)',
                            data: hrPoints,
                            backgroundColor: timeColors,
                            borderColor: timeColors.map(c => c.replace('rgb', 'rgba').replace(')', ',0.7)')),
                            pointRadius: pointSizes,
                            pointHoverRadius: pointSizes.map(s => s + 3),
                        }},
                        {{
                            label: 'Trend',
                            type: 'line',
                            data: trendData,
                            borderColor: 'rgba(255,255,255,0.3)',
                            borderDash: [6, 4],
                            borderWidth: 2,
                            pointRadius: 0,
                            fill: false,
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        tooltip: {{
                            callbacks: {{
                                label: function(ctx) {{
                                    const p = ctx.raw;
                                    if (!p.date) return `HR: ${{p.y}} bpm`;
                                    return [
                                        `${{weekLabel(p.date)}} (${{p.date}})`,
                                        `${{p.y}} bpm · ${{Math.round(p.x)}}°F · ${{p.distance}} mi`,
                                        `${{p.sky}}`
                                    ];
                                }}
                            }}
                        }},
                        legend: {{ display: false }},
                    }},
                    scales: {{
                        x: {{
                            title: {{ display: true, text: 'Temperature (°F)' }},
                        }},
                        y: {{
                            title: {{ display: true, text: 'Avg Heart Rate (bpm)' }},
                        }}
                    }}
                }}
            }});
        }}
    }}
    </script>
</body>
</html>"""


def _get_activities_page_data(conn):
    """Get all data needed for the activities page."""
    rows = conn.execute(
        "SELECT date, activity_name, distance, duration_ms, calories, avg_heart_rate, data "
        "FROM activities WHERE date >= ? ORDER BY date DESC",
        (DATA_START_DATE,)
    ).fetchall()

    # Load weather data
    weather_map = {}
    try:
        weather_rows = conn.execute(
            "SELECT log_id, avg_temp_f, sky_condition, precip_type, total_precip_in, location_name "
            "FROM run_weather WHERE date >= ?", (DATA_START_DATE,)
        ).fetchall()
        weather_map = {r["log_id"]: dict(r) for r in weather_rows}
    except Exception:
        pass

    activities = []
    type_calories = defaultdict(int)
    type_count = defaultdict(int)
    type_miles = defaultdict(float)
    day_of_week_count = defaultdict(int)
    monthly_calories = defaultdict(lambda: defaultdict(int))
    monthly_miles = defaultdict(float)

    for r in rows:
        act = json.loads(r["data"])
        name = r["activity_name"] or "Unknown"
        dist = r["distance"] or 0
        unit = act.get("distanceUnit", "")
        if "kilometer" in unit.lower() or "km" in unit.lower():
            dist = dist * KM_TO_MILES
        dur_min = (r["duration_ms"] or 0) / 60000
        cal = r["calories"] or 0
        hr = r["avg_heart_rate"] or 0
        log_id = act.get("logId")

        entry = {
            "date": r["date"],
            "name": name,
            "distance_mi": round(dist, 2),
            "duration_min": round(dur_min, 1),
            "calories": cal,
            "avg_hr": hr,
        }

        # Attach weather if available
        w = weather_map.get(log_id)
        if w:
            entry["temp_f"] = w.get("avg_temp_f")
            entry["sky"] = w.get("sky_condition", "")
            entry["precip"] = w.get("precip_type") or ""
            entry["location"] = w.get("location_name", "")
        else:
            entry["temp_f"] = None
            entry["sky"] = ""
            entry["precip"] = ""
            entry["location"] = ""

        activities.append(entry)

        type_calories[name] += cal
        type_count[name] += 1
        type_miles[name] += dist

        if r["date"]:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
            dow = d.strftime("%A")
            day_of_week_count[dow] += 1
            month_key = d.strftime("%Y-%m")
            monthly_calories[month_key][name] += cal
            if "run" in name.lower() or "jog" in name.lower():
                monthly_miles[month_key] += dist

    # Sort types by total calories
    sorted_types = sorted(type_calories.items(), key=lambda x: x[1], reverse=True)

    # Miles by type (only types with distance > 0)
    sorted_miles = sorted(type_miles.items(), key=lambda x: x[1], reverse=True)
    sorted_miles = [(t, round(m, 1)) for t, m in sorted_miles if m > 0]

    # Monthly miles (running only)
    months = sorted(monthly_calories.keys())
    monthly_miles_data = {"labels": months, "values": [round(monthly_miles.get(m, 0), 1) for m in months]}

    # Monthly stacked data
    top_types = [t[0] for t in sorted_types[:5]]
    monthly_stacked = {
        "labels": months,
        "datasets": {},
    }
    for t in top_types:
        monthly_stacked["datasets"][t] = [monthly_calories[m].get(t, 0) for m in months]

    # Day of week ordered
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_data = {"labels": dow_order, "values": [day_of_week_count.get(d, 0) for d in dow_order]}

    return {
        "activities": activities,
        "type_calories": {"labels": [t[0] for t in sorted_types], "values": [t[1] for t in sorted_types]},
        "type_count": {"labels": [t[0] for t in sorted_types], "values": [type_count[t[0]] for t in sorted_types]},
        "type_miles": {"labels": [t[0] for t in sorted_miles], "values": [t[1] for t in sorted_miles]},
        "day_of_week": dow_data,
        "monthly_stacked": monthly_stacked,
        "monthly_miles": monthly_miles_data,
    }


def _build_activities_html(data):
    """Build the activities HTML page."""
    data_json = json.dumps(data, default=str)

    # Weather icon mapping
    _sky_icons = {
        "Sunny": "☀️", "Partly Cloudy": "⛅", "Mostly Cloudy": "🌥️", "Overcast": "☁️",
    }
    _precip_icons = {
        "Rain": "🌧️", "Heavy Rain": "🌧️", "Rain Showers": "🌧️", "Heavy Rain Showers": "🌧️",
        "Drizzle": "🌦️", "Freezing Drizzle": "🌨️", "Freezing Rain": "🌨️",
        "Snow": "🌨️", "Heavy Snow": "🌨️", "Snow Showers": "🌨️", "Heavy Snow Showers": "🌨️",
        "Snow Grains": "🌨️",
        "Thunderstorm": "⛈️", "Thunderstorm w/ Hail": "⛈️",
    }

    # Build activity table rows
    table_rows = ""
    for a in data["activities"]:
        dist_str = f'{a["distance_mi"]}' if a["distance_mi"] > 0 else "—"
        hr_str = str(a["avg_hr"]) if a["avg_hr"] > 0 else "—"
        temp_str = f'{a["temp_f"]:.0f}°F' if a.get("temp_f") is not None else ""

        # Weather icon with tooltip
        sky = a.get("sky", "")
        precip = a.get("precip", "")
        if precip and precip in _precip_icons:
            icon = _precip_icons[precip]
            tooltip = f"{sky}, {precip}"
        elif sky and sky in _sky_icons:
            icon = _sky_icons[sky]
            tooltip = sky
        else:
            icon = ""
            tooltip = ""

        if icon:
            weather_cell = f'<span title="{tooltip} {temp_str}">{icon} {temp_str}</span>'
        else:
            weather_cell = "—"

        location_str = a.get("location", "") or "—"
        table_rows += (
            f'<tr><td>{a["date"]}</td><td>{a["name"]}</td>'
            f'<td>{dist_str}</td><td>{a["duration_min"]}</td>'
            f'<td>{a["calories"]:,}</td><td>{hr_str}</td>'
            f'<td>{weather_cell}</td><td>{location_str}</td></tr>\n'
        )

    # Monthly stacked dataset JS
    stacked_colors = ["#238636", "#1f6feb", "#f0883e", "#a371f7", "#f85149",
                      "#7ee787", "#79c0ff", "#d2a8ff"]
    stacked_datasets = ""
    for i, (name, values) in enumerate(data["monthly_stacked"]["datasets"].items()):
        color = stacked_colors[i % len(stacked_colors)]
        vals_json = json.dumps(values)
        stacked_datasets += f"""{{
            label: '{name}',
            data: {vals_json},
            backgroundColor: '{color}',
            borderRadius: 2,
        }},\n"""

    monthly_labels = json.dumps(data["monthly_stacked"]["labels"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📋 Activities — {RACE_NAME}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 20px;
        }}
        h1 {{ text-align: center; color: #58a6ff; margin-bottom: 4px; font-size: 1.8rem; }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 8px; font-size: 0.95rem; }}
        nav {{ text-align: center; margin-bottom: 20px; }}
        nav a {{ color: #58a6ff; text-decoration: none; font-size: 0.95rem; }}
        nav a:hover {{ text-decoration: underline; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .grid {{
            display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 20px;
        }}
        .card {{
            background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px;
        }}
        .card.wide {{ grid-column: span 2; }}
        .card h3 {{ color: #58a6ff; margin-bottom: 12px; font-size: 1.1rem; }}
        canvas {{ width: 100% !important; max-height: 300px; }}
        table.activity-log {{
            width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 8px;
        }}
        table.activity-log th {{
            background: #21262d; color: #8b949e; text-align: left;
            padding: 8px 10px; border-bottom: 2px solid #30363d;
            position: sticky; top: 0; cursor: pointer;
        }}
        table.activity-log th:hover {{ color: #58a6ff; }}
        table.activity-log td {{ padding: 6px 10px; border-bottom: 1px solid #21262d; }}
        table.activity-log tbody tr:hover {{ background: #1c2128; }}
        .table-wrap {{
            max-height: 500px; overflow-y: auto; border-radius: 8px;
            border: 1px solid #30363d;
        }}
        .filter-bar {{
            display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
        }}
        .filter-bar input, .filter-bar select {{
            background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
            border-radius: 6px; padding: 6px 12px; font-size: 0.85rem;
        }}
        .filter-bar input::placeholder {{ color: #484f58; }}
        .stats-row {{
            display: flex; justify-content: space-around; text-align: center; padding: 12px 0;
        }}
        .stat-box .value {{ font-size: 1.6rem; font-weight: bold; color: #58a6ff; }}
        .stat-box .label {{ color: #8b949e; font-size: 0.8rem; }}
        @media (max-width: 768px) {{
            .grid {{ grid-template-columns: 1fr; }}
            .card.wide {{ grid-column: span 1; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 All Activities</h1>
        <p class="subtitle">{RACE_NAME} Training · Data from {DATA_START_DATE} · Generated {date.today().isoformat()}</p>
        <nav><a href="dashboard.html">← Back to Dashboard</a></nav>

        <div class="card wide" style="margin-bottom:20px">
            <div class="stats-row" id="activity-summary"></div>
        </div>

        <div class="grid">
            <div class="card">
                <h3>🏃 Miles by Activity Type</h3>
                <canvas id="typeMiles"></canvas>
            </div>
            <div class="card">
                <h3>📊 Monthly Running Miles</h3>
                <canvas id="monthlyMiles"></canvas>
            </div>
            <div class="card">
                <h3>📅 Activities by Day of Week</h3>
                <canvas id="dowChart"></canvas>
            </div>
            <div class="card">
                <h3>🔥 Monthly Calories by Type</h3>
                <canvas id="monthlyStacked"></canvas>
            </div>
        </div>

        <div class="card wide">
            <h3>📋 Activity Log</h3>
            <div class="filter-bar">
                <input type="text" id="searchInput" placeholder="Search activities..." oninput="filterTable()">
                <select id="typeFilter" onchange="filterTable()">
                    <option value="">All Types</option>
                </select>
            </div>
            <div class="table-wrap">
                <table class="activity-log" id="activityTable">
                    <thead><tr>
                        <th onclick="sortTable(0)">Date ↕</th>
                        <th onclick="sortTable(1)">Activity ↕</th>
                        <th onclick="sortTable(2)">Miles ↕</th>
                        <th onclick="sortTable(3)">Duration (min) ↕</th>
                        <th onclick="sortTable(4)">Calories ↕</th>
                        <th onclick="sortTable(5)">Avg HR ↕</th>
                        <th onclick="sortTable(6)">Weather ↕</th>
                        <th onclick="sortTable(7)">Location ↕</th>
                    </tr></thead>
                    <tbody>{table_rows}</tbody>
                </table>
                <p style="color:#8b949e; font-size:0.85em; margin-top:8px;">* Location estimated from default training location</p>
            </div>
        </div>
    </div>

    <script>
    const data = {data_json};

    Chart.defaults.color = '#8b949e';
    Chart.defaults.borderColor = '#30363d';
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';

    // Summary stats
    const totalActs = data.activities.length;
    const totalCal = data.activities.reduce((s, a) => s + a.calories, 0);
    const totalMilesRan = data.activities.filter(a => a.name.toLowerCase().includes('run') || a.name.toLowerCase().includes('jog')).reduce((s, a) => s + a.distance_mi, 0);
    const totalDur = data.activities.reduce((s, a) => s + a.duration_min, 0);

    document.getElementById('activity-summary').innerHTML = `
        <div class="stat-box"><div class="value">${{totalActs}}</div><div class="label">Total Activities</div></div>
        <div class="stat-box"><div class="value">${{totalMilesRan.toFixed(1)}}</div><div class="label">Total Miles Ran</div></div>
        <div class="stat-box"><div class="value">${{totalCal.toLocaleString()}}</div><div class="label">Total Calories</div></div>
        <div class="stat-box"><div class="value">${{Math.round(totalDur).toLocaleString()}}</div><div class="label">Total Minutes</div></div>
    `;

    // Populate type filter dropdown
    const typeFilter = document.getElementById('typeFilter');
    const uniqueTypes = [...new Set(data.activities.map(a => a.name))].sort();
    uniqueTypes.forEach(t => {{
        const opt = document.createElement('option');
        opt.value = t; opt.textContent = t;
        typeFilter.appendChild(opt);
    }});

    const actColors = ['#238636','#1f6feb','#f0883e','#a371f7','#f85149','#7ee787','#79c0ff','#d2a8ff'];

    // Miles by activity type (horizontal bar)
    new Chart(document.getElementById('typeMiles'), {{
        type: 'bar',
        data: {{
            labels: data.type_miles.labels,
            datasets: [{{ label: 'Miles', data: data.type_miles.values, backgroundColor: actColors, borderRadius: 4 }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: 'Miles' }} }} }}
        }}
    }});

    // Monthly running miles
    new Chart(document.getElementById('monthlyMiles'), {{
        type: 'bar',
        data: {{
            labels: data.monthly_miles.labels,
            datasets: [{{ label: 'Miles', data: data.monthly_miles.values, backgroundColor: '#238636', borderRadius: 4 }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Miles' }} }} }}
        }}
    }});

    // Day of week
    new Chart(document.getElementById('dowChart'), {{
        type: 'bar',
        data: {{
            labels: data.day_of_week.labels.map(d => d.slice(0, 3)),
            datasets: [{{ label: 'Activities', data: data.day_of_week.values, backgroundColor: '#58a6ff', borderRadius: 4 }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }}
        }}
    }});

    // Monthly stacked
    new Chart(document.getElementById('monthlyStacked'), {{
        type: 'bar',
        data: {{
            labels: {monthly_labels},
            datasets: [{stacked_datasets}]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }},
                tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.raw.toLocaleString() + ' cal' }} }}
            }},
            scales: {{
                x: {{ stacked: true }},
                y: {{ stacked: true, beginAtZero: true, title: {{ display: true, text: 'Calories' }} }}
            }}
        }}
    }});

    // Table sorting
    let sortCol = -1, sortAsc = true;
    function sortTable(col) {{
        const table = document.getElementById('activityTable');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        if (sortCol === col) sortAsc = !sortAsc; else {{ sortCol = col; sortAsc = true; }}
        rows.sort((a, b) => {{
            let va = a.cells[col].textContent.replace(/[,—]/g, '');
            let vb = b.cells[col].textContent.replace(/[,—]/g, '');
            const na = parseFloat(va), nb = parseFloat(vb);
            if (!isNaN(na) && !isNaN(nb)) return sortAsc ? na - nb : nb - na;
            return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        }});
        rows.forEach(r => tbody.appendChild(r));
    }}

    // Table filtering
    function filterTable() {{
        const search = document.getElementById('searchInput').value.toLowerCase();
        const type = document.getElementById('typeFilter').value;
        const rows = document.querySelectorAll('#activityTable tbody tr');
        rows.forEach(r => {{
            const text = r.textContent.toLowerCase();
            const actType = r.cells[1].textContent;
            const matchSearch = !search || text.includes(search);
            const matchType = !type || actType === type;
            r.style.display = (matchSearch && matchType) ? '' : 'none';
        }});
    }}
    </script>
</body>
</html>"""
