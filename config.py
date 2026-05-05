"""Configuration module — loads environment variables and race config."""

import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID", "")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET", "")
FITBIT_REDIRECT_URI = os.getenv("FITBIT_REDIRECT_URI", "http://localhost:8080/callback")

FITBIT_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
FITBIT_API_BASE = "https://api.fitbit.com"

SCOPES = "activity heartrate sleep profile cardio_fitness weight oxygen_saturation nutrition location"

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".fitbit_tokens.json")
RACE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "race_config.json")


class RaceConfigError(Exception):
    """Raised when race_config.json is missing or invalid."""
    pass


def _load_race_config():
    """Load race configuration from race_config.json.

    Returns a dict with keys: race_name, race_date, race_distance_miles,
    data_start_date, target_time (optional), target_pace (optional).
    Raises RaceConfigError if the file doesn't exist.
    """
    if not os.path.exists(RACE_CONFIG_FILE):
        raise RaceConfigError(
            "No race_config.json found. Run `python main.py setup` to configure your race goal."
        )

    with open(RACE_CONFIG_FILE, "r") as f:
        config = json.load(f)

    required = ["race_name", "race_date", "race_distance_miles"]
    for key in required:
        if key not in config:
            raise RaceConfigError(f"race_config.json missing required field: {key}")

    # Derive data_start_date if not set (20 weeks before race)
    if "data_start_date" not in config or not config["data_start_date"]:
        race_dt = datetime.strptime(config["race_date"], "%Y-%m-%d")
        start_dt = race_dt - timedelta(weeks=20)
        config["data_start_date"] = start_dt.strftime("%Y-%m-%d")

    # Calculate target_pace if target_time is provided
    config.setdefault("target_time", None)
    config["target_pace"] = None
    if config["target_time"]:
        parts = config["target_time"].split(":")
        if len(parts) == 3:
            total_minutes = int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        elif len(parts) == 2:
            total_minutes = int(parts[0]) * 60 + int(parts[1])
        else:
            total_minutes = float(parts[0]) * 60
        config["target_pace"] = total_minutes / config["race_distance_miles"]

    return config


def _try_load_race_config():
    """Attempt to load race config, returning None on failure (for setup command)."""
    try:
        return _load_race_config()
    except RaceConfigError:
        return None


# Load race config — modules that import these will get the configured values.
# The setup command is the only command that works without race_config.json.
_race_config = _try_load_race_config()

if _race_config:
    RACE_NAME = _race_config["race_name"]
    RACE_DATE = _race_config["race_date"]
    RACE_DISTANCE_MILES = _race_config["race_distance_miles"]
    DATA_START_DATE = _race_config["data_start_date"]
    TARGET_TIME = _race_config["target_time"]
    TARGET_PACE = _race_config["target_pace"]
else:
    # Placeholders — only the setup command should run without config
    RACE_NAME = None
    RACE_DATE = None
    RACE_DISTANCE_MILES = None
    DATA_START_DATE = None
    TARGET_TIME = None
    TARGET_PACE = None


def require_race_config():
    """Call this at the start of any command that needs race config.
    Raises RaceConfigError if not configured."""
    if RACE_NAME is None:
        raise RaceConfigError(
            "No race_config.json found. Run `python main.py setup` to configure your race goal."
        )


# Default training location (used for weather when GPS is unavailable)
DEFAULT_LATITUDE = float(os.getenv("DEFAULT_LATITUDE", "43.1203"))
DEFAULT_LONGITUDE = float(os.getenv("DEFAULT_LONGITUDE", "-85.5600"))
DEFAULT_LOCATION_NAME = os.getenv("DEFAULT_LOCATION_NAME", "Rockford, MI")
