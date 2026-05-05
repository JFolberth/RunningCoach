# Data Model — `fitbit_cache.db`

All application data is stored in a single SQLite database (`fitbit_cache.db`). This file is **not committed to source control** — it is generated at runtime by fetching data from external APIs and Copilot-generated assessments.

> **Convention:** No raw data or data population scripts should be committed to the repo. The database is the single source of truth.

---

## Table Reference

### `sync_log` — Incremental Sync Tracking

Tracks the last sync date per API endpoint so subsequent runs only fetch new data.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `endpoint` | TEXT | PK | API endpoint name (e.g., `activities`, `weight`, `sleep`) |
| `last_sync_date` | TEXT | | ISO date of last successful sync |
| `updated_at` | TEXT | | Timestamp of last update |

---

### `profile` — User Profile

Single-row table with the Fitbit user profile.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `id` | INTEGER | PK | Always 1 (singleton) |
| `data` | TEXT | | Full JSON profile response |
| `updated_at` | TEXT | | Timestamp of last update |

---

### `weight_log` — Daily Weight Measurements

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `weight_kg` | REAL | | Weight in **kilograms** (raw from Fitbit) |
| `bmi` | REAL | | BMI value |
| `fat` | REAL | | Body fat percentage |
| `data` | TEXT | | Full JSON response |

---

### `body_fat_log` — Body Fat Measurements

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `fat` | REAL | | Body fat percentage |
| `data` | TEXT | | Full JSON response |

---

### `activities` — Activity Logs

All logged activities (runs, rowing, walks, etc.).

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit activity log ID |
| `date` | TEXT | IDX | ISO date |
| `activity_name` | TEXT | | Activity type (e.g., `Run`, `Treadmill run`, `Rowing machine`, `Walk`) |
| `distance` | REAL | | Distance in **kilometers** (raw from Fitbit API). Multiply by `0.621371` for miles. |
| `duration_ms` | INTEGER | | Duration in milliseconds |
| `calories` | INTEGER | | Calories burned |
| `avg_heart_rate` | INTEGER | | Average heart rate during activity |
| `data` | TEXT | | Full JSON response (includes `distanceUnit`, `activityName`, etc.) |

> ⚠️ **Distance is stored in kilometers.** All display/analysis code must convert to miles using `KM_TO_MILES` from `utils.py`. The `data` JSON contains `distanceUnit` for verification.

> **Activity names to know:** Outdoor runs are `Run`, treadmill runs are `Treadmill run` (not `Treadmill`), rowing is `Rowing machine`.

---

### `workout_summaries` — Detailed Workout Data

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit activity log ID |
| `data` | TEXT | | Full JSON workout summary |

---

### `activity_time_series` — Daily Activity Metrics

Daily aggregates for steps, distance, floors, active minutes, etc.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `resource` | TEXT | PK | Metric name (e.g., `steps`, `distance`, `floors`) |
| `date` | TEXT | PK | ISO date |
| `value` | TEXT | | Metric value as string |

---

### `heart_rate` — Daily Resting Heart Rate

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `resting_hr` | INTEGER | | Resting heart rate (bpm) |
| `data` | TEXT | | Full JSON response (includes HR zones) |

---

### `vo2_max` — VO2 Max Estimates

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `value` | TEXT | | JSON string containing `vo2Max` field (e.g., `{"vo2Max": "40"}`) |
| `data` | TEXT | | Full JSON response |

> **Note:** The `value` column is a JSON string, not a plain number. Parse with `json.loads(value).get("vo2Max")`.

---

### `sleep_log` — Sleep Sessions

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit sleep log ID |
| `date` | TEXT | IDX | ISO date |
| `is_main_sleep` | INTEGER | | 1 if main sleep, 0 if nap |
| `duration_ms` | INTEGER | | Sleep duration in milliseconds. Divide by `3600000` for hours. |
| `efficiency` | INTEGER | | Sleep efficiency percentage (0-100) |
| `data` | TEXT | | Full JSON response (includes sleep stages) |

---

### `water_log` — Daily Water Intake

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `total_ml` | REAL | | Total water intake in milliliters |
| `data` | TEXT | | Full JSON response |

---

### `water_goal` — Water Intake Goal

Single-row table with the daily water goal.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `id` | INTEGER | PK | Always 1 (singleton) |
| `goal_ml` | REAL | | Daily water goal in milliliters |
| `data` | TEXT | | Full JSON response |
| `updated_at` | TEXT | | Timestamp of last update |

---

