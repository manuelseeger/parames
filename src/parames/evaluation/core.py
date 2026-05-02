from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from parames.config import AlertProfileConfig, ScoringConfig
from parames.domain import CandidateWindow, HourForecast
from parames.evaluation.scoring import build_candidate_windows
from parames.evaluation.wind import evaluate_hour_candidate, models_agree
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
    accepted_hours: list[EvaluatedHour] = []
    for timestamp in timestamps:
        if timestamp < current_time or timestamp > horizon_end:
            continue
        evaluated = _evaluate_timestamp(
            timestamp=timestamp,
            profile=profile,
            model_forecasts=model_forecasts,
        )
        if evaluated is not None:
            accepted_hours.append(evaluated)

    windows = build_candidate_windows(
        profile,
        accepted_hours,
        plugins=plugins,
        plugin_data=plugin_data,
        scoring=scoring,
    )
    scored = [
        window
        for window in windows
        if window.score is not None and window.score >= scoring.emit_threshold
    ]
    attach_context_hours(scored, model_forecasts)
    return scored


def _evaluate_timestamp(
    *,
    timestamp: datetime,
    profile: AlertProfileConfig,
    model_forecasts: dict[str, dict[datetime, HourForecast]],
) -> EvaluatedHour | None:
    matching: dict[str, HourForecast] = {}
    for model, forecast_by_time in model_forecasts.items():
        hour = forecast_by_time.get(timestamp)
        if hour is None:
            continue
        if evaluate_hour_candidate(
            hour, wind=profile.wind, time_window=profile.time_window, dry=profile.dry
        ):
            matching[model] = hour

    agreement = profile.model_agreement
    assert agreement is not None
    if len(matching) < agreement.min_models_matching:
        return None
    if agreement.required and not models_agree(list(matching.values()), agreement):
        return None

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
        return None
    return EvaluatedHour(
        time=timestamp,
        avg_wind_speed_kmh=sum(speeds) / len(speeds),
        max_wind_speed_kmh=max(speeds),
        avg_direction_deg=vector_average_direction(directions),
        models=tuple(sorted(matching)),
        avg_precipitation_mm_per_hour=(sum(precipitations) / len(precipitations))
        if precipitations
        else None,
    )
