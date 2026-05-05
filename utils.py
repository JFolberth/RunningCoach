"""Shared utility functions for the Fitbit training tool."""

from datetime import timedelta


KM_TO_MILES = 0.621371


def format_pace(minutes_per_mile, suffix=False):
    """Format pace as MM:SS or MM:SS/mi.
    
    Args:
        minutes_per_mile: Pace in minutes per mile (float).
        suffix: If True, append '/mi' to the result.
    """
    if not minutes_per_mile or minutes_per_mile <= 0:
        return "N/A"
    mins = int(minutes_per_mile)
    secs = int((minutes_per_mile - mins) * 60)
    result = f"{mins}:{secs:02d}"
    if suffix:
        result += "/mi"
    return result


def km_to_miles(km):
    """Convert kilometers to miles."""
    if km is None:
        return None
    return km * KM_TO_MILES


def get_week_start(date_obj):
    """Get Monday of the week containing date_obj."""
    return date_obj - timedelta(days=date_obj.weekday())
