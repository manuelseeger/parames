from __future__ import annotations

import math
from itertools import combinations

from parames.config import DryConfig, TimeWindowConfig, WindConfig
from parames.domain import HourForecast
from parames.evaluation.direction import angular_distance, direction_in_range

from parames.config import ModelAgreementConfig


def evaluate_hour_reasons(
    hour: HourForecast,
    *,
    wind: WindConfig,
    time_window: TimeWindowConfig | None,
    dry: DryConfig | None,  # noqa: ARG001
) -> tuple[bool, list[str]]:
    """Return (passed, rejection_reasons) for per-model hour gating."""
    reasons: list[str] = []
    if time_window is not None and not (
        time_window.start_hour <= hour.time.hour < time_window.end_hour
    ):
        reasons.append("out_of_time_window")
    if hour.wind_speed is None or hour.wind_speed < wind.min_speed_kmh:
        reasons.append("wind_below_min")
    elif hour.wind_direction is None or not direction_in_range(
        hour.wind_direction, wind.direction_min_deg, wind.direction_max_deg
    ):
        reasons.append("wind_direction_out_of_range")
    return not bool(reasons), reasons


def evaluate_hour_candidate(
    hour: HourForecast,
    *,
    wind: WindConfig,
    time_window: TimeWindowConfig | None,
    dry: DryConfig | None,
) -> bool:
    passed, _ = evaluate_hour_reasons(hour, wind=wind, time_window=time_window, dry=dry)
    return passed


def models_agree(hours: list[HourForecast], agreement: ModelAgreementConfig) -> bool:
    for left, right in combinations(hours, 2):
        if left.wind_direction is None or right.wind_direction is None:
            return False
        if left.wind_speed is None or right.wind_speed is None:
            return False
        if (
            angular_distance(left.wind_direction, right.wind_direction)
            > agreement.max_direction_delta_deg
        ):
            return False
        if abs(left.wind_speed - right.wind_speed) > agreement.max_speed_delta_kmh:
            return False
    return True


def subscore_wind_speed(hourly_speeds: list[float], wind: WindConfig) -> float:
    """Gaussian bell centered at sweet_spot_kmh, scored per hour then averaged."""
    mu = wind.sweet_spot_kmh
    sigma = wind.sweet_spot_sigma_kmh
    if not hourly_speeds or mu is None or sigma is None:
        return 0.0
    scores = [math.exp(-0.5 * ((s - mu) / sigma) ** 2) * 100.0 for s in hourly_speeds]
    return sum(scores) / len(scores)


