from __future__ import annotations
"""Fitbit Web API client with auth, rate limiting, and retry logic."""

import time
from datetime import date, datetime

import requests

from core.auth import get_valid_token
from config import FITBIT_API_BASE


class RateLimitError(Exception):
    """Raised when Fitbit API rate limit is hit."""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Resets in {retry_after}s (~{retry_after // 60} min)")


class FitbitClient:
    """Wrapper around the Fitbit Web API."""

    def __init__(self):
        self._session = requests.Session()
        self._request_timestamps: list[float] = []
        self._rate_limit = 150  # requests per hour

    def _headers(self) -> dict:
        token = get_valid_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _throttle(self):
        """Enforce rate limit of 150 requests/hour."""
        now = time.time()
        cutoff = now - 3600
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]

        if len(self._request_timestamps) >= self._rate_limit:
            wait = self._request_timestamps[0] - cutoff
            print(f"Rate limit approaching, waiting {wait:.0f}s...")
            time.sleep(wait)

        self._request_timestamps.append(now)

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Make an authenticated GET request with retry logic."""
        self._throttle()
        url = f"{FITBIT_API_BASE}{path}"

        for attempt in range(3):
            try:
                resp = self._session.get(url, headers=self._headers(), params=params)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After",
                                      resp.headers.get("fitbit-rate-limit-reset", 60)))
                    raise RateLimitError(retry_after)

                # Don't retry 400/403 — these won't resolve with retries
                if resp.status_code in (400, 403):
                    raise requests.exceptions.HTTPError(
                        f"{resp.status_code} Client Error: {resp.reason} for url: {url}",
                        response=resp,
                    )

                resp.raise_for_status()
                return resp.json()

            except (RateLimitError, requests.exceptions.HTTPError):
                raise
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                print(f"Request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)

        return {}

    # --- User Profile ---

    def get_profile(self) -> dict:
        """Get user profile: height, weight, age, stride length, etc."""
        return self._get("/1/user/-/profile.json")

    # --- Body & Weight ---

    def get_weight_log(self, start_date: str, end_date: str) -> dict:
        """Get weight log entries for a date range (max 31 days)."""
        return self._get(f"/1/user/-/body/log/weight/date/{start_date}/{end_date}.json")

    def get_body_fat_log(self, start_date: str, end_date: str) -> dict:
        """Get body fat log entries for a date range (max 31 days)."""
        return self._get(f"/1/user/-/body/log/fat/date/{start_date}/{end_date}.json")

    # --- Activity ---

    def get_activity_log_list(self, before_date: str, limit: int = 20, sort: str = "desc",
                              offset: int = 0) -> dict:
        """Get list of activity log entries."""
        return self._get("/1/user/-/activities/list.json", params={
            "beforeDate": before_date,
            "limit": limit,
            "sort": sort,
            "offset": offset,
        })

    def get_activity_time_series(self, resource: str, start_date: str, period: str) -> dict:
        """Get activity time series (steps, distance, floors, etc.).

        resource: steps, distance, floors, elevation, minutesSedentary,
                  minutesLightlyActive, minutesFairlyActive, minutesVeryActive,
                  activityCalories, calories
        period: 1d, 7d, 30d, 1w, 1m, 3m, 6m, 1y
        """
        return self._get(
            f"/1/user/-/activities/{resource}/date/{start_date}/{period}.json"
        )

    def get_daily_activity_summary(self, day: str) -> dict:
        """Get full daily activity summary for a specific date."""
        return self._get(f"/1/user/-/activities/date/{day}.json")

    def get_lifetime_stats(self) -> dict:
        """Get user's lifetime activity statistics."""
        return self._get("/1/user/-/activities.json")

    def get_workout_summary(self, activity_log_id: int) -> dict:
        """Get workout summary (cadence, ground contact time) for a run."""
        return self._get(f"/1/user/-/activities/{activity_log_id}/workout-summary.json")

    # --- Heart Rate ---

    def get_heart_rate_time_series(self, start_date: str, period: str) -> dict:
        """Get heart rate time series.

        period: 1d, 7d, 30d, 1w, 1m, 3m, 6m, 1y
        """
        return self._get(
            f"/1/user/-/activities/heart/date/{start_date}/{period}.json"
        )

    def get_heart_rate_by_date_range(self, start_date: str, end_date: str) -> dict:
        """Get heart rate time series by date range."""
        return self._get(
            f"/1/user/-/activities/heart/date/{start_date}/{end_date}.json"
        )

    # --- Cardio Fitness (VO2 Max) ---

    def get_vo2_max_summary(self, day: str) -> dict:
        """Get VO2 Max summary for a given date."""
        return self._get(f"/1/user/-/cardioscore/date/{day}.json")

    def get_vo2_max_by_range(self, start_date: str, end_date: str) -> dict:
        """Get VO2 Max data for a date range."""
        return self._get(f"/1/user/-/cardioscore/date/{start_date}/{end_date}.json")

    # --- Sleep ---

    def get_sleep_log_by_date(self, day: str) -> dict:
        """Get sleep log for a specific date."""
        return self._get(f"/1.2/user/-/sleep/date/{day}.json")

    def get_sleep_log_by_date_range(self, start_date: str, end_date: str) -> dict:
        """Get sleep log for a date range (max 100 days)."""
        return self._get(f"/1.2/user/-/sleep/date/{start_date}/{end_date}.json")

    # --- Water ---

    def get_water_log(self, day: str) -> dict:
        """Get water log entries and daily summary for a date."""
        return self._get(f"/1/user/-/foods/log/water/date/{day}.json")

    def get_water_goal(self) -> dict:
        """Get user's daily water consumption goal."""
        return self._get("/1/user/-/foods/log/water/goal.json")

    # --- SpO2 ---

    def get_spo2_summary(self, day: str) -> dict:
        """Get SpO2 (blood oxygen) summary for a date."""
        return self._get(f"/1/user/-/spo2/date/{day}.json")

    def get_spo2_by_range(self, start_date: str, end_date: str) -> dict:
        """Get SpO2 data for a date range (max 30 days)."""
        return self._get(f"/1/user/-/spo2/date/{start_date}/{end_date}.json")

    # --- Active Zone Minutes ---

    def get_active_zone_minutes(self, start_date: str, period: str) -> dict:
        """Get active zone minutes time series.

        period: 1d, 7d, 30d, 1w, 1m, 3m, 6m, 1y
        """
        return self._get(
            f"/1/user/-/activities/active-zone-minutes/date/{start_date}/{period}.json"
        )

    # --- TCX (GPS tracks) ---

    def get_tcx(self, activity_log_id: int) -> str:
        """Download TCX file for an activity. Returns raw XML string."""
        self._throttle()
        url = f"{FITBIT_API_BASE}/1/user/-/activities/{activity_log_id}.tcx"

        for attempt in range(3):
            try:
                resp = self._session.get(url, headers=self._headers())

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After",
                                      resp.headers.get("fitbit-rate-limit-reset", 60)))
                    raise RateLimitError(retry_after)

                if resp.status_code in (400, 403):
                    raise requests.exceptions.HTTPError(
                        f"{resp.status_code} Client Error: {resp.reason} for url: {url}",
                        response=resp,
                    )

                resp.raise_for_status()
                return resp.text

            except (RateLimitError, requests.exceptions.HTTPError):
                raise
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                print(f"TCX download failed ({e}), retrying in {wait}s...")
                time.sleep(wait)

        return ""

    # --- Intraday (workout-scoped) ---

    def get_heart_rate_intraday(self, day: str, start_time: str, end_time: str,
                                detail_level: str = "1sec") -> dict:
        """Get intraday heart rate data for a time window within a single day.

        Args:
            day: Date string (YYYY-MM-DD).
            start_time: Start time (HH:mm).
            end_time: End time (HH:mm).
            detail_level: Resolution — "1sec" or "1min". Defaults to "1sec".
        """
        return self._get(
            f"/1/user/-/activities/heart/date/{day}/{day}/{detail_level}/time/{start_time}/{end_time}.json"
        )

    def get_distance_intraday(self, day: str, start_time: str, end_time: str) -> dict:
        """Get 1-minute distance data for a time window within a single day.

        Args:
            day: Date string (YYYY-MM-DD).
            start_time: Start time (HH:mm).
            end_time: End time (HH:mm).
        """
        return self._get(
            f"/1/user/-/activities/distance/date/{day}/{day}/1min/time/{start_time}/{end_time}.json"
        )

    def get_steps_intraday(self, day: str, start_time: str, end_time: str) -> dict:
        """Get 1-minute steps data for a time window within a single day.

        Args:
            day: Date string (YYYY-MM-DD).
            start_time: Start time (HH:mm).
            end_time: End time (HH:mm).
        """
        return self._get(
            f"/1/user/-/activities/steps/date/{day}/{day}/1min/time/{start_time}/{end_time}.json"
        )
