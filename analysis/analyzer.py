from __future__ import annotations
"""Analyzes Fitbit data to assess fitness for half marathon readiness."""

from datetime import date, datetime, timedelta
from collections import defaultdict

from config import RACE_DATE, RACE_DISTANCE_MILES
from utils import format_pace
from utils import KM_TO_MILES


def analyze(data: dict) -> dict:
    """Analyze all collected Fitbit data and return a fitness assessment.

    Returns a dict with sections: profile, body, running, heart_rate,
    vo2_max, sleep, hydration, daily_activity, readiness.
    """
    result = {}

    result["profile"] = _analyze_profile(data.get("profile", {}))
    result["body"] = _analyze_body(data)
    result["running"] = _analyze_running(data.get("activities", []),
                                          data.get("run_weather", {}))
    result["cross_training"] = _analyze_cross_training(data.get("activities", []))
    result["heart_rate"] = _analyze_heart_rate(data.get("heart_rate", []))
    result["vo2_max"] = _analyze_vo2_max(data.get("vo2_max", []))
    result["sleep"] = _analyze_sleep(data.get("sleep", []))
    result["hydration"] = _analyze_hydration(data.get("water", []), data.get("water_goal", {}))
    result["daily_activity"] = _analyze_daily_activity(data.get("time_series", {}))
    result["spo2"] = _analyze_spo2(data.get("spo2", []))
    result["weekly_calories"] = _analyze_weekly_calories(data.get("activities", []))
    result["splits"] = _analyze_splits(
        data.get("workout_splits", {}),
        data.get("activities", []),
    )
    result["readiness"] = _assess_readiness(result)

    return result


def _analyze_profile(profile_data: dict) -> dict:
    """Extract key profile metrics."""
    user = profile_data.get("user", {})
    height_cm = user.get("height", 0)
    weight_kg = user.get("weight", 0)
    bmi = 0
    if height_cm > 0 and weight_kg > 0:
        height_m = height_cm / 100
        bmi = weight_kg / (height_m ** 2)

    return {
        "name": user.get("displayName", "Unknown"),
        "age": user.get("age", 0),
        "height_cm": height_cm,
        "height_in": round(height_cm / 2.54, 1) if height_cm else 0,
        "weight_kg": weight_kg,
        "weight_lbs": round(weight_kg * 2.205, 1) if weight_kg else 0,
        "bmi": round(bmi, 1),
        "stride_length_running": user.get("strideLengthRunning", 0),
        "stride_length_walking": user.get("strideLengthWalking", 0),
    }


def _analyze_body(data: dict) -> dict:
    """Analyze weight and body fat trends."""
    weights = data.get("weight", [])
    body_fat = data.get("body_fat", [])

    result = {
        "weight_entries": len(weights),
        "body_fat_entries": len(body_fat),
        "weight_trend": "insufficient data",
        "current_weight_kg": None,
        "current_weight_lbs": None,
        "weight_change_kg": None,
        "avg_body_fat": None,
    }

    if weights:
        sorted_w = sorted(weights, key=lambda x: x.get("date", ""))
        result["current_weight_kg"] = sorted_w[-1].get("weight", 0)
        result["current_weight_lbs"] = round(result["current_weight_kg"] * 2.205, 1)

        if len(sorted_w) >= 2:
            first = sorted_w[0].get("weight", 0)
            last = sorted_w[-1].get("weight", 0)
            change = last - first
            result["weight_change_kg"] = round(change, 2)
            if change > 0.5:
                result["weight_trend"] = "gaining"
            elif change < -0.5:
                result["weight_trend"] = "losing"
            else:
                result["weight_trend"] = "stable"

    if body_fat:
        avg_bf = sum(e.get("fat", 0) for e in body_fat) / len(body_fat)
        result["avg_body_fat"] = round(avg_bf, 1)

    return result


