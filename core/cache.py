from __future__ import annotations
"""SQLite caching layer for Fitbit API data.

Stores all fetched data locally so subsequent runs only need to fetch
data newer than the last sync — dramatically reducing API calls.
"""

import json
import os
import sqlite3
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fitbit_cache.db")


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite cache database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all cache tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_log (
            endpoint TEXT PRIMARY KEY,
            last_sync_date TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS weight_log (
            date TEXT PRIMARY KEY,
            weight_kg REAL,
            bmi REAL,
            fat REAL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS body_fat_log (
            date TEXT PRIMARY KEY,
            fat REAL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activities (
            log_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            activity_name TEXT,
            distance REAL,
            duration_ms INTEGER,
            calories INTEGER,
            avg_heart_rate INTEGER,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);

        CREATE TABLE IF NOT EXISTS workout_summaries (
            log_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_time_series (
            resource TEXT NOT NULL,
            date TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (resource, date)
        );

        CREATE TABLE IF NOT EXISTS heart_rate (
            date TEXT PRIMARY KEY,
            resting_hr INTEGER,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vo2_max (
            date TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sleep_log (
            log_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            is_main_sleep INTEGER,
            duration_ms INTEGER,
            efficiency INTEGER,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep_log(date);

        CREATE TABLE IF NOT EXISTS water_log (
            date TEXT PRIMARY KEY,
            total_ml REAL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS water_goal (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            goal_ml REAL,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spo2 (
            date TEXT PRIMARY KEY,
            avg_value REAL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS active_zone_minutes (
            date TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workout_intraday (
            log_id INTEGER NOT NULL,
            interval_index INTEGER NOT NULL,
            elapsed_sec INTEGER NOT NULL,
            avg_hr REAL,
            distance REAL,
            steps INTEGER,
            PRIMARY KEY (log_id, interval_index)
        );

        CREATE TABLE IF NOT EXISTS workout_splits (
            log_id INTEGER NOT NULL,
            mile_number INTEGER NOT NULL,
            split_time_sec REAL,
            pace_per_mile REAL,
            avg_hr REAL,
            avg_cadence REAL,
            cumulative_distance REAL,
            PRIMARY KEY (log_id, mile_number)
        );

        CREATE TABLE IF NOT EXISTS run_weather (
            log_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            location_name TEXT,
            avg_temp_f REAL,
            total_precip_in REAL,
            precip_type TEXT,
            sky_condition TEXT,
            cloud_cover_pct REAL,
            raw_data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_weather_date ON run_weather(date);

        CREATE TABLE IF NOT EXISTS confidence_scores (
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            score REAL,
            reasoning TEXT,
            PRIMARY KEY (date, model)
        );
    """)

    # Migration: add reasoning column if it doesn't exist yet
    try:
        conn.execute("SELECT reasoning FROM confidence_scores LIMIT 1")
    except Exception:
        try:
            conn.execute("ALTER TABLE confidence_scores ADD COLUMN reasoning TEXT")
        except Exception:
            pass

    conn.commit()
    conn.close()


def get_last_sync(endpoint: str) -> str | None:
    """Get the last sync date for an endpoint. Returns date string or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT last_sync_date FROM sync_log WHERE endpoint = ?", (endpoint,)
    ).fetchone()
    conn.close()
    return row["last_sync_date"] if row else None


def set_last_sync(endpoint: str, sync_date: str):
    """Update the last sync date for an endpoint."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sync_log (endpoint, last_sync_date, updated_at) VALUES (?, ?, ?)",
        (endpoint, sync_date, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# --- Profile ---

def save_profile(data: dict):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO profile (id, data, updated_at) VALUES (1, ?, ?)",
        (json.dumps(data), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_profile() -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    conn.close()
    return json.loads(row["data"]) if row else None


# --- Weight ---

def save_weight_entries(entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            "INSERT OR REPLACE INTO weight_log (date, weight_kg, bmi, fat, data) VALUES (?, ?, ?, ?, ?)",
            (e.get("date"), e.get("weight"), e.get("bmi"), e.get("fat"), json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_weight_entries(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM weight_log WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Body Fat ---

def save_body_fat_entries(entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            "INSERT OR REPLACE INTO body_fat_log (date, fat, data) VALUES (?, ?, ?)",
            (e.get("date"), e.get("fat"), json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_body_fat_entries(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM body_fat_log WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Activities ---

def save_activities(activities: list):
    conn = get_connection()
    for a in activities:
        start_time = a.get("originalStartTime") or a.get("startTime", "")
        act_date = start_time[:10] if start_time else ""
        conn.execute(
            """INSERT OR REPLACE INTO activities
               (log_id, date, activity_name, distance, duration_ms, calories, avg_heart_rate, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (a.get("logId"), act_date,
             a.get("activityName"), a.get("distance"), a.get("duration"),
             a.get("calories"), a.get("averageHeartRate"), json.dumps(a)),
        )
    conn.commit()
    conn.close()


def load_activities(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM activities WHERE date >= ? ORDER BY date DESC", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Workout Summaries ---

def save_workout_summary(log_id: int, data: dict):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO workout_summaries (log_id, data) VALUES (?, ?)",
        (log_id, json.dumps(data)),
    )
    conn.commit()
    conn.close()


def load_workout_summaries() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT log_id, data FROM workout_summaries").fetchall()
    conn.close()
    return {r["log_id"]: json.loads(r["data"]) for r in rows}


# --- Activity Time Series ---

def save_time_series(resource: str, entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            "INSERT OR REPLACE INTO activity_time_series (resource, date, value) VALUES (?, ?, ?)",
            (resource, e.get("dateTime"), e.get("value", "0")),
        )
    conn.commit()
    conn.close()


def load_time_series(resource: str, start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, value FROM activity_time_series WHERE resource = ? AND date >= ? ORDER BY date",
        (resource, start_date),
    ).fetchall()
    conn.close()
    return [{"dateTime": r["date"], "value": r["value"]} for r in rows]


# --- Heart Rate ---

def save_heart_rate(entries: list):
    conn = get_connection()
    for e in entries:
        rhr = e.get("value", {}).get("restingHeartRate")
        conn.execute(
            "INSERT OR REPLACE INTO heart_rate (date, resting_hr, data) VALUES (?, ?, ?)",
            (e.get("dateTime"), rhr, json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_heart_rate(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM heart_rate WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- VO2 Max ---

def save_vo2_max(entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            "INSERT OR REPLACE INTO vo2_max (date, value, data) VALUES (?, ?, ?)",
            (e.get("dateTime"), json.dumps(e.get("value", {})), json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_vo2_max(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM vo2_max WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Sleep ---

def save_sleep_logs(entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            """INSERT OR REPLACE INTO sleep_log
               (log_id, date, is_main_sleep, duration_ms, efficiency, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (e.get("logId"), e.get("dateOfSleep"), int(e.get("isMainSleep", False)),
             e.get("duration"), e.get("efficiency"), json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_sleep_logs(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM sleep_log WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Water ---

def save_water_log(day: str, total_ml: float, data: dict):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO water_log (date, total_ml, data) VALUES (?, ?, ?)",
        (day, total_ml, json.dumps(data)),
    )
    conn.commit()
    conn.close()


def load_water_logs(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, data FROM water_log WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


def save_water_goal(data: dict):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO water_goal (id, goal_ml, data, updated_at) VALUES (1, ?, ?, ?)",
        (data.get("goal", {}).get("goal", 0), json.dumps(data), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_water_goal() -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT data FROM water_goal WHERE id = 1").fetchone()
    conn.close()
    return json.loads(row["data"]) if row else None


# --- SpO2 ---

def save_spo2(entries: list):
    conn = get_connection()
    for e in entries:
        avg_val = e.get("value", {}).get("avg")
        dt = e.get("dateTime", e.get("date", ""))
        if dt:
            conn.execute(
                "INSERT OR REPLACE INTO spo2 (date, avg_value, data) VALUES (?, ?, ?)",
                (dt, avg_val, json.dumps(e)),
            )
    conn.commit()
    conn.close()


def load_spo2(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM spo2 WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Active Zone Minutes ---

def save_active_zone_minutes(entries: list):
    conn = get_connection()
    for e in entries:
        conn.execute(
            "INSERT OR REPLACE INTO active_zone_minutes (date, value, data) VALUES (?, ?, ?)",
            (e.get("dateTime"), json.dumps(e.get("value", {})), json.dumps(e)),
        )
    conn.commit()
    conn.close()


def load_active_zone_minutes(start_date: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT data FROM active_zone_minutes WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


# --- Workout Intraday (30-sec compressed) ---

def save_workout_intraday(log_id: int, intervals: list):
    """Save 30-second compressed intraday data for a workout.

    intervals: list of dicts with keys: interval_index, elapsed_sec, avg_hr, distance, steps
    """
    conn = get_connection()
    for iv in intervals:
        conn.execute(
            """INSERT OR REPLACE INTO workout_intraday
               (log_id, interval_index, elapsed_sec, avg_hr, distance, steps)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (log_id, iv["interval_index"], iv["elapsed_sec"],
             iv.get("avg_hr"), iv.get("distance"), iv.get("steps")),
        )
    conn.commit()
    conn.close()


def load_workout_intraday(log_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workout_intraday WHERE log_id = ? ORDER BY interval_index",
        (log_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_workouts_with_intraday() -> set:
    """Return set of log_ids that already have intraday data cached."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT log_id FROM workout_intraday"
    ).fetchall()
    conn.close()
    return {r["log_id"] for r in rows}


# --- Workout Splits (per-mile) ---

def save_workout_splits(log_id: int, splits: list):
    """Save computed per-mile splits for a workout.

    splits: list of dicts with keys: mile_number, split_time_sec, pace_per_mile,
            avg_hr, avg_cadence, cumulative_distance
    """
    conn = get_connection()
    for s in splits:
        conn.execute(
            """INSERT OR REPLACE INTO workout_splits
               (log_id, mile_number, split_time_sec, pace_per_mile,
                avg_hr, avg_cadence, cumulative_distance)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, s["mile_number"], s["split_time_sec"], s["pace_per_mile"],
             s.get("avg_hr"), s.get("avg_cadence"), s.get("cumulative_distance")),
        )
    conn.commit()
    conn.close()


def load_workout_splits(log_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workout_splits WHERE log_id = ? ORDER BY mile_number",
        (log_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_all_workout_splits() -> dict:
    """Return all splits grouped by log_id: {log_id: [split_dicts]}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workout_splits ORDER BY log_id, mile_number"
    ).fetchall()
    conn.close()
    from collections import defaultdict
    result = defaultdict(list)
    for r in rows:
        result[r["log_id"]].append(dict(r))
    return dict(result)


# --- Stats ---

def get_cache_stats() -> dict:
    """Return counts of cached records per table."""
    conn = get_connection()
    tables = ["profile", "weight_log", "body_fat_log", "activities",
              "heart_rate", "vo2_max", "sleep_log", "water_log", "spo2",
              "active_zone_minutes", "activity_time_series",
              "workout_intraday", "workout_splits", "run_weather"]
    stats = {}
    for table in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        except Exception:
            stats[table] = 0
    conn.close()
    return stats


# --- Run Weather ---

def save_run_weather(log_id: int, date_str: str, weather: dict):
    """Save weather data for an outdoor run."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO run_weather
           (log_id, date, latitude, longitude, location_name, avg_temp_f, total_precip_in,
            precip_type, sky_condition, cloud_cover_pct, raw_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (log_id, date_str,
         weather.get("latitude"), weather.get("longitude"),
         weather.get("location_name"),
         weather.get("avg_temp_f"), weather.get("total_precip_in"),
         weather.get("precip_type"), weather.get("sky_condition"),
         weather.get("cloud_cover_pct"), json.dumps(weather.get("raw_hourly", {}))),
    )
    conn.commit()
    conn.close()


def load_run_weather(start_date: str) -> dict:
    """Load weather data for outdoor runs since start_date. Returns {log_id: weather_dict}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM run_weather WHERE date >= ? ORDER BY date", (start_date,)
    ).fetchall()
    conn.close()
    return {r["log_id"]: dict(r) for r in rows}


def get_runs_with_weather() -> set:
    """Return set of log_ids that already have weather data cached."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT log_id FROM run_weather").fetchall()
    except Exception:
        rows = []
    conn.close()
    return {r["log_id"] for r in rows}
