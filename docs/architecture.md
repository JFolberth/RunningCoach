# Fitbit Race Training Tool — Architecture

A personal fitness analysis tool that pulls data from the Fitbit Web API, enriches it with weather and location context, caches everything locally in SQLite, and produces training plans, dashboards, and reports for any user-configured race goal.

---

## High-Level System Diagram

```mermaid
graph TD
    User([fa:fa-user User])
    CLI["main.py<br/>CLI Entry Point"]
    Pipeline["core/<br/>Data Pipeline"]
    Cache[("fitbit_cache.db<br/>SQLite Cache")]
    Analysis["analysis/<br/>Metrics & Planning"]
    Output["output/<br/>Reports & Dashboards"]

    User --> CLI
    CLI --> Pipeline
    Pipeline --> Cache
    Cache --> Analysis
    Analysis --> Output
    Cache --> Output
    Output -->|Rich CLI| User
    Output -->|Markdown & HTML| Reports["reports/"]

    FitbitAPI{{Fitbit Web API}}
    WeatherAPI{{Open-Meteo API}}
    GeoAPI{{Nominatim API}}

    FitbitAPI --> Pipeline
    WeatherAPI --> Pipeline
    GeoAPI --> Pipeline

    style FitbitAPI fill:#4a90d9,color:#fff
    style WeatherAPI fill:#f5a623,color:#fff
    style GeoAPI fill:#7ed321,color:#fff
    style Cache fill:#f8e71c,color:#333
    style User fill:#9013fe,color:#fff
```

---

## Data Flow Diagram

```mermaid
graph LR
    subgraph External APIs
        FitbitAPI{{Fitbit Web API<br/>OAuth 2.0 PKCE<br/>150 req/hr}}
        OpenMeteo{{Open-Meteo API<br/>Historical Weather}}
        Nominatim{{Nominatim API<br/>Reverse Geocoding}}
    end

    subgraph "core/ — Data Pipeline"
        Auth["auth.py<br/>OAuth 2.0 PKCE Flow"]
        Client["fitbit_client.py<br/>API Client + Rate Limiting<br/>+ Backoff Retries"]
        Fetcher["data_fetcher.py<br/>Orchestrator<br/>Incremental Sync"]
        Weather["weather.py<br/>GPS Parsing<br/>Weather Enrichment"]
        Cache["cache.py<br/>SQLite Caching<br/>+ sync_log"]
    end

    subgraph "analysis/ — Metrics & Planning"
        Analyzer["analyzer.py<br/>Running, Cross-Training, HR Zones,<br/>VO2 Max, Sleep, Body,<br/>Pace, Mile Splits"]
        Plan["training_plan.py<br/>Hal Higdon Intermediate 1<br/>Karvonen HR Zones"]
    end

    subgraph "output/ — Presentation"
        Report["report_generator.py<br/>Rich CLI Display<br/>+ Markdown Reports"]
        Calendar["calendar_view.py<br/>Rich CLI Calendar Grid"]
        Dashboard["dashboard.py<br/>HTML + Chart.js<br/>dashboard.html<br/>activities.html<br/>confidence_reasoning.html"]
    end

    FitbitAPI -->|Token Exchange| Auth
    Auth -->|Access Token| Client
    FitbitAPI -->|Activity, Sleep,<br/>HR, SpO2, Body| Client
    Client -->|JSON + TCX| Fetcher
    Fetcher -->|Raw Data| Cache
    Client -->|TCX Data| Weather
    Weather -->|GPS Coords| Nominatim
    Weather -->|Lat/Lon + Date| OpenMeteo
    Weather -->|Weather + Location| Fetcher
    Fetcher -->|Weather Data| Cache

    Cache -->|Cached Data| Analyzer
    Cache -->|Cached Data| Plan
    Analyzer -->|Assessment Dict| Report
    Analyzer -->|Assessment Dict| Calendar
    Plan -->|Plan Dict| Report
    Cache -->|Direct SQL Read| Dashboard
    Cache -->|Direct SQL Read| Calendar
```

---

## Module Dependency Diagram

```mermaid
graph TD
    subgraph "Shared"
        Config["config.py<br/>Env vars, API URLs,<br/>Race constants,<br/>DATA_START_DATE"]
        Utils["utils.py<br/>format_pace()<br/>KM_TO_MILES<br/>get_week_start()"]
    end

    subgraph "core/"
        Auth["core/auth.py"]
        Client["core/fitbit_client.py"]
        Fetcher["core/data_fetcher.py"]
        CacheMod["core/cache.py"]
        WeatherMod["core/weather.py"]
    end

    subgraph "analysis/"
        Analyzer["analysis/analyzer.py"]
        TrainingPlan["analysis/training_plan.py"]
    end

    subgraph "output/"
        ReportGen["output/report_generator.py"]
        CalendarView["output/calendar_view.py"]
        DashboardMod["output/dashboard.py"]
    end

    Main["main.py<br/>CLI Entry Point"]

    %% main.py imports
    Main -->|authorize| Auth
    Main -->|fetch_all_data| Fetcher
    Main -->|analyze| Analyzer
    Main -->|display / save| ReportGen
    Main -->|generate_plan| TrainingPlan
    Main -->|display_calendar| CalendarView
    Main -->|generate_dashboard| DashboardMod

    %% core/ internal imports
    Auth --> Config
    Client -->|get_valid_token| Auth
    Client --> Config
    Fetcher -->|FitbitClient| Client
    Fetcher -->|cache module| CacheMod
    Fetcher --> Config
    Fetcher --> Utils

    %% analysis/ imports
    Analyzer --> Config
    Analyzer --> Utils
    TrainingPlan --> Config
    TrainingPlan --> Utils

    %% output/ imports
    ReportGen --> Config
    CalendarView --> Config
    CalendarView --> Utils
    DashboardMod -->|DB_PATH| CacheMod
    DashboardMod --> Config
    DashboardMod --> Utils

    style Main fill:#9013fe,color:#fff
    style Config fill:#f5a623,color:#fff
    style Utils fill:#f5a623,color:#fff
```

