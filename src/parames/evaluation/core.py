from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from parames.config import AlertProfileConfig, ScoringConfig
from parames.domain import CandidateWindow, HourEvaluation, HourForecast, ModelForecastSeries, ModelHourForecast
from parames.evaluation.scoring import build_candidate_windows
from parames.evaluation.wind import evaluate_hour_reasons, models_agree
from parames.evaluation.windows import EvaluatedHour, attach_context_hours
from parames.evaluation.direction import vector_average_direction
from parames.forecast import ForecastClient, OpenMeteoForecastClient, ZURICH_TIMEZONE
from parames.plugins import build_plugins


def evaluate(
    profile: AlertProfileConfig,
    *,
    client: ForecastClient | None = None,
    now: datetime | None = None,
    scoring: ScoringConfig | None = None,
) -> list[CandidateWindow]:
    if (
        profile.forecast_hours is None
        or profile.wind_level_m is None
        or profile.model_agreement is None
        or profile.wind.min_speed_kmh is None
        or profile.wind.strong_speed_kmh is None
    ):
        raise ValueError(
            "Alert profile must be resolved with defaults before evaluation"
        )

    active_client = client or OpenMeteoForecastClient()
    should_close = client is None
    effective_scoring = scoring if scoring is not None else ScoringConfig()
    try:
        return _evaluate_with_client(
            profile, active_client, now=now, scoring=effective_scoring
        )
    finally:
        if should_close:
            active_client.close()


def _evaluate_with_client(
    profile: AlertProfileConfig,
    client: ForecastClient,
    *,
    now: datetime | None,
    scoring: ScoringConfig,
) -> list[CandidateWindow]:
    timezone = ZoneInfo(ZURICH_TIMEZONE)
    current_time = now.astimezone(timezone) if now else datetime.now(timezone)
    horizon_end = current_time + timedelta(hours=profile.forecast_hours)

    hourly_variables = [
        f"wind_speed_{profile.wind_level_m}m",
        f"wind_direction_{profile.wind_level_m}m",
        "precipitation",
        "pressure_msl",
    ]
    model_forecasts: dict[str, dict[datetime, HourForecast]] = {}
    for model in profile.models:
        model_forecasts[model] = client.fetch_hourly_forecast(
            location=profile.location,
            model=model,
            hourly_variables=hourly_variables,
        )

    plugins = [p for p in build_plugins(profile.plugins) if p.enabled]
    plugin_data: dict[str, Any] = {
        plugin.type: plugin.prefetch(client=client, models=profile.models, location=profile.location)
        for plugin in plugins
    }

    timestamps = sorted(
        {timestamp for forecasts in model_forecasts.values() for timestamp in forecasts}
    )

    all_hour_evaluations: list[HourEvaluation] = []
    accepted_hours: list[EvaluatedHour] = []

    for timestamp in timestamps:
        if timestamp < current_time or timestamp > horizon_end:
            all_hour_evaluations.append(HourEvaluation(
                time=timestamp,
                accepted=False,
                matching_models=[],
                rejection_reasons=["out_of_horizon"],
            ))
            continue
        evaluated, hour_eval = _evaluate_timestamp(
            timestamp=timestamp,
            profile=profile,
            model_forecasts=model_forecasts,
        )
        all_hour_evaluations.append(hour_eval)
        if evaluated is not None:
            accepted_hours.append(evaluated)

    # Snapshot raw forecasts (full prefetch horizon, all models)
    raw_forecasts: list[ModelForecastSeries] = [
        ModelForecastSeries(
            model=model,
            hours=[
                ModelHourForecast(
                    time=ts,
                    wind_speed=_r(h.wind_speed, 2),
                    wind_direction=_r(h.wind_direction, 1),
                    wind_gusts=_r(h.wind_gusts, 2),
                    precipitation=_r(h.precipitation, 3),
                    pressure_msl=_r(h.pressure_msl, 2),
                    cape=_r(h.cape, 1),
                    showers=_r(h.showers, 3),
                )
                for ts, h in sorted(by_time.items())
            ],
        )
        for model, by_time in model_forecasts.items()
    ]

    windows = build_candidate_windows(
        profile,
        accepted_hours,
        plugins=plugins,
        plugin_data=plugin_data,
        scoring=scoring,
        hour_evaluations=all_hour_evaluations,
        raw_forecasts=raw_forecasts,
    )
    scored = [
        window
        for window in windows
        if window.score is not None and window.score >= scoring.emit_threshold
    ]
    attach_context_hours(scored, model_forecasts)
    return scored


def _r(value: float | None, dp: int) -> float | None:
    """Round a float to dp decimal places, or return None."""
    return round(value, dp) if value is not None else None


def _evaluate_timestamp(
    *,
    timestamp: datetime,
    profile: AlertProfileConfig,
    model_forecasts: dict[str, dict[datetime, HourForecast]],
) -> tuple[EvaluatedHour | None, HourEvaluation]:
    matching: dict[str, HourForecast] = {}

    for model, forecast_by_time in model_forecasts.items():
        hour = forecast_by_time.get(timestamp)
        if hour is None:
            continue
        passed, _ = evaluate_hour_reasons(
            hour, wind=profile.wind, time_window=profile.time_window, dry=profile.dry
        )
        if passed:
            matching[model] = hour

    agreement = profile.model_agreement
    assert agreement is not None
    matching_model_list = sorted(matching.keys())

    if len(matching) < agreement.min_models_matching:
        return None, HourEvaluation(
            time=timestamp,
            accepted=False,
            matching_models=matching_model_list,
            rejection_reasons=["min_models_matching_not_met"],
        )

    if agreement.required and not models_agree(list(matching.values()), agreement):
        return None, HourEvaluation(
            time=timestamp,
            accepted=False,
            matching_models=matching_model_list,
            rejection_reasons=["model_agreement_failed"],
        )

    directions = [
        hour.wind_direction
        for hour in matching.values()
        if hour.wind_direction is not None
    ]
    speeds = [
        hour.wind_speed for hour in matching.values() if hour.wind_speed is not None
    ]
    precipitations = [
        hour.precipitation
        for hour in matching.values()
        if hour.precipitation is not None
    ]
    if not directions or not speeds:
        return None, HourEvaluation(
            time=timestamp,
            accepted=False,
            matching_models=matching_model_list,
            rejection_reasons=["missing_wind_data"],
        )

    evaluated = EvaluatedHour(
        time=timestamp,
        avg_wind_speed_kmh=sum(speeds) / len(speeds),
        max_wind_speed_kmh=max(speeds),
        avg_direction_deg=vector_average_direction(directions),
        models=tuple(sorted(matching)),
        avg_precipitation_mm_per_hour=(sum(precipitations) / len(precipitations))
        if precipitations
        else None,
    )

    return evaluated, HourEvaluation(
        time=timestamp,
        accepted=True,
        matching_models=matching_model_list,
        rejection_reasons=[],
    )
