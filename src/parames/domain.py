from __future__ import annotations

from datetime import datetime

from pyodmongo import MainBaseModel


class WindowHour(MainBaseModel):
    """Per-hour data point within a CandidateWindow, used for charting."""

    time: datetime
    avg_wind_speed_kmh: float
    avg_direction_deg: float
    avg_precipitation_mm_per_hour: float | None = None
    in_window: bool = True  # False for ±context hours outside the alert window


class HourForecast(MainBaseModel):
    time: datetime
    wind_speed: float | None = None
    wind_direction: float | None = None
    precipitation: float | None = None
    pressure_msl: float | None = None


class CandidateWindow(MainBaseModel):
    alert_name: str
    start: datetime
    end: datetime
    duration_hours: int
    avg_wind_speed_kmh: float
    max_wind_speed_kmh: float
    avg_direction_deg: float
    avg_precipitation_mm_per_hour: float | None = None
    max_precipitation_mm_per_hour: float | None = None
    bise_pressure_gradient_hpa: float | None = None
    models: list[str]
    dry_filter_applied: bool
    score: int
    classification: str
    hours: list[WindowHour] = []
