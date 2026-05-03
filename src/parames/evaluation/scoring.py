from __future__ import annotations

from datetime import timedelta
from typing import Any

from parames.config import AlertProfileConfig, ScoringConfig
from parames.domain import (
    CandidateWindow,
    Classification,
    EvaluationReport,
    HourEvaluation,
    ModelForecastSeries,
    PluginReport,
    ScoringTrace,
    WindowHour,
)
from parames.evaluation.direction import vector_average_direction
from parames.evaluation.wind import subscore_wind_speed
from parames.evaluation.windows import EvaluatedHour
from parames.plugins import EvaluationPlugin
from parames.plugins.base import PluginScoringResult

import logging

logger = logging.getLogger(__name__)
_warned_unknown_plugins: set[str] = set()


def _classify(score: int | None, tiers) -> Classification:
    if score is None:
        return Classification.unavailable
    if score >= tiers.excellent_min:
        return Classification.excellent
    if score >= tiers.strong_min:
        return Classification.strong
    if score >= tiers.candidate_min:
        return Classification.candidate
    return Classification.weak


def _build_weight_map(
    plugins: list[EvaluationPlugin],
    scoring: ScoringConfig,
) -> dict[str, float]:
    weights: dict[str, float] = {
        "wind_speed": scoring.weights.wind_speed,
    }
    plugin_weights = scoring.weights.plugins
    for plugin in plugins:
        if plugin.type in plugin_weights:
            weights[plugin.type] = plugin_weights[plugin.type]
        else:
            if plugin.type not in _warned_unknown_plugins:
                logger.warning(
                    "No weight configured for plugin %r in scoring.weights.plugins; defaulting to 1.0",
                    plugin.type,
                )
                _warned_unknown_plugins.add(plugin.type)
            weights[plugin.type] = 1.0
    return weights


def build_candidate_windows(
    profile: AlertProfileConfig,
    accepted_hours: list[EvaluatedHour],
    *,
    plugins: list[EvaluationPlugin] | None = None,
    plugin_data: dict[str, Any] | None = None,
    scoring: ScoringConfig | None = None,
    hour_evaluations: list[HourEvaluation] | None = None,
    raw_forecasts: list[ModelForecastSeries] | None = None,
) -> list[CandidateWindow]:
    if not accepted_hours:
        return []
    windows: list[list[EvaluatedHour]] = [[accepted_hours[0]]]
    for hour in accepted_hours[1:]:
        previous = windows[-1][-1]
        if hour.time - previous.time == timedelta(hours=1):
            windows[-1].append(hour)
        else:
            windows.append([hour])

    effective_scoring = scoring if scoring is not None else ScoringConfig()
    return [
        score_window(
            profile,
            window,
            plugins=plugins or [],
            plugin_data=plugin_data or {},
            scoring=effective_scoring,
            hour_evaluations=hour_evaluations,
            raw_forecasts=raw_forecasts,
        )
        for window in windows
        if len(window) >= profile.wind.min_consecutive_hours
    ]


