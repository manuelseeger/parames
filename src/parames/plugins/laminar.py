from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal

from pydantic import Field
from pyodmongo import MainBaseModel

from parames.common import LocationConfig
from parames.domain import HourForecast
from parames.forecast import ForecastClient
from parames.plugins.base import PluginConfigBase, register_plugin


class GustFactorThresholds(MainBaseModel):
    good_max: float = 1.35
    marginal_max: float = 1.60


class GustSpreadThresholds(MainBaseModel):
    good_max: float = 6.0
    marginal_max: float = 10.0


class DirectionVariabilityThresholds(MainBaseModel):
    good_max: float = 20.0
    marginal_max: float = 40.0


class SpeedRangeThresholds(MainBaseModel):
    good_max: float = 4.0
    marginal_max: float = 7.0


class CapeThresholds(MainBaseModel):
    good_max: float = 50.0
    marginal_max: float = 200.0


class LaminarModelAgreement(MainBaseModel):
    direction_good_max_deg: float = 25.0
    direction_marginal_max_deg: float = 40.0
    speed_good_max_kmh: float = 5.0
    speed_marginal_max_kmh: float = 8.0


class PressureTendencyThresholds(MainBaseModel):
    good_max_abs: float = 1.5
    marginal_max_abs: float = 2.5


class PrecipThresholds(MainBaseModel):
    max_precip_mm_h: float = 0.0
    max_showers_mm_h: float = 0.0


class LaminarPluginConfig(PluginConfigBase):
    type: Literal["laminar"] = "laminar"
    primary_model: str | None = None
    secondary_model: str | None = None
    # Must match the alert profile's wind_level_m so gust variable names align.
    wind_level_m: int = 10
    gust_factor: GustFactorThresholds = Field(default_factory=GustFactorThresholds)
    gust_spread_kmh: GustSpreadThresholds = Field(default_factory=GustSpreadThresholds)
    direction_variability_deg: DirectionVariabilityThresholds = Field(
        default_factory=DirectionVariabilityThresholds
    )
    speed_range_kmh: SpeedRangeThresholds = Field(default_factory=SpeedRangeThresholds)
    cape_j_kg: CapeThresholds = Field(default_factory=CapeThresholds)
    model_agreement: LaminarModelAgreement = Field(
        default_factory=LaminarModelAgreement
    )
    pressure_tendency_3h_hpa: PressureTendencyThresholds = Field(
        default_factory=PressureTendencyThresholds
    )
    precipitation: PrecipThresholds = Field(default_factory=PrecipThresholds)


class LaminarPrefetched:
    __slots__ = ("data",)

    def __init__(self, data: dict[str, dict[datetime, HourForecast]]) -> None:
        self.data = data


def _percentile_75(values: list[float]) -> float:
    """75th percentile via linear interpolation over sorted values."""
    n = len(values)
    if n == 0:
        return 0.0
    if n == 1:
        return values[0]
    sorted_vals = sorted(values)
    rank = 0.75 * (n - 1)
    low = int(rank)
    high = min(low + 1, n - 1)
    frac = rank - low
    return sorted_vals[low] + frac * (sorted_vals[high] - sorted_vals[low])


