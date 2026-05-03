from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from parames.domain import HourForecast, WindowHour
from parames.evaluation.direction import vector_average_direction


@dataclass(frozen=True)
class EvaluatedHour:
    time: datetime
    avg_wind_speed_kmh: float
    max_wind_speed_kmh: float
    avg_direction_deg: float
    models: tuple[str, ...]
    avg_precipitation_mm_per_hour: float | None


def _avg_hour_from_forecasts(
    timestamp: datetime,
    model_forecasts: dict[str, dict[datetime, HourForecast]],
) -> tuple[float, float, float | None] | None:
    """Return (avg_speed, avg_direction, avg_precip) across models, or None if wind data is unavailable."""
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
    avg_precipitation = (
        sum(precipitations) / len(precipitations) if precipitations else None
    )
    return (
        sum(speeds) / len(speeds),
        vector_average_direction(directions),
        avg_precipitation,
    )


def attach_context_hours(
    windows: list,
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
