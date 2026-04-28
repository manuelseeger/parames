from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any
from zoneinfo import ZoneInfo

from parames.config import AlertProfileConfig, DryConfig, ModelAgreementConfig, TimeWindowConfig, WindConfig
from parames.domain import CandidateWindow, HourForecast, WindowHour
from parames.forecast import OpenMeteoForecastClient, ZURICH_TIMEZONE
from parames.plugins import EvaluationPlugin, build_plugins


@dataclass(frozen=True)
class EvaluatedHour:
    time: datetime
    avg_wind_speed_kmh: float
    max_wind_speed_kmh: float
    avg_direction_deg: float
    models: tuple[str, ...]
    avg_precipitation_mm_per_hour: float | None


def direction_in_range(direction: float, min_deg: float, max_deg: float) -> bool:
    direction = direction % 360
    min_deg = min_deg % 360
    max_deg = max_deg % 360
    if min_deg <= max_deg:
        return min_deg <= direction <= max_deg
    return direction >= min_deg or direction <= max_deg


def angular_distance(first: float, second: float) -> float:
    delta = abs((first - second) % 360)
    return min(delta, 360 - delta)


def vector_average_direction(directions: list[float]) -> float:
    if not directions:
        raise ValueError("directions must not be empty")
    sin_sum = sum(math.sin(math.radians(direction)) for direction in directions)
    cos_sum = sum(math.cos(math.radians(direction)) for direction in directions)
    average = math.degrees(math.atan2(sin_sum, cos_sum))
    return (average + 360) % 360


def evaluate_hour_candidate(
    hour: HourForecast,
    *,
    wind: WindConfig,
    time_window: TimeWindowConfig | None,
    dry: DryConfig | None,
) -> bool:
    if time_window is not None and not (time_window.start_hour <= hour.time.hour < time_window.end_hour):
        return False
    if hour.wind_speed is None or hour.wind_speed < wind.min_speed_kmh:
        return False
    if hour.wind_direction is None or not direction_in_range(
        hour.wind_direction, wind.direction_min_deg, wind.direction_max_deg
    ):
        return False
    return True


def evaluate(
    profile: AlertProfileConfig,
    *,
    client: OpenMeteoForecastClient | None = None,
    now: datetime | None = None,
) -> list[CandidateWindow]:
    if profile.forecast_hours is None or profile.wind_level_m is None or profile.model_agreement is None:
        raise ValueError("Alert profile must be resolved with defaults before evaluation")

    active_client = client or OpenMeteoForecastClient()
    should_close = client is None
    try:
        return _evaluate_with_client(profile, active_client, now=now)
    finally:
        if should_close:
            active_client.close()


def _evaluate_with_client(
    profile: AlertProfileConfig,
    client: OpenMeteoForecastClient,
    *,
    now: datetime | None,
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
        plugin.type: plugin.prefetch(client=client, models=profile.models) for plugin in plugins
    }

    timestamps = sorted({timestamp for forecasts in model_forecasts.values() for timestamp in forecasts})
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

    windows = build_candidate_windows(profile, accepted_hours, plugins=plugins, plugin_data=plugin_data)
    scored = [window for window in windows if window.score >= 3]
    _attach_context_hours(scored, model_forecasts)
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
        if evaluate_hour_candidate(hour, wind=profile.wind, time_window=profile.time_window, dry=profile.dry):
            matching[model] = hour

    agreement = profile.model_agreement
    assert agreement is not None
    if len(matching) < agreement.min_models_matching:
        return None
    if agreement.required and not models_agree(list(matching.values()), agreement):
        return None

    directions = [hour.wind_direction for hour in matching.values() if hour.wind_direction is not None]
    speeds = [hour.wind_speed for hour in matching.values() if hour.wind_speed is not None]
    precipitations = [hour.precipitation for hour in matching.values() if hour.precipitation is not None]
    if not directions or not speeds:
        return None
    return EvaluatedHour(
        time=timestamp,
        avg_wind_speed_kmh=sum(speeds) / len(speeds),
        max_wind_speed_kmh=max(speeds),
        avg_direction_deg=vector_average_direction(directions),
        models=tuple(sorted(matching)),
        avg_precipitation_mm_per_hour=(sum(precipitations) / len(precipitations)) if precipitations else None,
    )


def models_agree(hours: list[HourForecast], agreement: ModelAgreementConfig) -> bool:
    for left, right in combinations(hours, 2):
        if left.wind_direction is None or right.wind_direction is None:
            return False
        if left.wind_speed is None or right.wind_speed is None:
            return False
        if angular_distance(left.wind_direction, right.wind_direction) > agreement.max_direction_delta_deg:
            return False
        if abs(left.wind_speed - right.wind_speed) > agreement.max_speed_delta_kmh:
            return False
    return True


