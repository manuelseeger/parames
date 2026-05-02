from __future__ import annotations

from itertools import combinations

from parames.config import DryConfig, TimeWindowConfig, WindConfig
from parames.domain import HourForecast
from parames.evaluation.direction import angular_distance, direction_in_range

from parames.config import ModelAgreementConfig


def evaluate_hour_candidate(
    hour: HourForecast,
    *,
    wind: WindConfig,
    time_window: TimeWindowConfig | None,
    dry: DryConfig | None,
) -> bool:
    if time_window is not None and not (
        time_window.start_hour <= hour.time.hour < time_window.end_hour
    ):
        return False
    if hour.wind_speed is None or hour.wind_speed < wind.min_speed_kmh:
        return False
    if hour.wind_direction is None or not direction_in_range(
        hour.wind_direction, wind.direction_min_deg, wind.direction_max_deg
    ):
        return False
    return True


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


def subscore_wind_speed(avg_speed_kmh: float, wind: WindConfig) -> float:
    """Tent: 0 at min and strong, peaks 100 at midpoint."""
    lo = wind.min_speed_kmh
    hi = wind.strong_speed_kmh
    if lo is None or hi is None or avg_speed_kmh <= lo or avg_speed_kmh >= hi:
        return 0.0
    peak = (lo + hi) / 2.0
    if avg_speed_kmh <= peak:
        return (avg_speed_kmh - lo) / (peak - lo) * 100.0
    return (hi - avg_speed_kmh) / (hi - peak) * 100.0


def subscore_wind_duration(duration_hours: int, wind: WindConfig) -> float:
    """0 below min_consecutive, 50 at min_consecutive, linear to 100 at 4h+."""
    if duration_hours < wind.min_consecutive_hours:
        return 0.0
    if duration_hours >= 4:
        return 100.0
    if wind.min_consecutive_hours >= 4:
        return 100.0
    span = 4 - wind.min_consecutive_hours
    extra = duration_hours - wind.min_consecutive_hours
    return 50.0 + (extra / span) * 50.0