---

## Folder Structure

```
fitbit-data/
├── main.py                  # CLI entry point (subcommands: setup, auth, assess, plan, progress, report, calendar, dashboard)
├── config.py                # Race config loader + environment variables
├── utils.py                 # Shared helpers: format_pace(), KM_TO_MILES, get_week_start()
├── requirements.txt         # requests, python-dotenv, rich
├── .env                     # FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET
├── .fitbit_tokens.json      # OAuth tokens (auto-generated)
├── fitbit_cache.db          # SQLite cache (auto-generated)
│
├── core/                    # Data pipeline — fetch, cache, enrich
│   ├── auth.py              # OAuth 2.0 PKCE flow + token refresh
│   ├── fitbit_client.py     # Fitbit API wrapper (rate limiting, retries)
│   ├── data_fetcher.py      # Orchestrates incremental sync across endpoints
│   ├── cache.py             # SQLite caching layer + sync_log tracking
│   └── weather.py           # TCX GPS parsing → weather + reverse geocode
│
├── analysis/                # Metrics computation and plan generation
│   ├── analyzer.py          # Fitness assessment (running, cross-training, HR, VO2 max, sleep, body, pace, splits)
│   └── training_plan.py     # Hal Higdon Intermediate 1 plan + Karvonen HR zones
│
├── output/                  # Presentation layer
│   ├── report_generator.py  # Rich CLI display + Markdown report files
│   ├── calendar_view.py     # Rich CLI month-by-month calendar grid
│   └── dashboard.py         # Standalone HTML dashboard with Chart.js
│
├── reports/                 # Generated output files
│   ├── dashboard.html       # Interactive charts dashboard
│   ├── activities.html      # Activity detail pages
│   ├── confidence_reasoning.html  # AI model reasoning table
│   └── *.md                 # Markdown assessment and plan reports
│
└── docs/                    # Documentation
    ├── architecture.md      # This file
    └── data-model.md        # SQLite schema reference for fitbit_cache.db
```

---

## Package Descriptions

### `core/` — Data Pipeline

Handles all communication with external APIs and local data persistence. The pipeline runs as: **authenticate → fetch → cache → enrich**. On first run, pulls full history back to `DATA_START_DATE` (defaults to 20 weeks before race date, configurable in `race_config.json`). On subsequent runs, performs incremental sync from the last cached date per endpoint. If the Fitbit API rate limit (150 req/hr) is hit, a module-level `_rate_limited` flag causes all remaining endpoints to gracefully fall back to cached data.

### `analysis/` — Metrics & Planning

Pure computation modules that read cached data and produce structured dicts. `analyzer.py` computes a comprehensive fitness assessment covering running stats, cross-training metrics, heart rate zones, VO2 max estimates, sleep quality, body composition, pace analysis, and mile splits. `training_plan.py` generates a week-by-week training schedule based on the Hal Higdon Intermediate 1 model, with heart rate zone targets calculated via the Karvonen method.

### `output/` — Presentation

Renders analysis results into user-facing formats. All modules consume either the analyzer's assessment dict, the training plan dict, or read directly from the SQLite cache. `report_generator.py` handles both Rich CLI terminal output and Markdown file generation. `calendar_view.py` renders a workout calendar grid. `dashboard.py` bypasses the analyzer and queries the SQLite database directly to produce standalone HTML files with embedded Chart.js visualizations, including `activities.html` for activity details and `confidence_reasoning.html` for AI model score explanations.

### `config.py` — Shared Configuration

The most-imported module in the codebase (7 dependents). Loads race goal from `race_config.json` (created by `python main.py setup`). Exports `RACE_NAME`, `RACE_DATE`, `RACE_DISTANCE_MILES`, `DATA_START_DATE`, `TARGET_TIME`, `TARGET_PACE`. Also centralizes environment variables (`FITBIT_CLIENT_ID`, `FITBIT_CLIENT_SECRET`), API base URLs, and OAuth endpoints.

### `utils.py` — Shared Utilities

Small helper functions used across packages: `format_pace()` for MM:SS/mi formatting, `KM_TO_MILES` conversion constant, and `get_week_start()` for week-based grouping. Imported by 4 modules across `core/`, `analysis/`, and `output/`.
