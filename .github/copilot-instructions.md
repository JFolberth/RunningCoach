# Copilot Instructions — Fitbit Race Training Tool

## Git Branching Convention

All changes must be made on a branch — **never commit directly to `main`**.

- **`feature/<name>`** — New functionality (e.g., `feature/add-pace-zones`)
- **`fix/<name>`** — Bug fixes (e.g., `fix/broken-weather-import`)

Workflow:
1. Create a GitHub Issue describing the work (bug report or feature request)
2. Branch from `main`: `git checkout -b feature/<name>` or `git checkout -b fix/<name>`
3. Make changes, commit with descriptive messages
4. Push and create a Pull Request referencing the issue (e.g., "Fixes #2")
5. Merge to `main` after review

## Running the App

```bash
pip install -r requirements.txt    # requests, python-dotenv, rich
python main.py setup               # Configure your race goal (required first)
python main.py auth                # OAuth 2.0 PKCE flow (opens browser)
python main.py assess              # Fetch data + fitness assessment
python main.py plan                # Generate training plan
python main.py report              # Save Markdown reports to reports/
python main.py calendar            # Workout calendar view
python main.py dashboard           # Generate HTML dashboard with Chart.js
```

No test suite, linter, or build system exists. Run commands directly with `python main.py <subcommand>`.

## Architecture

The app follows a linear data pipeline:

```
Fitbit API → FitbitClient → data_fetcher → SQLite cache → analyzer → output modules
```

- **config.py** — Loads race goal from `race_config.json` (created by `python main.py setup`). Exports `RACE_NAME`, `RACE_DATE`, `RACE_DISTANCE_MILES`, `DATA_START_DATE`, `TARGET_TIME`, `TARGET_PACE`. Also loads Fitbit API credentials from `.env`.
- **utils.py** — Shared utility functions used across packages.
- **core/auth.py** — OAuth 2.0 PKCE flow with a local HTTP callback server. Tokens stored in `.fitbit_tokens.json`. Auto-refreshes expired tokens.
- **core/fitbit_client.py** — `FitbitClient` class wrapping the Fitbit Web API. Handles client-side rate limiting (150 req/hr), exponential backoff retries, and auth header injection.
- **core/cache.py** — SQLite caching layer (`fitbit_cache.db`). Every data category has its own table. A `sync_log` table tracks the last sync date per endpoint.
- **core/data_fetcher.py** — Orchestrates all data collection. On first run, pulls full history; on subsequent runs, only fetches data since last sync. If rate-limited, sets a global `_rate_limited` flag so remaining endpoints gracefully fall back to cached data.
- **core/weather.py** — Weather data integration for training conditions.
- **analysis/analyzer.py** — Computes fitness metrics from raw data. Returns a dict with sections: `profile`, `body`, `running`, `cross_training`, `heart_rate`, `vo2_max`, `sleep`, `hydration`, `daily_activity`, `spo2`, `weekly_calories`, `splits`, `readiness`.
- **analysis/training_plan.py** — Generates a week-by-week plan based on Hal Higdon Intermediate 1 model. All workouts are long-distance easy runs (no tempo/interval splits). Includes long run progression, recovery weeks, taper, and HR zone calculations (Karvonen method).
- **output/report_generator.py** — Rich CLI display functions and Markdown report saving. All display functions follow the `_display_<section>(data)` pattern.
- **output/calendar_view.py** — Month-by-month calendar grid of workouts using Rich tables.
- **output/dashboard.py** — Reads directly from SQLite cache (not through data_fetcher) to generate a standalone HTML file with inline Chart.js. Also generates `activities.html` and `confidence_reasoning.html` as linked sub-pages.

## Key Conventions

- **All data flows as plain dicts** — no dataclasses, Pydantic models, or typed containers. The `analyze()` return structure and `generate_plan()` return structure are the implicit contracts between modules.
- **Lazy imports in CLI commands** — `main.py` defers all module imports inside `cmd_*` functions so the CLI stays fast and only loads what's needed.
- **Distance is always in miles** — Fitbit returns kilometers; normalization to miles happens at every layer. Activity distances are converted in `analysis/analyzer.py`, `output/calendar_view.py`, and `output/dashboard.py` by checking the `distanceUnit` field. Intraday distance data (used for mile splits) is converted from km to miles in `core/data_fetcher.py._compress_intraday()` before storage. All stored distances in `workout_intraday` and `workout_splits` tables are in miles.
- **Pace is minutes-per-mile** (float) — Formatted as `MM:SS/mi` via `_format_pace()` helpers (duplicated in `analysis/analyzer.py` and `analysis/training_plan.py`).
- **Workouts are long-distance easy runs** — No tempo, interval, or split-based workouts. All runs target Zone 2 (conversational pace). Speed comes from building endurance over distance.
- **Fitbit API date ranges have per-endpoint chunk limits** — weight: 31 days, sleep: 100 days, SpO2: 30 days. The `_date_chunks()` helper splits ranges accordingly.
- **Rate limit resilience** — `core/data_fetcher.py` uses a module-level `_rate_limited` flag. Once any endpoint hits a 429, all subsequent endpoints skip API calls and serve cached data.
- **Rich markup for CLI output** — All terminal output uses the `rich` library. Strings contain Rich markup like `[bold blue]...[/bold blue]`.
- **Race details come from `race_config.json`** — `RACE_DATE`, `RACE_NAME`, `RACE_DISTANCE_MILES`, `TARGET_TIME`, `TARGET_PACE` are loaded by `config.py`. Users run `python main.py setup` to configure. No hardcoded race constants exist.
- **Credentials come from `.env`** — `FITBIT_CLIENT_ID` and `FITBIT_CLIENT_SECRET` loaded via `python-dotenv`. Copy `.env.example` to `.env` to configure.
- **Confidence scores are Copilot-generated** — The `confidence_scores` table stores weekly AI model assessments (score + reasoning). These are generated by Copilot during data refresh sessions, not by the app itself. The data lives only in `fitbit_cache.db` — never commit data population scripts to the repo.
- **All cached data lives in `fitbit_cache.db`** — No raw data, generated assessments, or population scripts should be committed to source control. The database is the single source of truth for all fetched and derived data. See `docs/data-model.md` for the full schema reference.

## Refreshing Data

To refresh data, clear the `sync_log` table so the next run fetches new data incrementally:

```bash
sqlite3 fitbit_cache.db "DELETE FROM sync_log"
python main.py assess   # or any command — will re-fetch from last cached dates
```

**Never delete `fitbit_cache.db` without explicit user confirmation.** The Fitbit API has a 150 requests/hour rate limit and a full re-fetch from scratch is expensive. Assume "refresh" means pull the latest data on top of what's cached, not start over.
