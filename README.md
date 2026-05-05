# Fitbit Race Training Tool

A Fitbit-powered training tool that fetches your biometric data and provides personalized training recommendations for **any race goal** — from a 5K to an ultramarathon.

## Setup

### 1. Register a Fitbit App

1. Go to [https://dev.fitbit.com/apps](https://dev.fitbit.com/apps)
2. Register a new application:
   - **OAuth 2.0 Application Type:** Personal
   - **Redirect URL:** `http://localhost:8080/callback`
   - **Default Access Type:** Read Only

### 2. Configure Credentials

```bash
cp .env.example .env
# Edit .env with your Client ID and Client Secret
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Your Race Goal

```bash
python main.py setup
```

This interactive prompt asks for:
- **Race name** (e.g., "Chicago Marathon", "Couch to 5K")
- **Race date** (YYYY-MM-DD)
- **Race distance** in miles (e.g., 3.1, 6.2, 13.1, 26.2)
- **Target completion time** (optional — HH:MM:SS)
- **Training start date** (optional — defaults to 20 weeks before race)

Configuration is saved to `race_config.json` (user-specific, gitignored). Re-run `setup` anytime to update your goal.

<details>
<summary>Example race_config.json</summary>

```json
{
  "race_name": "Chicago Marathon",
  "race_date": "2026-10-11",
  "race_distance_miles": 26.2,
  "target_time": "4:00:00",
  "data_start_date": "2026-05-24"
}
```
</details>

### 5. Authenticate with Fitbit

```bash
python main.py auth
```

This opens your browser to authorize the app. After granting access, tokens are saved locally.

## Usage

```bash
# Configure your race goal (required first step)
python main.py setup

# Run OAuth flow and save tokens
python main.py auth

# Fetch data and show fitness assessment
python main.py assess

# Generate personalized training plan
python main.py plan

# Show weekly progress vs training plan
python main.py progress

# Generate and save full report to reports/
python main.py report

# Show workout calendar
python main.py calendar

# Generate interactive HTML dashboard
python main.py dashboard
```

## Project Structure

```
fitbit-data/
├── main.py                  # CLI entry point
├── config.py                # Race config loader + environment variables
├── race_config.json         # Your race goal (created by setup, gitignored)
├── utils.py                 # Shared utility functions
├── requirements.txt
├── README.md
├── docs/
│   └── architecture.md      # Detailed architecture documentation
├── core/                    # Data acquisition and caching
│   ├── auth.py              # OAuth 2.0 PKCE authentication
│   ├── fitbit_client.py     # Fitbit Web API client
│   ├── cache.py             # SQLite caching layer
│   ├── data_fetcher.py      # Data collection orchestrator
│   └── weather.py           # Weather data integration
├── analysis/                # Data analysis and planning
│   ├── analyzer.py          # Fitness metrics computation
│   └── training_plan.py     # Training plan generator
├── output/                  # Reporting and visualization
│   ├── report_generator.py  # CLI display and Markdown reports
│   ├── calendar_view.py     # Workout calendar grid
│   └── dashboard.py         # HTML dashboard with Chart.js
├── reports/                 # Generated reports (gitignored)
└── .github/
    └── copilot-instructions.md
```

## Data Collected

| Category | Details |
|---|---|
| Profile | Height, weight, age, stride length |
| Body | Weight & body fat trends |
| Activities | Running logs, steps, floors, active minutes |
| Heart Rate | Resting HR, HR zones, time series |
| VO2 Max | Cardio fitness score |
| Sleep | Duration, quality, stages |
| Water | Daily intake vs goal |
| SpO2 | Blood oxygen levels |
| Workouts | Cadence, ground contact time |

## Race Goal Examples

| Goal | Distance | Setup Values |
|---|---|---|
| Couch to 5K | 3.1 mi | `distance: 3.1` |
| 10K | 6.2 mi | `distance: 6.2` |
| Half Marathon | 13.1 mi | `distance: 13.1` |
| Marathon | 26.2 mi | `distance: 26.2` |
| Ultra (50K) | 31.1 mi | `distance: 31.1` |