def _analyze_running(activities: list, run_weather: dict | None = None) -> dict:
    """Analyze running activities for training metrics."""
    if run_weather is None:
        run_weather = {}
    runs = []
    for act in activities:
        name = act.get("activityName", "").lower()
        if "run" in name or "jog" in name:
            distance_mi = act.get("distance", 0)
            distance_unit = act.get("distanceUnit", "")
            # Fitbit may return km — normalize to miles
            if "kilometer" in distance_unit.lower() or "km" in distance_unit.lower():
                distance_mi = distance_mi * KM_TO_MILES

            duration_ms = act.get("duration", 0)
            duration_min = duration_ms / 60000

            pace_per_mile = duration_min / distance_mi if distance_mi > 0 else 0
            calories = act.get("calories", 0)
            avg_hr = act.get("averageHeartRate", 0)

            # Extract date from originalStartTime or startTime
            start_time = act.get("originalStartTime") or act.get("startTime", "")
            run_date = start_time[:10] if start_time else ""

            log_id = act.get("logId")
            run_entry = {
                "date": run_date,
                "distance_mi": round(distance_mi, 2),
                "duration_min": round(duration_min, 1),
                "pace_per_mile": round(pace_per_mile, 2),
                "calories": calories,
                "avg_heart_rate": avg_hr,
                "log_id": log_id,
                "is_outdoor": act.get("hasGps", False),
            }

            # Attach weather data if available
            weather = run_weather.get(log_id)
            if weather:
                run_entry["weather"] = {
                    "temp_f": weather.get("avg_temp_f"),
                    "sky": weather.get("sky_condition"),
                    "precip": weather.get("precip_type") or "None",
                    "precip_in": weather.get("total_precip_in", 0),
                    "cloud_pct": weather.get("cloud_cover_pct"),
                    "location": weather.get("location_name", ""),
                }

            runs.append(run_entry)

    result = {
        "total_runs": len(runs),
        "runs": runs,
        "avg_weekly_mileage": 0,
        "avg_pace_per_mile": 0,
        "longest_run_mi": 0,
        "total_distance_mi": 0,
        "avg_run_distance_mi": 0,
    }

    if runs:
        total_dist = sum(r["distance_mi"] for r in runs)
        result["total_distance_mi"] = round(total_dist, 1)
        result["avg_run_distance_mi"] = round(total_dist / len(runs), 2)
        result["longest_run_mi"] = max(r["distance_mi"] for r in runs)

        paces = [r["pace_per_mile"] for r in runs if r["pace_per_mile"] > 0]
        if paces:
            result["avg_pace_per_mile"] = round(sum(paces) / len(paces), 2)

        # Weekly mileage: group by week
        if len(runs) >= 2:
            dates = sorted(
                datetime.strptime(r["date"], "%Y-%m-%d") for r in runs if r["date"]
            )
            if dates:
                weeks = max(1, (dates[-1] - dates[0]).days / 7)
                result["avg_weekly_mileage"] = round(total_dist / weeks, 1)

    # Weather summary across outdoor runs
    weather_runs = [r for r in runs if r.get("weather")]
    if weather_runs:
        temps = [r["weather"]["temp_f"] for r in weather_runs if r["weather"].get("temp_f") is not None]
        sky_counts = defaultdict(int)
        precip_counts = defaultdict(int)
        for r in weather_runs:
            sky_counts[r["weather"]["sky"]] += 1
            precip_counts[r["weather"]["precip"]] += 1

        result["weather_summary"] = {
            "runs_with_weather": len(weather_runs),
            "avg_temp_f": round(sum(temps) / len(temps), 1) if temps else None,
            "min_temp_f": round(min(temps), 1) if temps else None,
            "max_temp_f": round(max(temps), 1) if temps else None,
            "sky_distribution": dict(sky_counts),
            "precip_distribution": dict(precip_counts),
            "runs_with_precip": sum(1 for r in weather_runs if r["weather"]["precip"] != "None"),
        }

    return result


