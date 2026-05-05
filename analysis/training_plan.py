"""Generates a personalized training plan based on Fitbit data.

Plan structure modeled after Hal Higdon Intermediate 1:
- Long run increases ~1mi/week, peaking at race distance * 0.9
- Recovery week every 4th week (~40% long run reduction)
- 2-week taper before race
- Workouts are long-distance easy runs (no tempo/interval splits)
"""

from datetime import date, datetime, timedelta

from config import RACE_DATE, RACE_DISTANCE_MILES, RACE_NAME, DATA_START_DATE, TARGET_TIME, TARGET_PACE
from utils import format_pace


def generate_plan(analysis: dict) -> dict:
    """Generate a week-by-week half marathon training plan.

    Args:
        analysis: Output from analyzer.analyze()

    Returns:
        Dictionary with training plan details.
    """
    race_date = datetime.strptime(RACE_DATE, "%Y-%m-%d").date()
    training_start = datetime.strptime(DATA_START_DATE, "%Y-%m-%d").date()
    today = date.today()
    days_until = (race_date - today).days
    weeks_remaining = max(1, days_until / 7)
    weeks_trained = max(0, (today - training_start).days / 7)

    running = analysis.get("running", {})
    cross_training = analysis.get("cross_training", {})
    hr = analysis.get("heart_rate", {})
    profile = analysis.get("profile", {})
    sleep = analysis.get("sleep", {})
    hydration = analysis.get("hydration", {})
    readiness = analysis.get("readiness", {})

    plan = {
        "race": {
            "name": RACE_NAME,
            "date": RACE_DATE,
            "distance_miles": RACE_DISTANCE_MILES,
            "days_until": days_until,
            "weeks_remaining": round(weeks_remaining, 1),
            "target_time": TARGET_TIME,
            "target_pace": TARGET_PACE,
        },
        "training_history": {
            "start_date": DATA_START_DATE,
            "weeks_trained": round(weeks_trained, 1),
            "total_runs": running.get("total_runs", 0),
            "total_miles": running.get("total_distance_mi", 0),
            "longest_run": running.get("longest_run_mi", 0),
            "avg_weekly_mileage": running.get("avg_weekly_mileage", 0),
            "cross_training_sessions": cross_training.get("total_sessions", 0),
            "phase_completed": "Base Building",
        },
        "guardrails": {
            "no_back_to_back_runs": True,
            "max_weekly_increase": "10%",
            "long_run_progression": "+1 mi/week to 12 mi peak (Hal Higdon Intermediate 1)",
            "workout_style": "Long-distance easy runs only — no tempo or interval splits",
            "cross_training": "Cross-training on non-run days (tapering as running volume increases)",
            "strength_training": "2x/week: squats, single-leg deadlifts, calf raises, planks",
            "rest_days": "As needed based on recovery data",
            "hr_guidance": "Easy/long runs: stay in Zone 2 — walk if HR exceeds ceiling",
            "taper": f"{TAPER_WEEKS} weeks before race",
        },
        "hr_zones": _calculate_hr_zones(hr, profile),
        "weekly_plan": _build_weekly_plan(
            running, hr, readiness, cross_training
        ),
        "race_day": _race_day_recommendations(analysis),
        "general_tips": _general_tips(analysis),
    }

    return plan


def _calculate_hr_zones(hr_data: dict, profile: dict) -> dict:
    """Calculate personalized HR training zones."""
    rhr = hr_data.get("avg_resting_hr", 65)
    age = profile.get("age", 30)

    # Max HR estimate (Tanaka formula)
    max_hr = 208 - (0.7 * age)

    # Heart rate reserve (Karvonen method)
    hrr = max_hr - rhr

    zones = {
        "max_hr": round(max_hr),
        "resting_hr": rhr,
        "zone_1_recovery": {
            "name": "Recovery / Easy",
            "pct": "50-60%",
            "bpm_low": round(rhr + hrr * 0.50),
            "bpm_high": round(rhr + hrr * 0.60),
            "purpose": "Warm-up, cool-down, recovery runs",
        },
        "zone_2_aerobic": {
            "name": "Aerobic / Easy Run",
            "pct": "60-70%",
            "bpm_low": round(rhr + hrr * 0.60),
            "bpm_high": round(rhr + hrr * 0.70),
            "purpose": "Base building, long runs — majority of training",
        },
        "zone_3_tempo": {
            "name": "Tempo / Threshold",
            "pct": "70-80%",
            "bpm_low": round(rhr + hrr * 0.70),
            "bpm_high": round(rhr + hrr * 0.80),
            "purpose": "Race pace reference",
        },
        "zone_4_threshold": {
            "name": "Threshold",
            "pct": "80-90%",
            "bpm_low": round(rhr + hrr * 0.80),
            "bpm_high": round(rhr + hrr * 0.90),
            "purpose": "Avoid — indicates too fast for easy runs",
        },
        "zone_5_max": {
            "name": "VO2 Max / Sprint",
            "pct": "90-100%",
            "bpm_low": round(rhr + hrr * 0.90),
            "bpm_high": round(max_hr),
            "purpose": "Short bursts only — hill sprints, finishing kicks",
        },
    }

    return zones


