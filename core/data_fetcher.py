from __future__ import annotations
"""Orchestrates data collection from Fitbit API with SQLite caching.

On first run, fetches all historical data and stores it in the local cache.
On subsequent runs, only fetches data newer than the last sync date,
dramatically reducing API calls and avoiding rate limits.
"""

from datetime import date, datetime, timedelta


from core.fitbit_client import FitbitClient, RateLimitError
from config import DATA_START_DATE
from utils import KM_TO_MILES
import core.cache as cache


def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _date_chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split a date range into chunks of max_days."""
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


# Track whether we've been rate limited to skip remaining API calls
_rate_limited = False
_rate_limit_reset = 0


def _check_rate_limit():
    """If we've been rate limited, skip API calls."""
    global _rate_limited
    if _rate_limited:
        raise RateLimitError(_rate_limit_reset)


def _handle_rate_limit(e: RateLimitError):
    """Mark that we're rate limited so remaining syncs skip API calls."""
    global _rate_limited, _rate_limit_reset
    _rate_limited = True
    _rate_limit_reset = e.retry_after
    mins = e.retry_after // 60
    print(f"  ⚠️  Rate limited — resets in ~{mins} min. Using cached data for remaining endpoints.")


def fetch_all_data(lookback_days: int | None = None) -> dict:
    """Fetch Fitbit data, using local cache to minimize API calls.

    First run pulls all data since DATA_START_DATE. Subsequent runs only
    fetch data since last sync.

    Args:
        lookback_days: Ignored (kept for CLI compat). Uses DATA_START_DATE.

    Returns:
        Dictionary with all collected data organized by category.
    """
    cache.init_db()
    client = FitbitClient()
    today = date.today()
    start = _parse_date(DATA_START_DATE)
    today_str = _date_str(today)
    start_str = _date_str(start)

    # Reset rate limit state for this run
    global _rate_limited
    _rate_limited = False

    data = {}

    # 1. User Profile — refresh once per day
    last = cache.get_last_sync("profile")
    if last != today_str:
        try:
            _check_rate_limit()
            print("Fetching user profile...")
            profile = client.get_profile()
            cache.save_profile(profile)
            cache.set_last_sync("profile", today_str)
        except RateLimitError as e:
            _handle_rate_limit(e)
    else:
        print("Using cached profile...")
    data["profile"] = cache.load_profile() or {}

    # 2. Weight & body fat — only fetch new days
    try:
        _check_rate_limit()
        _sync_weight(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["weight"] = cache.load_weight_entries(start_str)
    data["body_fat"] = cache.load_body_fat_entries(start_str)

    # 3. Activity logs
    try:
        _check_rate_limit()
        _sync_activities(client, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["activities"] = cache.load_activities(start_str)

    # Workout summaries for runs
    try:
        _check_rate_limit()
        _sync_workout_summaries(client, data["activities"])
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["workout_summaries"] = cache.load_workout_summaries()

    # Workout intraday (per-mile splits)
    try:
        _check_rate_limit()
        _sync_workout_intraday(client, data["activities"])
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["workout_splits"] = cache.load_all_workout_splits()

    # Run weather enrichment (GPS → Open-Meteo)
    try:
        _check_rate_limit()
        _sync_run_weather(client, data["activities"])
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["run_weather"] = cache.load_run_weather(start_str)

    # 4. Activity time series
    try:
        _check_rate_limit()
        _sync_time_series(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["time_series"] = {}
    for resource in ["steps", "distance", "floors", "minutesSedentary",
                     "minutesLightlyActive", "minutesFairlyActive", "minutesVeryActive"]:
        data["time_series"][resource] = cache.load_time_series(resource, start_str)

    # 5. Heart rate
    try:
        _check_rate_limit()
        _sync_heart_rate(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["heart_rate"] = cache.load_heart_rate(start_str)

    # 6. VO2 Max
    try:
        _check_rate_limit()
        _sync_vo2_max(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["vo2_max"] = cache.load_vo2_max(start_str)

    # 7. Sleep
    try:
        _check_rate_limit()
        _sync_sleep(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["sleep"] = cache.load_sleep_logs(start_str)

    # 8. Water
    try:
        _check_rate_limit()
        _sync_water(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["water"] = cache.load_water_logs(start_str)
    data["water_goal"] = cache.load_water_goal() or {}

    # 9. SpO2
    try:
        _check_rate_limit()
        _sync_spo2(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["spo2"] = cache.load_spo2(start_str)

    # 10. Active zone minutes
    try:
        _check_rate_limit()
        _sync_azm(client, start, today)
    except RateLimitError as e:
        _handle_rate_limit(e)
    data["active_zone_minutes"] = cache.load_active_zone_minutes(start_str)

    # Show cache stats
    stats = cache.get_cache_stats()
    total = sum(stats.values())
    if _rate_limited:
        print(f"\n⚠️  Partial sync due to rate limit. Showing results from {total} cached records.")
        print(f"   Run again after the rate limit resets for complete data.\n")
    else:
        print(f"Data ready! ({total} cached records across {len(stats)} tables)\n")
    return data


def _get_sync_start(endpoint: str, earliest: date) -> date:
    """Determine the start date for a sync: day after last sync or earliest."""
    last = cache.get_last_sync(endpoint)
    if last:
        last_date = _parse_date(last)
        # Re-fetch the last synced day (in case it was partial) plus new days
        return last_date
    return earliest


def _sync_weight(client: FitbitClient, start: date, today: date):
    sync_start = _get_sync_start("weight", start)
    if sync_start >= today:
        print("Using cached weight data...")
        return
    print(f"Fetching weight data from {_date_str(sync_start)}...")
    for chunk_start, chunk_end in _date_chunks(sync_start, today, 31):
        try:
            w = client.get_weight_log(_date_str(chunk_start), _date_str(chunk_end))
            cache.save_weight_entries(w.get("weight", []))
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: weight data unavailable for {chunk_start}: {e}")
        try:
            bf = client.get_body_fat_log(_date_str(chunk_start), _date_str(chunk_end))
            cache.save_body_fat_entries(bf.get("fat", []))
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: body fat data unavailable for {chunk_start}: {e}")
        # Save progress after each chunk
        cache.set_last_sync("weight", _date_str(chunk_end))


def _sync_activities(client: FitbitClient, today: date):
    last = cache.get_last_sync("activities")
    if last == _date_str(today):
        print("Using cached activities...")
        return
    print("Fetching activity logs...")
    # Paginate to get ALL activities from DATA_START_DATE
    all_activities = []
    offset = 0
    while True:
        resp = client.get_activity_log_list(
            _date_str(today), limit=100, sort="desc", offset=offset
        )
        activities = resp.get("activities", [])
        if not activities:
            break
        # Filter to only include activities on or after DATA_START_DATE
        for act in activities:
            act_date = act.get("startDate", act.get("originalStartTime", "")[:10])
            if act_date >= DATA_START_DATE:
                all_activities.append(act)
        # Check if there are more pages and if we haven't gone past our start date
        oldest_date = activities[-1].get("startDate", activities[-1].get("originalStartTime", "")[:10])
        if oldest_date < DATA_START_DATE:
            break
        # Check pagination from response
        pagination = resp.get("pagination", {})
        next_url = pagination.get("next", "")
        if not next_url:
            break
        offset += 100
    if all_activities:
        cache.save_activities(all_activities)
    cache.set_last_sync("activities", _date_str(today))


def _sync_workout_summaries(client: FitbitClient, activities: list):
    existing = cache.load_workout_summaries()
    for act in activities:
        log_id = act.get("logId")
        name = act.get("activityName", "").lower()
        if log_id and ("run" in name or "jog" in name) and log_id not in existing:
            try:
                ws = client.get_workout_summary(log_id)
                cache.save_workout_summary(log_id, ws)
            except RateLimitError:
                raise
            except Exception:
                pass


def _sync_time_series(client: FitbitClient, start: date, today: date):
    last = cache.get_last_sync("time_series")
    if last == _date_str(today):
        print("Using cached time series...")
        return
    print("Fetching activity time series...")
    resources = ["steps", "distance", "floors", "minutesSedentary",
                 "minutesLightlyActive", "minutesFairlyActive", "minutesVeryActive"]
    fetch_date = _date_str(today)
    period = "1m" if last else "3m"
    for resource in resources:
        try:
            ts = client.get_activity_time_series(resource, fetch_date, period)
            key = f"activities-{resource}"
            entries = ts.get(key, [])
            if entries:
                cache.save_time_series(resource, entries)
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: {resource} unavailable: {e}")
    cache.set_last_sync("time_series", _date_str(today))


def _sync_heart_rate(client: FitbitClient, start: date, today: date):
    last = cache.get_last_sync("heart_rate")
    if last == _date_str(today):
        print("Using cached heart rate data...")
        return
    print("Fetching heart rate data...")
    period = "1m" if last else "3m"
    hr = client.get_heart_rate_time_series(_date_str(today), period)
    entries = hr.get("activities-heart", [])
    if entries:
        cache.save_heart_rate(entries)
    cache.set_last_sync("heart_rate", _date_str(today))


def _sync_vo2_max(client: FitbitClient, start: date, today: date):
    sync_start = _get_sync_start("vo2_max", start)
    if sync_start >= today:
        print("Using cached VO2 Max data...")
        return
    print(f"Fetching VO2 Max data from {_date_str(sync_start)}...")
    for chunk_start, chunk_end in _date_chunks(sync_start, today, 30):
        try:
            vo2 = client.get_vo2_max_by_range(_date_str(chunk_start), _date_str(chunk_end))
            entries = vo2.get("cardioScore", [])
            if entries:
                cache.save_vo2_max(entries)
            cache.set_last_sync("vo2_max", _date_str(chunk_end))
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: VO2 Max unavailable for {chunk_start}: {e}")
            cache.set_last_sync("vo2_max", _date_str(chunk_end))


def _sync_sleep(client: FitbitClient, start: date, today: date):
    sync_start = _get_sync_start("sleep", start)
    if sync_start >= today:
        print("Using cached sleep data...")
        return
    print(f"Fetching sleep data from {_date_str(sync_start)}...")
    for chunk_start, chunk_end in _date_chunks(sync_start, today, 100):
        try:
            sleep = client.get_sleep_log_by_date_range(
                _date_str(chunk_start), _date_str(chunk_end)
            )
            entries = sleep.get("sleep", [])
            if entries:
                cache.save_sleep_logs(entries)
            cache.set_last_sync("sleep", _date_str(chunk_end))
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: sleep unavailable for {chunk_start}: {e}")
            cache.set_last_sync("sleep", _date_str(chunk_end))


def _sync_water(client: FitbitClient, start: date, today: date):
    sync_start = _get_sync_start("water", start)
    water_start = max(sync_start, today - timedelta(days=30))
    if water_start >= today:
        print("Using cached water data...")
        return
    print(f"Fetching water data from {_date_str(water_start)}...")

    # Water goal (only fetch once)
    if not cache.load_water_goal():
        try:
            goal = client.get_water_goal()
            cache.save_water_goal(goal)
        except RateLimitError:
            raise
        except Exception as e:
            print(f"  Warning: water goal unavailable: {e}")

    current = water_start
    while current <= today:
        try:
            wl = client.get_water_log(_date_str(current))
            total = wl.get("summary", {}).get("water", 0)
            cache.save_water_log(_date_str(current), total, {
                "date": _date_str(current),
                "summary": wl.get("summary", {}),
                "water": wl.get("water", []),
            })
        except RateLimitError:
            cache.set_last_sync("water", _date_str(current - timedelta(days=1)))
            raise
        except Exception as e:
            print(f"  Warning: water data unavailable for {current}: {e}")
        current += timedelta(days=1)
    cache.set_last_sync("water", _date_str(today))


def _sync_spo2(client: FitbitClient, start: date, today: date):
    sync_start = _get_sync_start("spo2", start)
    spo2_start = max(sync_start, today - timedelta(days=30))
    if spo2_start >= today:
        print("Using cached SpO2 data...")
        return
    print(f"Fetching SpO2 data from {_date_str(spo2_start)}...")
    spo2 = client.get_spo2_by_range(_date_str(spo2_start), _date_str(today))
    entries = spo2 if isinstance(spo2, list) else [spo2]
    cache.save_spo2(entries)
    cache.set_last_sync("spo2", _date_str(today))


def _sync_azm(client: FitbitClient, start: date, today: date):
    last = cache.get_last_sync("azm")
    if last == _date_str(today):
        print("Using cached active zone minutes...")
        return
    print("Fetching active zone minutes...")
    period = "1m" if last else "3m"
    azm = client.get_active_zone_minutes(_date_str(today), period)
    entries = azm.get("activities-active-zone-minutes", [])
    if entries:
        cache.save_active_zone_minutes(entries)
    cache.set_last_sync("azm", _date_str(today))


def _extract_workout_time_window(activity: dict) -> tuple[str, str, str] | None:
    """Extract date and start/end HH:mm from an activity log entry.

    Returns (date_str, start_hhmm, end_hhmm) or None if times can't be parsed.
    """
    start_time_str = activity.get("originalStartTime") or activity.get("startTime", "")
    duration_ms = activity.get("duration", 0) or activity.get("activeDuration", 0)
    if not start_time_str or not duration_ms:
        return None

    try:
        # Parse ISO format: 2026-01-15T06:30:00.000-06:00 or similar
        # Strip timezone for local time parsing
        clean = start_time_str.replace("Z", "")
        if "+" in clean[10:]:
            clean = clean[:clean.index("+", 10)]
        elif clean.count("-") > 2:
            last_dash = clean.rindex("-")
            if last_dash > 10:
                clean = clean[:last_dash]

        dt_start = datetime.fromisoformat(clean)
        dt_end = dt_start + timedelta(milliseconds=duration_ms)

        day_str = dt_start.strftime("%Y-%m-%d")
        start_hhmm = dt_start.strftime("%H:%M")
        end_hhmm = dt_end.strftime("%H:%M")
        return (day_str, start_hhmm, end_hhmm)
    except (ValueError, TypeError):
        return None


def _compress_intraday(hr_data: list, distance_data: list, steps_data: list,
                       workout_start_str: str, convert_km_to_mi: bool = False) -> list:
    """Compress raw intraday data into 30-second intervals.

    HR data is at 1-sec resolution — averaged over each 30-sec window.
    Distance/steps are at 1-min resolution — interpolated to 30-sec intervals.
    Raw data is discarded after compression (never stored).

    Args:
        hr_data: List of {"time": "HH:MM:SS", "value": int} at 1-sec resolution.
        distance_data: List of {"time": "HH:MM:SS", "value": float} at 1-min resolution.
        steps_data: List of {"time": "HH:MM:SS", "value": int} at 1-min resolution.
        workout_start_str: Workout start time as "HH:MM" for computing elapsed seconds.
        convert_km_to_mi: If True, convert distance values from kilometers to miles.

    Returns:
        List of interval dicts ready for cache.save_workout_intraday().
    """
    if not hr_data and not distance_data:
        return []

    def _time_to_sec(t: str) -> int:
        parts = t.split(":")
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s

    start_sec = _time_to_sec(workout_start_str + ":00")

    # Build cumulative distance from per-minute increments
    dist_by_sec = {}
    cumulative = 0.0
    km_factor = KM_TO_MILES if convert_km_to_mi else 1.0
    for d in distance_data:
        sec = _time_to_sec(d["time"])
        val = float(d.get("value", 0)) * km_factor
        cumulative += val
        dist_by_sec[sec] = cumulative

    # Build steps by second offset
    steps_by_sec = {}
    for s in steps_data:
        sec = _time_to_sec(s["time"])
        steps_by_sec[sec] = int(s.get("value", 0))

    # Build HR by second offset
    hr_by_sec = {}
    for h in hr_data:
        sec = _time_to_sec(h["time"])
        hr_by_sec[sec] = int(h.get("value", 0))

    # Determine time range
    all_secs = set()
    all_secs.update(hr_by_sec.keys())
    all_secs.update(dist_by_sec.keys())
    all_secs.update(steps_by_sec.keys())
    if not all_secs:
        return []

    min_sec = min(all_secs)
    max_sec = max(all_secs)

    # Generate 30-second intervals
    intervals = []
    idx = 0
    window_start = min_sec

    while window_start <= max_sec:
        window_end = window_start + 30
        elapsed = window_start - start_sec

        # Average HR over this 30-sec window
        hr_vals = [hr_by_sec[s] for s in range(window_start, min(window_end, max_sec + 1))
                   if s in hr_by_sec and hr_by_sec[s] > 0]
        avg_hr = sum(hr_vals) / len(hr_vals) if hr_vals else None

        # Cumulative distance: take the latest reading in or before this window
        latest_dist = None
        for s in range(window_end - 1, window_start - 61, -1):
            if s in dist_by_sec:
                latest_dist = dist_by_sec[s]
                break
        if latest_dist is None and intervals:
            latest_dist = intervals[-1].get("distance")

        # Steps in this window: sum minute-level readings that overlap
        window_steps = 0
        for s in range(window_start, window_end):
            if s in steps_by_sec:
                # Per-minute value — split proportionally into the 30-sec window
                window_steps += steps_by_sec[s] // 2

        intervals.append({
            "interval_index": idx,
            "elapsed_sec": max(0, elapsed),
            "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
            "distance": round(latest_dist, 4) if latest_dist is not None else None,
            "steps": window_steps,
        })

        idx += 1
        window_start = window_end

    return intervals


def _compute_mile_splits(intervals: list) -> list:
    """Compute per-mile splits from compressed 30-sec interval data.

    Walks through cumulative distance to find mile boundaries, then computes
    pace, HR, and cadence for each mile segment.

    Returns:
        List of split dicts ready for cache.save_workout_splits().
    """
    if not intervals:
        return []

    # Filter to intervals that have distance data
    valid = [iv for iv in intervals if iv.get("distance") is not None]
    if not valid:
        return []

    splits = []
    mile_number = 1
    mile_start_idx = 0
    # Interpolated time of the previous mile boundary for accurate lap times
    mile_boundary_time = valid[0]["elapsed_sec"]

    for i, iv in enumerate(valid):
        current_dist = iv["distance"]
        next_boundary = mile_number * 1.0

        if current_dist >= next_boundary:
            # Interpolate exact time the mile boundary was crossed
            if i > 0:
                prev_dist = valid[i - 1]["distance"]
                prev_time = valid[i - 1]["elapsed_sec"]
                curr_time = iv["elapsed_sec"]
                dist_gap = current_dist - prev_dist
                if dist_gap > 0:
                    fraction = (next_boundary - prev_dist) / dist_gap
                    crossing_time = prev_time + fraction * (curr_time - prev_time)
                else:
                    crossing_time = curr_time
            else:
                crossing_time = iv["elapsed_sec"]

            segment = valid[mile_start_idx:i + 1]
            elapsed_sec = crossing_time - mile_boundary_time

            # Collect HR values from segment
            hrs = [s["avg_hr"] for s in segment if s.get("avg_hr") is not None]
            avg_hr = sum(hrs) / len(hrs) if hrs else None

            # Cadence: total steps / elapsed minutes
            total_steps = sum(s.get("steps", 0) for s in segment)
            elapsed_min = elapsed_sec / 60.0 if elapsed_sec > 0 else 1
            avg_cadence = round(total_steps / elapsed_min, 1) if elapsed_sec > 0 else None

            splits.append({
                "mile_number": mile_number,
                "split_time_sec": round(elapsed_sec, 1),
                "pace_per_mile": round(elapsed_sec / 60.0, 2),
                "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
                "avg_cadence": avg_cadence,
                "cumulative_distance": round(current_dist, 2),
            })

            mile_number += 1
            mile_start_idx = i + 1
            mile_boundary_time = crossing_time

    # Include partial final mile only if ≥ 0.9 miles remaining
    if mile_start_idx < len(valid):
        segment = valid[mile_start_idx:]
        remaining_dist = valid[-1]["distance"] - (mile_number - 1) * 1.0
        if remaining_dist >= 0.9:
            elapsed_sec = valid[-1]["elapsed_sec"] - mile_boundary_time
            hrs = [s["avg_hr"] for s in segment if s.get("avg_hr") is not None]
            avg_hr = sum(hrs) / len(hrs) if hrs else None
            total_steps = sum(s.get("steps", 0) for s in segment)
            elapsed_min = elapsed_sec / 60.0 if elapsed_sec > 0 else 1
            pace_per_mile = round((elapsed_sec / remaining_dist) / 60.0, 2) if remaining_dist > 0 else None

            splits.append({
                "mile_number": mile_number,
                "split_time_sec": round(elapsed_sec, 1),
                "pace_per_mile": pace_per_mile,
                "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
                "avg_cadence": round(total_steps / elapsed_min, 1) if elapsed_sec > 0 else None,
                "cumulative_distance": round(valid[-1]["distance"], 2),
            })

    return splits


def _sync_workout_intraday(client: FitbitClient, activities: list):
    """Fetch and cache 30-sec compressed intraday data for each run/jog.

    Only fetches for workouts not already in the cache. Respects rate limits.
    Each intraday endpoint (HR, distance, steps) is tried independently —
    partial data is still useful for mile split computation.
    If the first 2 workouts get 403 on all endpoints, stops (app lacks intraday access).
    """
    existing = cache.get_workouts_with_intraday()
    runs = [a for a in activities
            if ("run" in a.get("activityName", "").lower()
                or "jog" in a.get("activityName", "").lower())
            and a.get("logId") not in existing]

    if not runs:
        print("Using cached workout intraday data...")
        return

    print(f"Fetching intraday data for {len(runs)} workout(s)...")
    consecutive_403s = 0

    for act in runs:
        log_id = act.get("logId")
        time_window = _extract_workout_time_window(act)
        if not time_window:
            continue

        day_str, start_hhmm, end_hhmm = time_window
        hr_data = []
        dist_data = []
        steps_data = []
        all_403 = True

        try:
            _check_rate_limit()
        except RateLimitError:
            raise

        # Try each endpoint independently — 403 on one shouldn't block others
        try:
            hr_resp = client.get_heart_rate_intraday(day_str, start_hhmm, end_hhmm, "1sec")
            hr_data = hr_resp.get("activities-heart-intraday", {}).get("dataset", [])
            if hr_data:
                all_403 = False
        except RateLimitError:
            raise
        except Exception as e:
            if "403" not in str(e):
                all_403 = False
            print(f"  [!] HR intraday unavailable for {day_str}: {e}")

        try:
            dist_resp = client.get_distance_intraday(day_str, start_hhmm, end_hhmm)
            dist_data = dist_resp.get("activities-distance-intraday", {}).get("dataset", [])
            if dist_data:
                all_403 = False
        except RateLimitError:
            raise
        except Exception as e:
            if "403" not in str(e):
                all_403 = False
            print(f"  [!] Distance intraday unavailable for {day_str}: {e}")

        try:
            steps_resp = client.get_steps_intraday(day_str, start_hhmm, end_hhmm)
            steps_data = steps_resp.get("activities-steps-intraday", {}).get("dataset", [])
            if steps_data:
                all_403 = False
        except RateLimitError:
            raise
        except Exception as e:
            if "403" not in str(e):
                all_403 = False
            print(f"  [!] Steps intraday unavailable for {day_str}: {e}")

        # If all endpoints returned 403, the app likely lacks intraday access
        if all_403:
            consecutive_403s += 1
            if consecutive_403s >= 2:
                print("  Intraday API access denied (403). Ensure your Fitbit app is registered")
                print("  as 'Personal' type at https://dev.fitbit.com/apps -- then re-auth.")
                return
            print(f"  [x] No intraday data for {act.get('activityName', 'Run')} on {day_str}")
            continue
        else:
            consecutive_403s = 0

        # Need at least distance data to compute meaningful splits
        if not dist_data and not hr_data:
            print(f"  [x] No intraday data for {act.get('activityName', 'Run')} on {day_str}")
            continue

        # Compress in memory (raw data never hits SQLite)
        # Convert distance from km to miles if needed
        distance_unit = act.get("distanceUnit", "")
        km_to_mi = "kilometer" in distance_unit.lower() or "km" in distance_unit.lower()
        intervals = _compress_intraday(hr_data, dist_data, steps_data, start_hhmm,
                                       convert_km_to_mi=km_to_mi)

        if intervals:
            cache.save_workout_intraday(log_id, intervals)

            # Compute and cache mile splits
            splits = _compute_mile_splits(intervals)
            if splits:
                cache.save_workout_splits(log_id, splits)

            print(f"  + {act.get('activityName', 'Run')} on {day_str}: "
                  f"{len(intervals)} intervals, {len(splits)} mile split(s)")


def _sync_run_weather(client: FitbitClient, activities: list):
    """Fetch and cache weather data for outdoor runs using GPS + Open-Meteo.

    For each outdoor run (hasGps=True), tries to download the TCX file for GPS
    coordinates. Falls back to DEFAULT_LATITUDE/DEFAULT_LONGITUDE from config
    if TCX is unavailable (e.g., 403 on non-Personal apps).
    """
    from core.weather import parse_tcx_first_point, fetch_run_weather, reverse_geocode
    from config import DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_LOCATION_NAME

    existing = cache.get_runs_with_weather()
    outdoor_runs = [
        a for a in activities
        if a.get("hasGps") is True
        and ("run" in a.get("activityName", "").lower()
             or "jog" in a.get("activityName", "").lower())
        and a.get("logId") not in existing
    ]

    if not outdoor_runs:
        if existing:
            print("Using cached run weather data...")
        return

    print(f"Enriching weather for {len(outdoor_runs)} outdoor run(s)...")
    tcx_available = True  # Track if TCX endpoint works at all

    for act in outdoor_runs:
        log_id = act.get("logId")
        start_time = act.get("originalStartTime") or act.get("startTime", "")
        run_date = start_time[:10] if start_time else ""
        if not run_date:
            continue

        lat, lon = None, None
        location_name = None

        # Try TCX for GPS coordinates (skip if endpoint already known to 403)
        if tcx_available:
            try:
                _check_rate_limit()
                tcx_xml = client.get_tcx(log_id)
                if tcx_xml:
                    gps = parse_tcx_first_point(tcx_xml)
                    if gps:
                        lat, lon = gps
                        location_name = reverse_geocode(lat, lon) or "GPS"
            except RateLimitError:
                raise
            except Exception as e:
                if "403" in str(e):
                    tcx_available = False
                    print("  TCX endpoint unavailable (403). Using default location.")

        # Fall back to configured default location
        if lat is None:
            lat, lon = DEFAULT_LATITUDE, DEFAULT_LONGITUDE
            location_name = DEFAULT_LOCATION_NAME + "*"

        # Extract run time window (start hour to end hour) in UTC
        try:
            if "T" in start_time:
                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                start_hour = dt.hour
            else:
                start_hour = 0
            duration_ms = act.get("duration", 0)
            duration_hours = duration_ms / 3_600_000
            end_hour = min(23, start_hour + max(1, int(duration_hours) + 1))
        except Exception:
            start_hour, end_hour = 0, 23

        # Fetch weather from Open-Meteo (free API, no Fitbit rate limit)
        weather = fetch_run_weather(lat, lon, run_date, start_hour, end_hour)
        if weather is None:
            print(f"  [!] No weather data for {run_date} (may be too recent)")
            continue

        weather["location_name"] = location_name

        # Cache it
        cache.save_run_weather(log_id, run_date, weather)

        temp = weather["avg_temp_f"]
        sky = weather["sky_condition"]
        precip = weather["precip_type"] or "No precipitation"
        print(f"  + Run on {run_date}: {temp:.0f}°F, {sky}, {precip}")