def _analyze_cross_training(activities: list) -> dict:
    """Analyze all non-running activities as cross-training."""
    running_keywords = ["run", "treadmill"]
    sessions = []
    activity_types = {}

    for act in activities:
        name = act.get("activityName", "")
        name_lower = name.lower()
        # Skip running activities
        if any(kw in name_lower for kw in running_keywords):
            continue

        duration_ms = act.get("duration", 0)
        duration_min = duration_ms / 60000
        if duration_min < 5:
            continue

        calories = act.get("calories", 0)
        avg_hr = act.get("averageHeartRate", 0)
        start_time = act.get("originalStartTime") or act.get("startTime", "")
        session_date = start_time[:10] if start_time else ""

        sessions.append({
            "date": session_date,
            "activity": name,
            "duration_min": round(duration_min, 1),
            "calories": calories,
            "avg_heart_rate": avg_hr,
        })

        activity_types[name] = activity_types.get(name, 0) + 1

    result = {
        "total_sessions": len(sessions),
        "sessions": sessions,
        "activity_types": activity_types,
        "avg_duration_min": 0,
        "avg_calories": 0,
        "avg_heart_rate": 0,
        "avg_weekly_sessions": 0,
    }

    if sessions:
        result["avg_duration_min"] = round(
            sum(s["duration_min"] for s in sessions) / len(sessions), 1
        )
        result["avg_calories"] = round(
            sum(s["calories"] for s in sessions) / len(sessions), 0
        )
        hrs = [s["avg_heart_rate"] for s in sessions if s["avg_heart_rate"] > 0]
        if hrs:
            result["avg_heart_rate"] = round(sum(hrs) / len(hrs), 0)

        if len(sessions) >= 2:
            dates = sorted(
                datetime.strptime(s["date"], "%Y-%m-%d")
                for s in sessions if s["date"]
            )
            if dates:
                weeks = max(1, (dates[-1] - dates[0]).days / 7)
                result["avg_weekly_sessions"] = round(len(sessions) / weeks, 1)

    return result
    result = {
        "data_points": len(hr_data),
        "avg_resting_hr": 0,
        "min_resting_hr": 0,
        "max_resting_hr": 0,
        "resting_hr_trend": "insufficient data",
        "hr_zones": {},
    }

    resting_hrs = []
    zone_totals = defaultdict(int)
    zone_counts = defaultdict(int)

    for day in hr_data:
        value = day.get("value", {})
        rhr = value.get("restingHeartRate")
        if rhr:
            resting_hrs.append(rhr)

        for zone in value.get("heartRateZones", []):
            name = zone.get("name", "Unknown")
            minutes = zone.get("minutes", 0)
            zone_totals[name] += minutes
            zone_counts[name] += 1

    if resting_hrs:
        result["avg_resting_hr"] = round(sum(resting_hrs) / len(resting_hrs), 1)
        result["min_resting_hr"] = min(resting_hrs)
        result["max_resting_hr"] = max(resting_hrs)

        if len(resting_hrs) >= 14:
            first_half = sum(resting_hrs[:len(resting_hrs)//2]) / (len(resting_hrs)//2)
            second_half = sum(resting_hrs[len(resting_hrs)//2:]) / (len(resting_hrs) - len(resting_hrs)//2)
            diff = second_half - first_half
            if diff < -1:
                result["resting_hr_trend"] = "improving (decreasing)"
            elif diff > 1:
                result["resting_hr_trend"] = "increasing (possible overtraining or fatigue)"
            else:
                result["resting_hr_trend"] = "stable"

    for name, total in zone_totals.items():
        result["hr_zones"][name] = {
            "total_minutes": total,
            "avg_daily_minutes": round(total / zone_counts[name], 1) if zone_counts[name] else 0,
        }

    return result


def _parse_vo2(value) -> float | None:
    """Parse a VO2 Max value which can be a number or a range string like '44-48'."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Handle range format "44-48" by averaging
        if "-" in value:
            parts = value.split("-")
            try:
                nums = [float(p.strip()) for p in parts]
                return sum(nums) / len(nums)
            except ValueError:
                return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _analyze_vo2_max(vo2_data: list) -> dict:
    """Analyze VO2 Max (cardio fitness score)."""
    result = {
        "data_points": len(vo2_data),
        "latest_vo2_max": None,
        "avg_vo2_max": None,
        "classification": "unknown",
    }

    values = []
    for entry in vo2_data:
        v = entry.get("value", {})
        vo2 = v.get("vo2Max")
        if vo2:
            if isinstance(vo2, list):
                for item in vo2:
                    values.append(_parse_vo2(item))
            else:
                values.append(_parse_vo2(vo2))

    # Filter out None values from failed parsing
    values = [v for v in values if v is not None]

    if values:
        result["latest_vo2_max"] = values[-1]
        result["avg_vo2_max"] = round(sum(values) / len(values), 1)

        latest = values[-1]
        if latest >= 50:
            result["classification"] = "Excellent"
        elif latest >= 43:
            result["classification"] = "Good"
        elif latest >= 36:
            result["classification"] = "Average"
        elif latest >= 30:
            result["classification"] = "Below Average"
        else:
            result["classification"] = "Poor"

    return result


def _analyze_sleep(sleep_data: list) -> dict:
    """Analyze sleep patterns."""
    result = {
        "total_logs": len(sleep_data),
        "avg_duration_hrs": 0,
        "avg_efficiency": 0,
        "avg_deep_pct": 0,
        "avg_rem_pct": 0,
        "sleep_quality": "insufficient data",
    }

    durations = []
    efficiencies = []
    deep_pcts = []
    rem_pcts = []

    for log in sleep_data:
        if not log.get("isMainSleep", False):
            continue

        duration_hrs = log.get("duration", 0) / 3600000  # ms to hours
        if duration_hrs > 0:
            durations.append(duration_hrs)

        eff = log.get("efficiency", 0)
        if eff > 0:
            efficiencies.append(eff)

        summary = log.get("levels", {}).get("summary", {})
        total_min = log.get("timeInBed", log.get("duration", 0) / 60000)
        if total_min > 0:
            deep = summary.get("deep", {}).get("minutes", 0)
            rem = summary.get("rem", {}).get("minutes", 0)
            if deep > 0:
                deep_pcts.append(deep / total_min * 100)
            if rem > 0:
                rem_pcts.append(rem / total_min * 100)

    if durations:
        result["avg_duration_hrs"] = round(sum(durations) / len(durations), 1)
    if efficiencies:
        result["avg_efficiency"] = round(sum(efficiencies) / len(efficiencies), 1)
    if deep_pcts:
        result["avg_deep_pct"] = round(sum(deep_pcts) / len(deep_pcts), 1)
    if rem_pcts:
        result["avg_rem_pct"] = round(sum(rem_pcts) / len(rem_pcts), 1)

    # Sleep quality assessment
    if durations:
        avg_hrs = result["avg_duration_hrs"]
        avg_eff = result["avg_efficiency"]
        if avg_hrs >= 7 and avg_eff >= 85:
            result["sleep_quality"] = "Excellent — great for recovery"
        elif avg_hrs >= 6.5 and avg_eff >= 75:
            result["sleep_quality"] = "Good — adequate for training"
        elif avg_hrs >= 6:
            result["sleep_quality"] = "Fair — consider improving sleep habits"
        else:
            result["sleep_quality"] = "Poor — sleep deficit may impair recovery"

    return result


def _analyze_hydration(water_data: list, water_goal: dict) -> dict:
    """Analyze water intake patterns."""
    result = {
        "days_tracked": len(water_data),
        "goal_ml": water_goal.get("goal", {}).get("goal", 0),
        "avg_daily_ml": 0,
        "avg_daily_oz": 0,
        "days_meeting_goal": 0,
        "hydration_score": "insufficient data",
    }

    daily_totals = []
    goal = result["goal_ml"]

    for day in water_data:
        total = day.get("summary", {}).get("water", 0)
        daily_totals.append(total)
        if goal > 0 and total >= goal:
            result["days_meeting_goal"] += 1

    if daily_totals:
        avg = sum(daily_totals) / len(daily_totals)
        result["avg_daily_ml"] = round(avg, 0)
        result["avg_daily_oz"] = round(avg / 29.574, 1)

        if goal > 0:
            pct = result["days_meeting_goal"] / len(daily_totals) * 100
            if pct >= 80:
                result["hydration_score"] = "Excellent — consistently hitting goal"
            elif pct >= 60:
                result["hydration_score"] = "Good — mostly on target"
            elif pct >= 40:
                result["hydration_score"] = "Fair — room for improvement"
            else:
                result["hydration_score"] = "Needs work — increase daily water intake"
        else:
            result["hydration_score"] = "No goal set — consider setting a daily target"

    return result


def _analyze_daily_activity(time_series: dict) -> dict:
    """Analyze daily activity patterns from time series data."""
    result = {
        "avg_daily_steps": 0,
        "avg_daily_distance_mi": 0,
        "avg_daily_floors": 0,
        "avg_sedentary_min": 0,
        "avg_lightly_active_min": 0,
        "avg_fairly_active_min": 0,
        "avg_very_active_min": 0,
        "activity_level": "insufficient data",
    }

    def _avg(series: list) -> float:
        vals = [float(e.get("value", 0)) for e in series if e.get("value")]
        return round(sum(vals) / len(vals), 1) if vals else 0

    result["avg_daily_steps"] = _avg(time_series.get("steps", []))
    result["avg_daily_distance_mi"] = _avg(time_series.get("distance", []))
    result["avg_daily_floors"] = _avg(time_series.get("floors", []))
    result["avg_sedentary_min"] = _avg(time_series.get("minutesSedentary", []))
    result["avg_lightly_active_min"] = _avg(time_series.get("minutesLightlyActive", []))
    result["avg_fairly_active_min"] = _avg(time_series.get("minutesFairlyActive", []))
    result["avg_very_active_min"] = _avg(time_series.get("minutesVeryActive", []))

    steps = result["avg_daily_steps"]
    if steps >= 12000:
        result["activity_level"] = "Very Active"
    elif steps >= 10000:
        result["activity_level"] = "Active"
    elif steps >= 7500:
        result["activity_level"] = "Somewhat Active"
    elif steps >= 5000:
        result["activity_level"] = "Low Active"
    elif steps > 0:
        result["activity_level"] = "Sedentary"

    return result


def _analyze_spo2(spo2_data: list) -> dict:
    """Analyze SpO2 (blood oxygen) data."""
    result = {
        "data_points": len(spo2_data),
        "avg_spo2": None,
        "min_spo2": None,
        "assessment": "insufficient data",
    }

    values = []
    for entry in spo2_data:
        v = entry.get("value", {})
        avg = v.get("avg")
        if avg:
            values.append(avg)

    if values:
        result["avg_spo2"] = round(sum(values) / len(values), 1)
        result["min_spo2"] = min(values)
        avg = result["avg_spo2"]
        if avg >= 95:
            result["assessment"] = "Normal — good oxygen delivery"
        elif avg >= 90:
            result["assessment"] = "Borderline — monitor closely"
        else:
            result["assessment"] = "Low — consult a physician"

    return result


def _analyze_weekly_calories(activities: list) -> dict:
    """Analyze calorie burn by week across all activity types."""
    weekly = defaultdict(lambda: {"total": 0, "by_type": defaultdict(int), "sessions": 0})

    for act in activities:
        start_time = act.get("originalStartTime") or act.get("startTime", "")
        act_date = start_time[:10] if start_time else ""
        if not act_date:
            continue

        calories = act.get("calories", 0)
        if calories <= 0:
            continue

        d = datetime.strptime(act_date, "%Y-%m-%d")
        week_start = d - timedelta(days=d.weekday())
        week_key = week_start.strftime("%Y-%m-%d")

        name = act.get("activityName", "Other")
        weekly[week_key]["total"] += calories
        weekly[week_key]["by_type"][name] += calories
        weekly[week_key]["sessions"] += 1

    sorted_weeks = sorted(weekly.items())
    weeks = []
    for week_key, data in sorted_weeks:
        weeks.append({
            "week_start": week_key,
            "total_calories": data["total"],
            "sessions": data["sessions"],
            "by_type": dict(data["by_type"]),
        })

    total_calories = sum(w["total_calories"] for w in weeks)
    avg_weekly = round(total_calories / len(weeks), 0) if weeks else 0

    return {
        "weeks": weeks,
        "total_calories": total_calories,
        "avg_weekly_calories": avg_weekly,
    }





def _assess_readiness(analysis: dict) -> dict:
    """Overall half marathon readiness assessment."""
    running = analysis.get("running", {})
    hr = analysis.get("heart_rate", {})
    vo2 = analysis.get("vo2_max", {})
    sleep = analysis.get("sleep", {})

    race_date = datetime.strptime(RACE_DATE, "%Y-%m-%d").date()
    weeks_remaining = max(0, (race_date - date.today()).days / 7)

    readiness = {
        "weeks_remaining": round(weeks_remaining, 1),
        "race_date": RACE_DATE,
        "distance_ready": False,
        "pace_ready": False,
        "estimated_finish_time": "insufficient data",
        "strengths": [],
        "areas_to_improve": [],
        "overall_readiness": "insufficient data",
    }

    longest = running.get("longest_run_mi", 0)
    avg_pace = running.get("avg_pace_per_mile", 0)
    weekly_mi = running.get("avg_weekly_mileage", 0)

    # Distance readiness
    if longest >= 10:
        readiness["distance_ready"] = True
        readiness["strengths"].append(f"Longest run of {longest} mi — close to race distance")
    elif longest >= 7:
        readiness["areas_to_improve"].append(
            f"Longest run is {longest} mi — need to build to 10-12 mi before race"
        )
    elif longest > 0:
        readiness["areas_to_improve"].append(
            f"Longest run is only {longest} mi — significant buildup needed for 13.1 mi"
        )

    # Pace assessment
    if avg_pace > 0:
        finish_minutes = avg_pace * RACE_DISTANCE_MILES
        hours = int(finish_minutes // 60)
        mins = int(finish_minutes % 60)
        readiness["estimated_finish_time"] = f"{hours}:{mins:02d} (at current avg pace of {format_pace(avg_pace)}/mi)"
        readiness["pace_ready"] = True

        if avg_pace < 9:
            readiness["strengths"].append(f"Strong pace ({format_pace(avg_pace)}/mi)")
        elif avg_pace < 11:
            readiness["strengths"].append(f"Solid pace ({format_pace(avg_pace)}/mi)")

    # Weekly mileage
    if weekly_mi >= 20:
        readiness["strengths"].append(f"Strong weekly mileage ({weekly_mi} mi/wk)")
    elif weekly_mi >= 12:
        readiness["strengths"].append(f"Decent weekly mileage ({weekly_mi} mi/wk)")
    elif weekly_mi > 0:
        readiness["areas_to_improve"].append(
            f"Weekly mileage is {weekly_mi} mi — aim for 15-25 mi/wk"
        )

    # Heart rate
    rhr = hr.get("avg_resting_hr", 0)
    if rhr > 0:
        if rhr < 60:
            readiness["strengths"].append(f"Excellent resting HR ({rhr} bpm)")
        elif rhr < 70:
            readiness["strengths"].append(f"Good resting HR ({rhr} bpm)")
        else:
            readiness["areas_to_improve"].append(
                f"Resting HR is {rhr} bpm — will improve with consistent training"
            )

    # VO2 Max
    v = vo2.get("latest_vo2_max")
    if v:
        classification = vo2.get("classification", "")
        if classification in ("Excellent", "Good"):
            readiness["strengths"].append(f"VO2 Max: {v} ({classification})")
        else:
            readiness["areas_to_improve"].append(f"VO2 Max: {v} ({classification}) — build aerobic base")

    # Sleep
    sq = sleep.get("sleep_quality", "")
    if "Excellent" in sq or "Good" in sq:
        readiness["strengths"].append(f"Sleep: {sq}")
    elif "Fair" in sq or "Poor" in sq:
        readiness["areas_to_improve"].append(f"Sleep: {sq}")

    # Cross-training
    cross = analysis.get("cross_training", {})
    cross_weekly = cross.get("avg_weekly_sessions", 0)
    if cross_weekly >= 2:
        types = ", ".join(cross.get("activity_types", {}).keys()) or "various"
        readiness["strengths"].append(
            f"Strong cross-training: {cross_weekly} sessions/wk "
            f"(avg {cross.get('avg_duration_min', 0)} min — {types})"
        )
    elif cross_weekly > 0:
        readiness["strengths"].append(
            f"Active cross-training: {cross_weekly} sessions/wk"
        )

    # Overall assessment
    s_count = len(readiness["strengths"])
    i_count = len(readiness["areas_to_improve"])
    if s_count == 0 and i_count == 0:
        readiness["overall_readiness"] = "Insufficient data — run 'assess' after syncing your Fitbit"
    elif readiness["distance_ready"] and s_count >= 3:
        readiness["overall_readiness"] = "Strong — well-positioned for the half marathon"
    elif s_count > i_count:
        readiness["overall_readiness"] = "Good — on track with some areas to develop"
    elif s_count == i_count:
        readiness["overall_readiness"] = "Moderate — targeted training needed"
    else:
        readiness["overall_readiness"] = "Building — focus on consistent training over the remaining weeks"

    return readiness


def _analyze_splits(workout_splits: dict, activities: list) -> dict:
    """Analyze per-mile split data across all runs.

    Args:
        workout_splits: {log_id: [split_dicts]} from cache.load_all_workout_splits()
        activities: List of activity dicts to correlate dates.

    Returns dict with per_run analysis and cross_run trends.
    """
    if not workout_splits:
        return {"per_run": [], "trends": {}, "has_data": False}

    # Build log_id → date mapping
    log_date = {}
    for act in activities:
        lid = act.get("logId")
        start_time = act.get("originalStartTime") or act.get("startTime", "")
        if lid and start_time:
            log_date[lid] = start_time[:10]

    per_run = []
    all_consistency_scores = []
    all_hr_drifts = []
    mile_pace_sums = defaultdict(list)

    for log_id, splits in sorted(workout_splits.items(), key=lambda x: log_date.get(x[0], "")):
        if len(splits) < 2:
            continue

        run_date = log_date.get(log_id, "")
        paces = [s["pace_per_mile"] for s in splits if s.get("pace_per_mile")]
        hrs = [s["avg_hr"] for s in splits if s.get("avg_hr")]

        if not paces:
            continue

        # Pace consistency: coefficient of variation (std / mean * 100)
        mean_pace = sum(paces) / len(paces)
        variance = sum((p - mean_pace) ** 2 for p in paces) / len(paces)
        std_pace = variance ** 0.5
        consistency_cv = round((std_pace / mean_pace) * 100, 1) if mean_pace > 0 else 0

        # Split type: compare first half avg vs second half avg
        mid = len(paces) // 2
        first_half_avg = sum(paces[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(paces[mid:]) / len(paces[mid:]) if paces[mid:] else 0
        if first_half_avg > 0 and second_half_avg > 0:
            diff_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            if diff_pct < -2:
                split_type = "negative"
            elif diff_pct > 2:
                split_type = "positive"
            else:
                split_type = "even"
        else:
            split_type = "unknown"

        # HR drift: average HR increase per mile (linear regression slope)
        hr_drift = None
        if len(hrs) >= 2:
            n = len(hrs)
            x_mean = (n - 1) / 2.0
            y_mean = sum(hrs) / n
            num = sum((i - x_mean) * (hrs[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            hr_drift = round(num / den, 1) if den > 0 else 0

        # Cardiac decoupling: pace:HR ratio first half vs second half
        decoupling = None
        if len(hrs) >= 2 and mid > 0:
            hr_first = sum(hrs[:mid]) / mid
            hr_second = sum(hrs[mid:]) / len(hrs[mid:])
            if hr_first > 0 and first_half_avg > 0 and second_half_avg > 0:
                ratio_first = first_half_avg / hr_first
                ratio_second = second_half_avg / hr_second if hr_second > 0 else ratio_first
                decoupling = round(((ratio_second - ratio_first) / ratio_first) * 100, 1)

        run_analysis = {
            "log_id": log_id,
            "date": run_date,
            "splits": splits,
            "split_type": split_type,
            "consistency_cv": consistency_cv,
            "hr_drift_per_mile": hr_drift,
            "cardiac_decoupling_pct": decoupling,
            "mean_pace": round(mean_pace, 2),
        }

        per_run.append(run_analysis)
        all_consistency_scores.append({"date": run_date, "cv": consistency_cv})
        if hr_drift is not None:
            all_hr_drifts.append({"date": run_date, "drift": hr_drift})

        # Track pace by mile number for cross-run trend
        for s in splits:
            mile_pace_sums[s["mile_number"]].append(s["pace_per_mile"])

    # Cross-run trends
    trends = {}

    # Pace consistency trend
    if len(all_consistency_scores) >= 3:
        recent = all_consistency_scores[-3:]
        older = all_consistency_scores[:-3] if len(all_consistency_scores) > 3 else all_consistency_scores[:1]
        recent_avg = sum(x["cv"] for x in recent) / len(recent)
        older_avg = sum(x["cv"] for x in older) / len(older)
        if recent_avg < older_avg - 1:
            trends["consistency_direction"] = "improving"
        elif recent_avg > older_avg + 1:
            trends["consistency_direction"] = "declining"
        else:
            trends["consistency_direction"] = "stable"

    # HR drift trend
    if len(all_hr_drifts) >= 3:
        recent_drift = sum(x["drift"] for x in all_hr_drifts[-3:]) / 3
        older_drift = sum(x["drift"] for x in all_hr_drifts[:-3]) / max(1, len(all_hr_drifts) - 3) if len(all_hr_drifts) > 3 else all_hr_drifts[0]["drift"]
        if recent_drift < older_drift - 0.5:
            trends["hr_drift_direction"] = "improving"
        elif recent_drift > older_drift + 0.5:
            trends["hr_drift_direction"] = "worsening"
        else:
            trends["hr_drift_direction"] = "stable"

    # Slowest/fastest mile across runs
    if mile_pace_sums:
        avg_by_mile = {m: sum(ps) / len(ps) for m, ps in mile_pace_sums.items()}
        trends["slowest_mile"] = max(avg_by_mile, key=avg_by_mile.get)
        trends["fastest_mile"] = min(avg_by_mile, key=avg_by_mile.get)
        trends["avg_pace_by_mile"] = {m: round(v, 2) for m, v in sorted(avg_by_mile.items())}

    # First mile too fast?
    if 1 in mile_pace_sums and len(mile_pace_sums) > 1:
        first_mile_avg = sum(mile_pace_sums[1]) / len(mile_pace_sums[1])
        all_paces = [p for ps in mile_pace_sums.values() for p in ps]
        overall_avg = sum(all_paces) / len(all_paces)
        trends["first_mile_too_fast"] = first_mile_avg < overall_avg * 0.95

    # Decoupling concern
    decouplings = [r["cardiac_decoupling_pct"] for r in per_run
                   if r.get("cardiac_decoupling_pct") is not None]
    if decouplings:
        avg_decoupling = sum(decouplings) / len(decouplings)
        trends["avg_cardiac_decoupling"] = round(avg_decoupling, 1)
        trends["decoupling_concern"] = avg_decoupling > 5.0

    return {
        "per_run": per_run,
        "trends": trends,
        "has_data": len(per_run) > 0,
        "total_runs_with_splits": len(per_run),
        "consistency_history": all_consistency_scores,
        "hr_drift_history": all_hr_drifts,
    }