def build_candidate_windows(
    profile: AlertProfileConfig,
    accepted_hours: list[EvaluatedHour],
    *,
    plugins: list[EvaluationPlugin] | None = None,
    plugin_data: dict[str, Any] | None = None,
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

    return [
        score_window(profile, window, plugins=plugins or [], plugin_data=plugin_data or {})
        for window in windows
        if len(window) >= profile.wind.min_consecutive_hours
    ]


def score_window(
    profile: AlertProfileConfig,
    hours: list[EvaluatedHour],
    *,
    plugins: list[EvaluationPlugin] | None = None,
    plugin_data: dict[str, Any] | None = None,
) -> CandidateWindow:
    plugins = plugins or []
    plugin_data = plugin_data or {}

    avg_speed = sum(hour.avg_wind_speed_kmh for hour in hours) / len(hours)
    max_speed = max(hour.max_wind_speed_kmh for hour in hours)
    avg_direction = vector_average_direction([hour.avg_direction_deg for hour in hours])
    precipitation_values = [hour.avg_precipitation_mm_per_hour for hour in hours if hour.avg_precipitation_mm_per_hour is not None]
    avg_precipitation = (
        sum(precipitation_values) / len(precipitation_values) if len(precipitation_values) == len(hours) else None
    )
    max_precipitation = max(precipitation_values) if precipitation_values else None

    score = 0
    if avg_speed >= profile.wind.strong_speed_kmh:
        score += 2
    elif avg_speed >= profile.wind.min_speed_kmh:
        score += 1

    if len(hours) >= 4:
        score += 2
    elif len(hours) >= profile.wind.min_consecutive_hours:
        score += 1

    contributing_models = sorted({model for hour in hours for model in hour.models})
    plugin_outputs: dict[str, dict[str, Any]] = {}
    for plugin in plugins:
        boost, output = plugin.score_window(
            window_times=[hour.time for hour in hours],
            prefetched=plugin_data.get(plugin.type),
            contributing_models=contributing_models,
        )
        score += boost
        if output:
            plugin_outputs[plugin.type] = output

    if score >= 5:
        classification = "strong"
    elif score >= 3:
        classification = "candidate"
    else:
        classification = "weak"

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
        hours=window_hours,
        plugin_outputs=plugin_outputs,
    )


def _avg_hour_from_forecasts(
    timestamp: datetime,
    model_forecasts: dict[str, dict[datetime, HourForecast]],
) -> tuple[float, float, float | None] | None:
    """Return averages for a timestamp across models, or None when wind data is unavailable."""
    speeds: list[float] = []
    directions: list[float] = []
    precipitations: list[float] = []
    for forecasts in model_forecasts.values():
        hour = forecasts.get(timestamp)
        if hour is None:
            continue
        if hour.wind_speed is not None and hour.wind_direction is not None:
            speeds.append(hour.wind_speed)
            directions.append(hour.wind_direction)
        if hour.precipitation is not None:
            precipitations.append(hour.precipitation)
    if not speeds:
        return None
    avg_precipitation = sum(precipitations) / len(precipitations) if precipitations else None
    return sum(speeds) / len(speeds), vector_average_direction(directions), avg_precipitation


def _attach_context_hours(
    windows: list[CandidateWindow],
    model_forecasts: dict[str, dict[datetime, HourForecast]],
    context_n: int = 2,
) -> None:
    """Prepend and append context hours (outside the alert window) to each window's hours list."""
    for window in windows:
        pre_times = [window.start - timedelta(hours=i) for i in range(context_n, 0, -1)]
        post_times = [window.end + timedelta(hours=i) for i in range(context_n)]

        context_before = []
        for t in pre_times:
            result = _avg_hour_from_forecasts(t, model_forecasts)
            if result is not None:
                context_before.append(
                    WindowHour(
                        time=t,
                        avg_wind_speed_kmh=result[0],
                        avg_direction_deg=result[1],
                        avg_precipitation_mm_per_hour=result[2],
                        in_window=False,
                    )
                )

        context_after = []
        for t in post_times:
            result = _avg_hour_from_forecasts(t, model_forecasts)
            if result is not None:
                context_after.append(
                    WindowHour(
                        time=t,
                        avg_wind_speed_kmh=result[0],
                        avg_direction_deg=result[1],
                        avg_precipitation_mm_per_hour=result[2],
                        in_window=False,
                    )
                )

        window.hours = context_before + window.hours + context_after