def _score_to_label(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "marginal"
    return "poor"


@register_plugin
class LaminarPlugin:
    """Laminar wind quality signal.

    Scores how stable, smooth, and non-convective the wind forecast is for an
    already-accepted window. A 0–100 sub-score participates in the weighted-mean
    composite; poor quality drags the composite down proportionally.
    Returns None only when required wind/gust data is entirely missing.
    """

    type: ClassVar[str] = "laminar"

    def __init__(self, config: LaminarPluginConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def prefetch(
        self,
        *,
        client: ForecastClient,
        models: list[str],
        location: LocationConfig,
    ) -> LaminarPrefetched:
        level = self.config.wind_level_m
        hourly_variables = [
            f"wind_speed_{level}m",
            f"wind_direction_{level}m",
            f"wind_gusts_{level}m",
            "precipitation",
            "showers",
            "cape",
            "pressure_msl",
        ]
        data: dict[str, dict[datetime, HourForecast]] = {}
        for model in models:
            data[model] = client.fetch_hourly_forecast(
                location=location,
                model=model,
                hourly_variables=hourly_variables,
            )
        return LaminarPrefetched(data=data)

    def score_window(
        self,
        *,
        window_times: list[datetime],
        prefetched: LaminarPrefetched,
        contributing_models: list[str],
    ) -> tuple[float | None, dict[str, Any]]:
        # Local import avoids circular dependency (evaluation.py imports parames.plugins).
        from parames.evaluation import angular_distance, vector_average_direction

        cfg = self.config
        reasons: list[str] = []

        # 1. Resolve primary model
        if cfg.primary_model and cfg.primary_model in contributing_models:
            primary = cfg.primary_model
        elif cfg.primary_model and cfg.primary_model not in contributing_models:
            primary = contributing_models[0]
            reasons.append("primary_model_substituted")
        else:
            primary = contributing_models[0]

        # 2. Resolve secondary model
        secondary: str | None = None
        if cfg.secondary_model and cfg.secondary_model in prefetched.data:
            secondary = cfg.secondary_model
        else:
            for candidate in contributing_models[1:]:
                if candidate in prefetched.data:
                    secondary = candidate
                    break

        # 3. Required-data gate (wind_speed, wind_direction, wind_gusts must be present
        #    for every hour in the window from the primary model)
        primary_hours = prefetched.data.get(primary, {})
        for ts in window_times:
            h = primary_hours.get(ts)
            if (
                h is None
                or h.wind_speed is None
                or h.wind_direction is None
                or h.wind_gusts is None
            ):
                return (
                    None,
                    {
                        "score": None,
                        "label": "unavailable",
                        "reasons": ["missing_required_wind_data"],
                    },
                )

        window_hours = [primary_hours[ts] for ts in window_times]
        score = 100.0

        # 4a. Gust factor and gust spread
        gust_factors = [
            h.wind_gusts / max(h.wind_speed, 1.0)  # type: ignore[operator]
            for h in window_hours
        ]
        gust_spreads = [
            h.wind_gusts - h.wind_speed  # type: ignore[operator]
            for h in window_hours
        ]
        avg_gust_factor = sum(gust_factors) / len(gust_factors)
        max_gust_factor = max(gust_factors)
        avg_gust_spread_kmh = sum(gust_spreads) / len(gust_spreads)
        max_gust_spread_kmh = max(gust_spreads)

        if max_gust_factor > cfg.gust_factor.marginal_max:
            score -= 35
            reasons.append("very_gusty")
        elif max_gust_factor > cfg.gust_factor.good_max:
            score -= 15
            reasons.append("high_gust_factor")
        else:
            reasons.append("low_gust_factor")

        if max_gust_spread_kmh > cfg.gust_spread_kmh.marginal_max:
            score -= 25
        elif max_gust_spread_kmh > cfg.gust_spread_kmh.good_max:
            score -= 10

        # 4b. Direction stability
        directions: list[float] = [h.wind_direction for h in window_hours]  # type: ignore[misc]
        mean_dir = vector_average_direction(directions)
        direction_variability_deg = max(
            angular_distance(d, mean_dir) for d in directions
        )

        if direction_variability_deg > cfg.direction_variability_deg.marginal_max:
            score -= 25
            reasons.append("very_shifty")
        elif direction_variability_deg > cfg.direction_variability_deg.good_max:
            score -= 10
            reasons.append("shifting_direction")
        else:
            reasons.append("stable_direction")

        # 4c. Speed stability
        speeds: list[float] = [h.wind_speed for h in window_hours]  # type: ignore[misc]
        gusts: list[float] = [h.wind_gusts for h in window_hours]  # type: ignore[misc]
        speed_range_kmh = max(speeds) - min(speeds)
        gust_range_kmh = max(gusts) - min(gusts)

        if speed_range_kmh > cfg.speed_range_kmh.marginal_max:
            score -= 20
            reasons.append("high_speed_range")
        elif speed_range_kmh > cfg.speed_range_kmh.good_max:
            score -= 8
            reasons.append("high_speed_range")
        else:
            reasons.append("low_speed_range")

        # 4d. Convective risk (CAPE)
        cape_values = [h.cape for h in window_hours if h.cape is not None]
        cape_available = len(cape_values) > len(window_hours) / 2
        max_cape: float | None = None
        avg_cape: float | None = None
        if not cape_available:
            reasons.append("cape_unavailable")
        else:
            max_cape = max(cape_values)
            avg_cape = sum(cape_values) / len(cape_values)
            if max_cape > cfg.cape_j_kg.marginal_max:
                score -= 25
                reasons.append("high_cape")
            elif max_cape > cfg.cape_j_kg.good_max:
                score -= 10
                reasons.append("moderate_cape")
            else:
                reasons.append("low_cape")

        # 4e. Precipitation / shower risk
        max_precipitation = max((h.precipitation or 0.0) for h in window_hours)
        max_showers = max((h.showers or 0.0) for h in window_hours)
        if max_precipitation > cfg.precipitation.max_precip_mm_h:
            score -= 30
            reasons.append("precipitation_risk")
        elif max_showers > cfg.precipitation.max_showers_mm_h:
            score -= 30
            reasons.append("showers_risk")

        # 4f. Pressure tendency (3h window starting at window_start)
        pressure_tendency_3h_hpa: float | None = None
        pressure_available = any(
            primary_hours.get(ts) is not None
            and primary_hours[ts].pressure_msl is not None
            for ts in window_times
        )
        if not pressure_available:
            reasons.append("pressure_unavailable")
        else:
            window_start = window_times[0]
            target_time = window_start + timedelta(hours=3)
            p_start = primary_hours.get(window_start)
            p_target = primary_hours.get(target_time)
            p_start_val = p_start.pressure_msl if p_start else None
            p_target_val = p_target.pressure_msl if p_target else None

            if p_start_val is not None and p_target_val is not None:
                pressure_tendency_3h_hpa = p_target_val - p_start_val
            else:
                # Fallback: scale first→last available pressure in the full
                # prefetched horizon to estimate a 3h tendency.
                p_series = [
                    (ts, h.pressure_msl)
                    for ts, h in primary_hours.items()
                    if h.pressure_msl is not None
                ]
                if len(p_series) >= 2:
                    p_series.sort()
                    p_first_ts, p_first = p_series[0]
                    p_last_ts, p_last = p_series[-1]
                    duration_h = (p_last_ts - p_first_ts).total_seconds() / 3600
                    if duration_h > 0 and p_first is not None and p_last is not None:
                        pressure_tendency_3h_hpa = (p_last - p_first) * (
                            3.0 / duration_h
                        )

            if pressure_tendency_3h_hpa is not None:
                abs_tendency = abs(pressure_tendency_3h_hpa)
                if abs_tendency > cfg.pressure_tendency_3h_hpa.marginal_max_abs:
                    score -= 15
                    reasons.append("pressure_unstable")
                elif abs_tendency > cfg.pressure_tendency_3h_hpa.good_max_abs:
                    score -= 5
                    reasons.append("pressure_unstable")
                else:
                    reasons.append("pressure_stable")

        # 4g. Model agreement (primary vs secondary)
        model_dir_delta_deg: float | None = None
        model_speed_delta_kmh: float | None = None
        if secondary is None:
            score -= 10
            reasons.append("secondary_model_unavailable")
        else:
            secondary_hours = prefetched.data.get(secondary, {})
            dir_deltas: list[float] = []
            speed_deltas: list[float] = []
            for ts in window_times:
                ph = primary_hours.get(ts)
                sh = secondary_hours.get(ts)
                if (
                    ph is None
                    or sh is None
                    or ph.wind_direction is None
                    or sh.wind_direction is None
                    or ph.wind_speed is None
                    or sh.wind_speed is None
                ):
                    continue
                dir_deltas.append(
                    angular_distance(ph.wind_direction, sh.wind_direction)
                )
                speed_deltas.append(abs(ph.wind_speed - sh.wind_speed))

            if dir_deltas and speed_deltas:
                use_percentile = len(window_times) >= 4
                if use_percentile:
                    dir_stat = _percentile_75(dir_deltas)
                    speed_stat = _percentile_75(speed_deltas)
                else:
                    dir_stat = max(dir_deltas)
                    speed_stat = max(speed_deltas)
                model_dir_delta_deg = dir_stat
                model_speed_delta_kmh = speed_stat

                ma = cfg.model_agreement
                if (
                    dir_stat <= ma.direction_good_max_deg
                    and speed_stat <= ma.speed_good_max_kmh
                ):
                    reasons.append("model_agreement_good")
                elif (
                    dir_stat <= ma.direction_marginal_max_deg
                    and speed_stat <= ma.speed_marginal_max_kmh
                ):
                    score -= 10
                    reasons.append("model_disagreement")
                else:
                    score -= 25
                    reasons.append("model_disagreement")
            else:
                # No overlapping data between models — treat as unavailable
                score -= 10
                reasons.append("secondary_model_unavailable")

        # Clamp and build result
        score = max(0.0, min(100.0, score))
        label = _score_to_label(score)

        metrics: dict[str, Any] = {
            "avg_gust_factor": round(avg_gust_factor, 3),
            "max_gust_spread_kmh": round(max_gust_spread_kmh, 2),
            "direction_variability_deg": round(direction_variability_deg, 1),
            "speed_range_kmh": round(speed_range_kmh, 2),
            "pressure_tendency_3h_hpa": (
                round(pressure_tendency_3h_hpa, 2)
                if pressure_tendency_3h_hpa is not None
                else None
            ),
        }
        if max_cape is not None:
            metrics["max_cape"] = round(max_cape, 1)
        if model_dir_delta_deg is not None:
            metrics["model_direction_delta_deg"] = round(model_dir_delta_deg, 1)
        if model_speed_delta_kmh is not None:
            metrics["model_speed_delta_kmh"] = round(model_speed_delta_kmh, 2)

        output: dict[str, Any] = {
            "score": round(score),
            "label": label,
            "reasons": reasons[:6],
            "metrics": metrics,
            "primary_model": primary,
            "secondary_model": secondary,
        }

        return (score, output)