### `spo2` — Blood Oxygen (SpO2)

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `avg_value` | REAL | | Average SpO2 percentage |
| `data` | TEXT | | Full JSON response |

---

### `active_zone_minutes` — Active Zone Minutes

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date |
| `value` | TEXT | | Zone minutes value |
| `data` | TEXT | | Full JSON response |

---

### `workout_intraday` — Per-Interval Workout Data

Compressed intraday data for workouts (time-series within a single activity).

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit activity log ID |
| `interval_index` | INTEGER | PK | Sequential interval number |
| `elapsed_sec` | INTEGER | | Seconds elapsed since activity start |
| `avg_hr` | REAL | | Average heart rate for interval |
| `distance` | REAL | | Distance in **miles** (converted before storage) |
| `steps` | INTEGER | | Step count for interval |

> **Note:** Unlike the `activities` table, intraday distances are pre-converted to miles in `data_fetcher._compress_intraday()`.

---

### `workout_splits` — Per-Mile Split Data

Mile-by-mile splits for running activities.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit activity log ID |
| `mile_number` | INTEGER | PK | Mile number (1-based) |
| `split_time_sec` | REAL | | Time for this mile in seconds |
| `pace_per_mile` | REAL | | Pace in minutes per mile |
| `avg_hr` | REAL | | Average heart rate during this mile |
| `avg_cadence` | REAL | | Average cadence (steps/min) |
| `cumulative_distance` | REAL | | Cumulative distance in **miles** |

> **Note:** All distances in this table are in miles (pre-converted).

---

### `run_weather` — Weather Data for Outdoor Runs

Weather conditions for outdoor running activities, enriched via Open-Meteo API.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `log_id` | INTEGER | PK | Fitbit activity log ID |
| `date` | TEXT | IDX | ISO date |
| `latitude` | REAL | | GPS latitude from TCX data |
| `longitude` | REAL | | GPS longitude from TCX data |
| `location_name` | TEXT | | Reverse-geocoded location name |
| `avg_temp_f` | REAL | | Average temperature in Fahrenheit |
| `total_precip_in` | REAL | | Total precipitation in inches |
| `precip_type` | TEXT | | Precipitation type (Rain, Snow, etc.) |
| `sky_condition` | TEXT | | Sky description (Sunny, Overcast, etc.) |
| `cloud_cover_pct` | REAL | | Cloud cover percentage |
| `raw_data` | TEXT | | Full weather API response |

---

### `confidence_scores` — AI Model Race Readiness Assessments

Weekly confidence scores from 5 AI models assessing half marathon readiness. **Generated by Copilot during data refresh sessions**, not by the app itself.

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| `date` | TEXT | PK | ISO date (weekly cadence, typically Mondays) |
| `model` | TEXT | PK | AI model name (GPT-4.1, GPT-5.1, Gemini 3 Pro, Opus 4.5, Sonnet 4.5) |
| `score` | REAL | | Confidence score 1-10 with tenths precision (e.g., 7.3) |
| `reasoning` | TEXT | | Point-in-time explanation of why the model scored this way |

> **Important:** Each week's reasoning must only reference fitness data available through the end of that week — no future data leakage. Scores and reasoning are populated by Copilot, not by the application code.

---

## Data Source Summary

| Table | Source | Units to Watch |
|-------|--------|---------------|
| `sync_log` | Internal tracking | — |
| `profile` | Fitbit API | — |
| `weight_log` | Fitbit API | `weight_kg` is **kilograms** |
| `body_fat_log` | Fitbit API | — |
| `activities` | Fitbit API | `distance` is **kilometers** |
| `workout_summaries` | Fitbit API | — |
| `activity_time_series` | Fitbit API | — |
| `heart_rate` | Fitbit API | — |
| `vo2_max` | Fitbit API | `value` is JSON string |
| `sleep_log` | Fitbit API | `duration_ms` is **milliseconds** |
| `water_log` | Fitbit API | `total_ml` is **milliliters** |
| `water_goal` | Fitbit API | `goal_ml` is **milliliters** |
| `spo2` | Fitbit API | — |
| `active_zone_minutes` | Fitbit API | — |
| `workout_intraday` | Fitbit API (processed) | `distance` is **miles** (pre-converted) |
| `workout_splits` | Fitbit API (processed) | All distances in **miles** (pre-converted) |
| `run_weather` | Open-Meteo + Nominatim APIs | `avg_temp_f` is **Fahrenheit** |
| `confidence_scores` | Copilot-generated | — |