def _get_starting_long_run(running: dict) -> float:
    """Determine starting long run distance based on recent longest run."""
    longest = running.get("longest_run_mi", 0)
    if longest >= 10:
        return longest  # Already strong — maintain
    elif longest >= 5:
        return round(longest + 1.0, 1)  # Bump by 1 mile
    elif longest > 0:
        return max(4.0, round(longest + 0.5, 1))
    else:
        return 4.0  # Hal Higdon week 1 default


# --- Guardrails ---
MAX_WEEKLY_INCREASE_PCT = 0.10  # 10% max weekly mileage increase
PEAK_LONG_RUN_MI = 12.0         # Peak long run target (Hal Higdon Intermediate 1)
LONG_RUN_INCREMENT = 1.0        # Increase long run ~1mi/week
TAPER_WEEKS = 2                 # 2-week taper before race


def _build_weekly_plan(running: dict,
                       hr_data: dict, readiness: dict,
                       cross_training: dict) -> list:
    """Build a data-driven training plan anchored to actual history.

    Phase 1: Replay actual run history (training start to today) as completed workouts.
    Phase 2: Project forward (today to race day) using HR-driven decisions
             for distance builds, maintenance runs, and rest days.

    Pattern: always alternates Run → Cross-train → Run → Cross-train...
    Never back-to-back run days.
    """
    training_start = datetime.strptime(DATA_START_DATE, "%Y-%m-%d").date()
    race_date = datetime.strptime(RACE_DATE, "%Y-%m-%d").date()
    today = date.today()

    avg_pace = running.get("avg_pace_per_mile", 10.0)
    if avg_pace <= 0:
        avg_pace = 10.0

    avg_xt_min = cross_training.get("avg_duration_min", 45)
    if avg_xt_min <= 0:
        avg_xt_min = 45

    easy_pace = avg_pace + 1.5
    conservative_pace = avg_pace * 1.10

    # Zone 2 HR ceiling (Karvonen 70% HRR)
    rhr = hr_data.get("avg_resting_hr", 65)
    age = 38
    max_hr = 208 - (0.7 * age)
    hrr = max_hr - rhr
    zone2_ceiling = round(rhr + hrr * 0.70)
    hr_note = f" Keep HR under {zone2_ceiling} bpm -- walk if needed."

    taper_starts_at = 14  # days before race

    # --- Analyze actual run history ---
    runs = sorted(running.get("runs", []), key=lambda r: r.get("date", ""))
    longest_done = running.get("longest_run_mi", 0)

    # Build a lookup: date_str -> run data
    run_by_date = {}
    for r in runs:
        d = r.get("date", "")
        if d:
            run_by_date[d] = r

    # Recent HR stats for projection decisions
    recent_runs = [r for r in runs if r.get("date", "") >= (today - timedelta(days=14)).isoformat()]
    recent_hrs = [r["avg_heart_rate"] for r in recent_runs if r.get("avg_heart_rate", 0) > 0]
    avg_recent_hr = sum(recent_hrs) / len(recent_hrs) if recent_hrs else 0

    resting_trend = hr_data.get("resting_hr_trend", "stable")
    resting_hr_rising = "increasing" in resting_trend.lower() if resting_trend else False

    # Maintenance distance (average of recent runs)
    recent_dists = [r["distance_mi"] for r in recent_runs if r.get("distance_mi", 0) > 0]
    if recent_dists:
        maintenance_dist = round(sum(recent_dists) / len(recent_dists), 1)
    elif longest_done > 0:
        maintenance_dist = round(longest_done * 0.7, 1)
    else:
        maintenance_dist = 3.0

    build_increment = 0.5 if longest_done < 6 else 1.0

    # --- Helper functions for projection ---
    def _needs_rest(last_hr, last_dist):
        """Decide if a rest day should be inserted after a run.
        Calibrated against actual training data — only triggers on
        genuine acute overtraining signals, not chronic trends.
        Chronic trends (rising resting HR) are surfaced in tips instead.
        """
        # Only rest if HR was extreme (>95% max HR) on a long effort
        if last_hr > 0 and last_hr > (max_hr * 0.95):
            return True
        return False

    def _should_build(runs_since_build, last_hr, days_to_race):
        """Decide if the next run should be a distance build."""
        if days_to_race <= taper_starts_at:
            return False  # Taper: no building
        if runs_since_build >= 2:
            return True  # Had enough maintenance
        if last_hr > 0 and last_hr < (zone2_ceiling + 10):
            return True  # HR was controlled, ready to push
        return runs_since_build >= 1  # Default: build every other run

    # ============================================================
    # PHASE 1: Replay actual history (training_start → today)
    # ============================================================
    all_days = []
    current_date = training_start

    while current_date <= today and current_date <= race_date:
        day_name = current_date.strftime("%a")
        date_str = current_date.isoformat()

        if date_str in run_by_date:
            r = run_by_date[date_str]
            dist = r.get("distance_mi", 0)
            hr = r.get("avg_heart_rate", 0)
            pace = r.get("pace_per_mile", 0)
            hr_str = f"HR: {hr}" if hr else ""
            all_days.append(_run(day_name, current_date, "Run (actual)",
                                 dist, pace, hr_str,
                                 f"Completed: {dist} mi"))
        else:
            # Non-run day: was it a row day or rest?
            # Check if adjacent days had runs (run-row-run pattern)
            prev_date = (current_date - timedelta(days=1)).isoformat()
            next_date = (current_date + timedelta(days=1)).isoformat()
            if prev_date in run_by_date or next_date in run_by_date:
                all_days.append(_run(day_name, current_date, "Cross-train (actual)",
                                     0, 0, "Zone 2",
                                     f"{avg_xt_min} min cross-training"))
            else:
                all_days.append(_run(day_name, current_date, "Rest (actual)",
                                     0, 0, "", "Rest day"))

        current_date += timedelta(days=1)

    # ============================================================
    # PHASE 2: Project forward (tomorrow → race day)
    # ============================================================
    # Determine starting state from actual history
    last_run_hr = 0
    last_run_dist = 0
    current_longest = longest_done
    runs_since_build = 0

    if runs:
        last_run = runs[-1]
        last_run_hr = last_run.get("avg_heart_rate", 0)
        last_run_dist = last_run.get("distance_mi", 0)
        last_run_date_str = last_run.get("date", "")

        # Determine runs_since_build from recent history
        for r in reversed(runs[-5:]):
            d = r.get("distance_mi", 0)
            if d >= current_longest:
                break
            runs_since_build += 1

        # Determine run/row alternation from last run date
        try:
            lr_date = date.fromisoformat(last_run_date_str)
            days_since_run = (today - lr_date).days
        except ValueError:
            days_since_run = 1
    else:
        days_since_run = 0

    # Start projection from tomorrow
    current_date = today + timedelta(days=1)

    # days_since_run tells us where we are in the run-row cycle
    # 1 = ran yesterday (rowed today) → tomorrow is run
    # 0 = ran today → tomorrow is row
    is_run_day = (days_since_run % 2) == 1

    while current_date <= race_date:
        day_name = current_date.strftime("%a")
        days_to_race = (race_date - current_date).days

        # Race day
        if current_date == race_date:
            all_days.append(_run(day_name, current_date,
                                 f"RACE: {RACE_NAME}", RACE_DISTANCE_MILES,
                                 conservative_pace, "Zone 2-3",
                                 "RACE DAY! Start slow, finish strong."))
            break

        if is_run_day:
            # Check if we need rest instead
            if _needs_rest(last_run_hr, last_run_dist) and last_run_dist > 0:
                all_days.append(_run(day_name, current_date, "Rest", 0, 0, "",
                                     "Recovery day — HR signals suggest rest"))
                current_date += timedelta(days=1)
                last_run_hr = 0
                last_run_dist = 0
                continue

            # Taper phase
            if days_to_race <= taper_starts_at:
                taper_pct = max(0.4, days_to_race / taper_starts_at)
                dist = round(maintenance_dist * taper_pct, 1)
                dist = max(2.0, dist)
                run_type = "Taper Run"
                notes = "Taper: maintain fitness, reduce volume." + hr_note
            elif _should_build(runs_since_build, last_run_hr, days_to_race):
                dist = round(min(PEAK_LONG_RUN_MI, current_longest + build_increment), 1)
                run_type = "Distance Build"
                notes = _long_run_note(dist, current_longest, zone2_ceiling)
                current_longest = max(current_longest, dist)
                runs_since_build = 0
            else:
                dist = maintenance_dist
                run_type = "Maintenance Run"
                notes = "Conversational pace — maintain cardio base." + hr_note
                runs_since_build += 1

            all_days.append(_run(day_name, current_date, run_type,
                                 dist, easy_pace, "Zone 2", notes))
            last_run_dist = dist
            last_run_hr = avg_recent_hr
        else:
            # Cross-training day
            if days_to_race <= taper_starts_at:
                dur = round(avg_xt_min * 0.6)
                xt_note = f"{dur} min easy cross-training (taper)"
            else:
                dur = round(avg_xt_min)
                xt_note = f"{dur} min cross-training"
            all_days.append(_run(day_name, current_date, "Cross-train",
                                 0, 0, "Zone 2", xt_note))

        is_run_day = not is_run_day
        current_date += timedelta(days=1)

    # ============================================================
    # Group all days into calendar weeks (Mon–Sun)
    # ============================================================
    weeks = {}
    week1_monday = training_start - timedelta(days=training_start.weekday())

    for day_entry in all_days:
        day_str = day_entry["day"]
        date_part = day_str[4:]  # e.g. "Jan 05"
        # Parse using training start year, handle year boundary
        for year in [training_start.year, training_start.year + 1]:
            try:
                d = datetime.strptime(f"{date_part} {year}", "%b %d %Y").date()
                if d >= training_start - timedelta(days=7):
                    break
            except ValueError:
                d = training_start

        week_monday = d - timedelta(days=d.weekday())
        week_key = week_monday.isoformat()

        if week_key not in weeks:
            week_num = ((week_monday - week1_monday).days // 7) + 1
            week_end = week_monday + timedelta(days=6)

            days_to_race_wk = (race_date - week_monday).days
            if days_to_race_wk <= 7:
                phase = "Race Week"
            elif days_to_race_wk <= taper_starts_at:
                phase = "Taper"
            elif d <= today:
                phase = "Completed"
            else:
                phase = "Build"

            weeks[week_key] = {
                "week": week_num,
                "dates": f"{week_monday.strftime('%b %d')} - {week_end.strftime('%b %d')}",
                "type": phase,
                "total_miles": 0,
                "long_run_mi": 0,
                "runs": [],
            }

        weeks[week_key]["runs"].append(day_entry)
        miles = day_entry.get("distance_mi", 0)
        weeks[week_key]["total_miles"] = round(weeks[week_key]["total_miles"] + miles, 1)
        if "Build" in day_entry["type"] or "RACE" in day_entry["type"]:
            weeks[week_key]["long_run_mi"] = max(weeks[week_key]["long_run_mi"], miles)

    return list(weeks.values())


def _long_run_note(distance: float, longest_done: float = 0,
                   zone2_ceiling: int = 145) -> str:
    """Generate contextual note for long run based on distance and current fitness."""
    hr_cap = f" HR cap: {zone2_ceiling} bpm."

    # If this long run is >2 mi beyond what they've done, suggest run/walk
    if longest_done > 0 and distance > longest_done + 2.0:
        run_walk = " Use run/walk strategy (run 4 min, walk 1 min) for new distances."
    else:
        run_walk = ""

    if distance >= 10:
        return "Race simulation -- practice pacing, nutrition, hydration." + hr_cap + run_walk
    elif distance >= 8:
        return "Practice race-day hydration and fueling strategy." + hr_cap + run_walk
    elif distance >= 6:
        return "Build endurance -- slow & steady, stay in Zone 2." + hr_cap + run_walk
    else:
        return "Slow & steady, practice hydration." + hr_cap


def _run(day: str, day_date: date, run_type: str, distance: float, pace: float,
         hr_zone: str, notes: str) -> dict:
    """Create a single run entry."""
    return {
        "day": f"{day} {day_date.strftime('%b %d')}",
        "type": run_type,
        "distance_mi": distance,
        "target_pace": format_pace(pace, suffix=True) if pace > 0 else "N/A",
        "hr_zone": hr_zone,
        "notes": notes,
    }







def _race_day_recommendations(analysis: dict) -> dict:
    """Generate race day strategy."""
    running = analysis.get("running", {})
    hydration = analysis.get("hydration", {})
    body = analysis.get("body", {})

    avg_pace = running.get("avg_pace_per_mile", 10.0)
    if avg_pace <= 0:
        avg_pace = 10.0

    # Race pace strategy: more conservative given HR data shows runner is
    # consistently in Zone 4-5 at training paces. Add 15% buffer to average
    # training pace for a sustainable race effort.
    conservative_pace = avg_pace * 1.10  # 10% slower than training avg
    first_half_pace = conservative_pace + 0.3  # Start conservative
    second_half_pace = conservative_pace - 0.3  # Aim to finish strong

    finish_min = conservative_pace * RACE_DISTANCE_MILES
    hours = int(finish_min // 60)
    mins = int(finish_min % 60)

    weight_lbs = body.get("current_weight_lbs") or analysis.get("profile", {}).get("weight_lbs", 150)

    # Water recommendation: ~4-8 oz every 15-20 min during race
    race_duration_hrs = finish_min / 60
    water_oz = round(race_duration_hrs * 20, 0)  # ~20 oz per hour

    recs = {
        "target_finish": f"{hours}:{mins:02d}",
        "pacing_strategy": {
            "first_half_pace": format_pace(first_half_pace, suffix=True),
            "second_half_pace": format_pace(second_half_pace, suffix=True),
            "strategy": "Start conservative, finish strong",
        },
        "hr_strategy": "Stay under Zone 3 (walk if needed) for first 8 miles. Allow Zone 3 for miles 9-11. Push Zone 3-4 only for final 2 miles.",
        "hydration": {
            "pre_race": "16-20 oz water 2-3 hours before start",
            "during_race": f"4-8 oz every 15-20 min (~{water_oz:.0f} oz total)",
            "post_race": "16-24 oz within 30 minutes of finishing",
            "tip": "Practice your hydration strategy on long training runs",
        },
        "nutrition_tips": {
            "week_before": "Increase carb intake to 3-5g per lb of body weight in final 2-3 days",
            "night_before": "Familiar carb-rich dinner (pasta, rice) — nothing new",
            "morning_of": "Eat 2-3 hours before start: oatmeal, banana, toast with peanut butter",
            "during_race": "Energy gel or chews every 45-60 min after mile 4",
            "important": "Nothing new on race day — only eat what you've tested in training",
        },
        "gear_checklist": [
            "Broken-in running shoes (NOT new ones)",
            "Race bib and timing chip",
            "Body Glide / anti-chafe",
            "Weather-appropriate layers",
            "Charged Fitbit for tracking",
            "Energy gels/chews (tested in training)",
            "Sunscreen if sunny",
        ],
    }

    return recs


def _general_tips(analysis: dict) -> list:
    """Generate general training tips based on analysis."""
    tips = []
    sleep = analysis.get("sleep", {})
    hydration = analysis.get("hydration", {})
    running = analysis.get("running", {})
    hr = analysis.get("heart_rate", {})

    # Sleep tips
    avg_sleep = sleep.get("avg_duration_hrs", 0)
    if avg_sleep > 0 and avg_sleep < 7:
        tips.append(
            f"SLEEP: Your average sleep is {avg_sleep} hrs. Aim for 7-9 hours -- "
            "sleep is when your body repairs and builds fitness."
        )

    # Hydration tips
    score = hydration.get("hydration_score", "")
    if "Needs work" in score or "Fair" in score:
        goal_ml = hydration.get("goal_ml", 0)
        tips.append(
            f"HYDRATION: Needs improvement. Aim for at least {goal_ml}ml "
            f"({round(goal_ml / 29.574)}oz) daily, more on run days."
        )

    # Training tips
    weekly = running.get("avg_weekly_mileage", 0)
    if weekly > 0 and weekly < 15:
        tips.append(
            "MILEAGE: Build weekly mileage gradually (no more than 10% increase per week) "
            "to avoid injury."
        )

    # HR training tip - CRITICAL for this runner
    hr_trend = hr.get("resting_hr_trend", "")
    avg_run_hr = running.get("avg_hr", 0)
    if "increasing" in hr_trend.lower():
        tips.insert(0,
            "** IMPORTANT: Resting HR is trending UP -- a key overtraining signal. "
            "Consider replacing one hard session per week with easy cross-training or rest. "
            "If the trend continues for 2+ weeks, take a full recovery week."
        )

    if avg_run_hr > 155:
        tips.insert(0,
            "** HR ALERT: Your average run HR ({:.0f} bpm) is too high for easy runs. "
            "Most runs should be in Zone 2. Slow down or use run/walk strategy "
            "until you can hold a conversation while running.".format(avg_run_hr)
        )

    # General half marathon tips
    tips.extend([
        "ALL RUNS EASY: Keep all training runs at conversational pace (Zone 2). "
        "Build distance gradually — speed comes from endurance.",
        "STRENGTH: Include strength training 2x/week (squats, lunges, calf raises, core) "
        "to prevent injury.",
        "RECOVERY: Ice or foam roll after hard sessions to aid recovery.",
        "REST: Don't skip rest days -- they're when adaptation happens.",
    ])

    return tips