def score_window(
    profile: AlertProfileConfig,
    hours: list[EvaluatedHour],
    *,
    plugins: list[EvaluationPlugin] | None = None,
    plugin_data: dict[str, Any] | None = None,
    scoring: ScoringConfig | None = None,
    hour_evaluations: list[HourEvaluation] | None = None,
    raw_forecasts: list[ModelForecastSeries] | None = None,
) -> CandidateWindow:
    plugins = plugins or []
    plugin_data = plugin_data or {}
    effective_scoring = scoring if scoring is not None else ScoringConfig()

    avg_speed = sum(hour.avg_wind_speed_kmh for hour in hours) / len(hours)
    max_speed = max(hour.max_wind_speed_kmh for hour in hours)
    avg_direction = vector_average_direction([hour.avg_direction_deg for hour in hours])
    precipitation_values = [
        hour.avg_precipitation_mm_per_hour
        for hour in hours
        if hour.avg_precipitation_mm_per_hour is not None
    ]
    avg_precipitation = (
        sum(precipitation_values) / len(precipitation_values)
        if len(precipitation_values) == len(hours)
        else None
    )
    max_precipitation = max(precipitation_values) if precipitation_values else None

    contributing_models = sorted({model for hour in hours for model in hour.models})

    subscores: dict[str, float | None] = {
        "wind_speed": subscore_wind_speed([h.avg_wind_speed_kmh for h in hours], profile.wind),
    }

    plugin_outputs: dict[str, dict[str, Any]] = {}
    plugin_reports: list[PluginReport] = []
    for plugin in plugins:
        result: PluginScoringResult = plugin.score_window(
            window_times=[hour.time for hour in hours],
            prefetched=plugin_data.get(plugin.type),
            contributing_models=contributing_models,
        )
        subscores[plugin.type] = result.sub_score
        if result.output:
            plugin_outputs[plugin.type] = result.output
        if result.report is not None:
            plugin_reports.append(result.report)

    weights = _build_weight_map(plugins, effective_scoring)

    # Compute contributions and aggregate
    weighted_sum = 0.0
    weight_total = 0.0
    contributions: dict[str, dict[str, Any]] = {}
    for name, value in subscores.items():
        w = weights.get(name, 0.0)
        included = value is not None and w > 0
        if included:
            weighted_sum += w * value  # type: ignore[operator]
            weight_total += w
        contributions[name] = {
            "weight": w,
            "sub_score": value,
            "weighted_value": round(w * value, 4) if included else None,  # type: ignore[operator]
            "included": included,
        }

    raw_score = weighted_sum / weight_total if weight_total > 0 else None
    score = max(0, min(100, round(raw_score))) if raw_score is not None else None
    classification = _classify(score, effective_scoring.tiers)

    scoring_trace = ScoringTrace(
        weights=weights,
        subscores=subscores,
        contributions=contributions,
        weight_total=round(weight_total, 4),
        weighted_sum=round(weighted_sum, 4),
        raw_score=round(raw_score, 2) if raw_score is not None else None,
        final_score=score,
        classification=classification,
        tiers={
            "candidate_min": effective_scoring.tiers.candidate_min,
            "strong_min": effective_scoring.tiers.strong_min,
            "excellent_min": effective_scoring.tiers.excellent_min,
        },
    )

    eff_hour_evals = hour_evaluations or []
    eff_raw_forecasts = raw_forecasts or []

    if eff_hour_evals:
        horizon_start = min(e.time for e in eff_hour_evals)
        horizon_end = max(e.time for e in eff_hour_evals)
    else:
        horizon_start = hours[0].time
        horizon_end = hours[-1].time

    report = EvaluationReport(
        profile_snapshot=profile.model_dump(mode="json"),
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        forecast_models=[s.model for s in eff_raw_forecasts] or contributing_models,
        hour_evaluations=eff_hour_evals,
        raw_forecasts=eff_raw_forecasts,
        scoring=scoring_trace,
        plugin_reports=plugin_reports,
    )

    window_hours = [
        WindowHour(
            time=hour.time,
            avg_wind_speed_kmh=hour.avg_wind_speed_kmh,
            avg_direction_deg=hour.avg_direction_deg,
            avg_precipitation_mm_per_hour=hour.avg_precipitation_mm_per_hour,
        )
        for hour in hours
    ]
    return CandidateWindow(
        alert_name=profile.name,
        start=hours[0].time,
        end=hours[-1].time + timedelta(hours=1),
        duration_hours=len(hours),
        avg_wind_speed_kmh=avg_speed,
        max_wind_speed_kmh=max_speed,
        avg_direction_deg=avg_direction,
        avg_precipitation_mm_per_hour=avg_precipitation,
        max_precipitation_mm_per_hour=max_precipitation,
        models=contributing_models,
        dry_filter_applied=False,
        score=score,
        classification=classification,
        subscores=subscores,
        hours=window_hours,
        plugin_outputs=plugin_outputs,
        report=report,
    )
