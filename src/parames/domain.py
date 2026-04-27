from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HourForecast(BaseModel):
    time: datetime
    wind_speed: float | None = None
    wind_direction: float | None = None
    precipitation: float | None = None
    pressure_msl: float | None = None


class CandidateWindow(BaseModel):
    alert_name: str
    start: datetime
    end: datetime
    duration_hours: int
    avg_wind_speed_kmh: float
    max_wind_speed_kmh: float
    avg_direction_deg: float
    bise_pressure_gradient_hpa: float | None = None
    models: list[str]
    dry_filter_applied: bool
    score: int
    classification: str
