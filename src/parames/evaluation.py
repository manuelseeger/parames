from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

from parames.config import AlertProfileConfig, DryConfig, ModelAgreementConfig, TimeWindowConfig, WindConfig
from parames.domain import CandidateWindow, HourForecast
from parames.forecast import OpenMeteoForecastClient, ZURICH_TIMEZONE


@dataclass(frozen=True)
class EvaluatedHour:
    time: datetime
    avg_wind_speed_kmh: float
    max_wind_speed_kmh: float
    avg_direction_deg: float
    models: tuple[str, ...]
    precipitation_ok: bool
    bise_gradient_hpa: float | None


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
    if dry is not None and dry.enabled:
        if hour.precipitation is None:
            return False
        if hour.precipitation > dry.max_precipitation_mm_per_hour:
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
    west_pressures: dict[str, dict[datetime, HourForecast]] = {}
    east_pressures: dict[str, dict[datetime, HourForecast]] = {}

    for model in profile.models:
        model_forecasts[model] = client.fetch_hourly_forecast(
            location=profile.location,
            model=model,
            hourly_variables=hourly_variables,
        )
        if profile.bise and profile.bise.enabled:
            west_pressures[model] = client.fetch_hourly_forecast(
                location=profile.bise.pressure_reference_west,
                model=model,
                hourly_variables=["pressure_msl"],
            )
            east_pressures[model] = client.fetch_hourly_forecast(
                location=profile.bise.pressure_reference_east,
                model=model,
                hourly_variables=["pressure_msl"],
            )

    timestamps = sorted({timestamp for forecasts in model_forecasts.values() for timestamp in forecasts})
    accepted_hours: list[EvaluatedHour] = []
    for timestamp in timestamps:
        if timestamp < current_time or timestamp > horizon_end:
            continue
        evaluated = _evaluate_timestamp(
            timestamp=timestamp,
            profile=profile,
            model_forecasts=model_forecasts,
            west_pressures=west_pressures,
            east_pressures=east_pressures,
        )
        if evaluated is not None:
            accepted_hours.append(evaluated)

    windows = build_candidate_windows(profile, accepted_hours)
    return [window for window in windows if window.score >= 3]


def _evaluate_timestamp(
    *,
    timestamp: datetime,
    profile: AlertProfileConfig,
    model_forecasts: dict[str, dict[datetime, HourForecast]],
    west_pressures: dict[str, dict[datetime, HourForecast]],
    east_pressures: dict[str, dict[datetime, HourForecast]],
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

    gradients = compute_bise_gradients(
        timestamp=timestamp,
        profile=profile,
        models=tuple(matching),
        west_pressures=west_pressures,
        east_pressures=east_pressures,
    )
    precipitation_ok = not (profile.dry and profile.dry.enabled) or all(
        hour.precipitation is not None and hour.precipitation <= profile.dry.max_precipitation_mm_per_hour
        for hour in matching.values()
    )
    directions = [hour.wind_direction for hour in matching.values() if hour.wind_direction is not None]
    speeds = [hour.wind_speed for hour in matching.values() if hour.wind_speed is not None]
    if not directions or not speeds:
        return None
    gradient_average = sum(gradients.values()) / len(gradients) if gradients else None
    return EvaluatedHour(
        time=timestamp,
        avg_wind_speed_kmh=sum(speeds) / len(speeds),
        max_wind_speed_kmh=max(speeds),
        avg_direction_deg=vector_average_direction(directions),
        models=tuple(sorted(matching)),
        precipitation_ok=precipitation_ok,
        bise_gradient_hpa=gradient_average,
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


def compute_bise_gradients(
    *,
    timestamp: datetime,
    profile: AlertProfileConfig,
    models: tuple[str, ...],
    west_pressures: dict[str, dict[datetime, HourForecast]],
    east_pressures: dict[str, dict[datetime, HourForecast]],
) -> dict[str, float]:
    if not profile.bise or not profile.bise.enabled:
        return {}
    gradients: dict[str, float] = {}
    for model in models:
        west = west_pressures.get(model, {}).get(timestamp)
        east = east_pressures.get(model, {}).get(timestamp)
        if west is None or east is None:
            return {}
        if west.pressure_msl is None or east.pressure_msl is None:
            return {}
        gradients[model] = east.pressure_msl - west.pressure_msl
    return gradients


def build_candidate_windows(
    profile: AlertProfileConfig, accepted_hours: list[EvaluatedHour]
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
        score_window(profile, window)
        for window in windows
        if len(window) >= profile.wind.min_consecutive_hours
    ]


def score_window(profile: AlertProfileConfig, hours: list[EvaluatedHour]) -> CandidateWindow:
    avg_speed = sum(hour.avg_wind_speed_kmh for hour in hours) / len(hours)
    max_speed = max(hour.max_wind_speed_kmh for hour in hours)
    avg_direction = vector_average_direction([hour.avg_direction_deg for hour in hours])
    gradient_values = [hour.bise_gradient_hpa for hour in hours if hour.bise_gradient_hpa is not None]
    gradient = sum(gradient_values) / len(gradient_values) if len(gradient_values) == len(hours) else None

    score = 0
    if avg_speed >= profile.wind.strong_speed_kmh:
        score += 2
    elif avg_speed >= profile.wind.min_speed_kmh:
        score += 1

    if len(hours) >= 4:
        score += 2
    elif len(hours) >= profile.wind.min_consecutive_hours:
        score += 1

    if profile.bise and profile.bise.enabled and profile.bise.boost_if_bise and gradient is not None:
        if gradient >= 3.0:
            score += 2
        elif gradient >= profile.bise.east_minus_west_pressure_hpa_min:
            score += 1

    if profile.dry and profile.dry.enabled and all(hour.precipitation_ok for hour in hours):
        score += 1

    if score >= 5:
        classification = "strong"
    elif score >= 3:
        classification = "candidate"
    else:
        classification = "weak"

    models = sorted({model for hour in hours for model in hour.models})
    return CandidateWindow(
        alert_name=profile.name,
        start=hours[0].time,
        end=hours[-1].time + timedelta(hours=1),
        duration_hours=len(hours),
        avg_wind_speed_kmh=avg_speed,
        max_wind_speed_kmh=max_speed,
        avg_direction_deg=avg_direction,
        bise_pressure_gradient_hpa=gradient,
        models=models,
        dry_filter_applied=bool(profile.dry and profile.dry.enabled),
        score=score,
        classification=classification,
    )
