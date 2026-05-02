from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pyodmongo import MainBaseModel
from pydantic import field_validator


class Classification(StrEnum):
    weak = "weak"
    candidate = "candidate"
    strong = "strong"
    excellent = "excellent"
    unavailable = "unavailable"


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
    wind_gusts: float | None = None
    cape: float | None = None
    showers: float | None = None


class RuleEvaluation(MainBaseModel):
    name: str
    observed: Any
    threshold: Any | None = None
    outcome: Literal["pass", "warn", "fail", "info"]
    delta: float | None = None
    message: str | None = None


class HourEvaluation(MainBaseModel):
    time: datetime
    accepted: bool
    matching_models: list[str] = []
    rejection_reasons: list[str] = []
    rules: list[RuleEvaluation] = []


class ScoringTrace(MainBaseModel):
    weights: dict[str, float]
    subscores: dict[str, float | None]
    contributions: dict[str, dict[str, Any]]
    weight_total: float
    weighted_sum: float
    raw_score: float | None
    final_score: int | None
    classification: Classification
    tiers: dict[str, int]


class PluginReport(MainBaseModel):
    type: str
    schema_version: int = 1
    summary: str | None = None
    config_snapshot: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    hourly: list[dict[str, Any]] = []
    rules: list[RuleEvaluation] = []
    notes: list[str] = []


class ModelHourForecast(MainBaseModel):
    time: datetime
    wind_speed: float | None = None
    wind_direction: float | None = None
    wind_gusts: float | None = None
    precipitation: float | None = None
    pressure_msl: float | None = None
    cape: float | None = None
    showers: float | None = None


class EvaluationReport(MainBaseModel):
    schema_version: int = 1
    profile_snapshot: dict[str, Any]
    horizon_start: datetime
    horizon_end: datetime
    forecast_models: list[str]
    hour_evaluations: list[HourEvaluation] = []
    raw_forecasts: dict[str, list[ModelHourForecast]] = {}
    scoring: ScoringTrace
    plugin_reports: dict[str, PluginReport] = {}


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
    # 0–100 weighted-mean composite. None when every signal opts out.
    score: int | None
    classification: Classification
    # Per-signal sub-scores (0–100) that fed the composite. None entries opted out.
    subscores: dict[str, float | None] = {}
    hours: list[WindowHour] = []
    plugin_outputs: dict[str, dict[str, Any]] = {}

    @field_validator("plugin_outputs", mode="before")
    @classmethod
    def _none_to_empty_dict(cls, v):
        return v if v is not None else {}

    @field_validator("subscores", mode="before")
    @classmethod
    def _subscores_none_to_empty(cls, v):
        return v if v is not None else {}
