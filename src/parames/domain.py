from __future__ import annotations

from datetime import datetime
from typing import Any

from pyodmongo import MainBaseModel
from pydantic import field_validator


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
    models: list[str]
    dry_filter_applied: bool
    score: int
    classification: str
    hours: list[WindowHour] = []
    plugin_outputs: dict[str, dict[str, Any]] = {}

    @field_validator("plugin_outputs", mode="before")
    @classmethod
    def _none_to_empty_dict(cls, v):
        return v if v is not None else {}
