from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import Field

from parames.common import LocationConfig
from parames.domain import HourForecast, PluginReport, RuleEvaluation
from parames.forecast import OpenMeteoForecastClient
from parames.plugins.base import PluginConfigBase, PluginScoringResult, register_plugin


class BisePluginConfig(PluginConfigBase):
    type: Literal["bise"] = "bise"
    east_minus_west_pressure_hpa_min: float = Field(default=1.5, ge=0)
    pressure_reference_west: LocationConfig
    pressure_reference_east: LocationConfig


PressureByModel = dict[str, dict[datetime, HourForecast]]


class BisePrefetched:
    __slots__ = ("west", "east")

    def __init__(self, west: PressureByModel, east: PressureByModel) -> None:
        self.west = west
        self.east = east


@register_plugin
class BisePlugin:
    """East-minus-West pressure gradient — corroboration signal.

    Returns a sub-score in [0, 100] when the pressure gradient confirms a Bise
    pattern, or `None` to opt out (no positive corroboration, missing data, or
    incomplete window). Opting out means Bise is excluded from both numerator
    and denominator of the weighted-mean composite.
    """

    type: ClassVar[str] = "bise"

    def __init__(self, config: BisePluginConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def prefetch(self, *, client: OpenMeteoForecastClient, models: list[str], location: LocationConfig) -> BisePrefetched:  # noqa: ARG002
        west: PressureByModel = {}
        east: PressureByModel = {}
        for model in models:
            west[model] = client.fetch_hourly_forecast(
                location=self.config.pressure_reference_west,
                model=model,
                hourly_variables=["pressure_msl"],
            )
            east[model] = client.fetch_hourly_forecast(
                location=self.config.pressure_reference_east,
                model=model,
                hourly_variables=["pressure_msl"],
            )
        return BisePrefetched(west=west, east=east)

    def score_window(
        self,
        *,
        window_times: list[datetime],
        prefetched: BisePrefetched,
        contributing_models: list[str],
    ) -> PluginScoringResult:
        cfg = self.config
        gradients: list[float] = []
        hourly: list[dict[str, Any]] = []
        missing_timestamps: int = 0

        for timestamp in window_times:
            per_model: dict[str, float] = {}
            for model in contributing_models:
                west = prefetched.west.get(model, {}).get(timestamp)
                east = prefetched.east.get(model, {}).get(timestamp)
                if (
                    west is None
                    or east is None
                    or west.pressure_msl is None
                    or east.pressure_msl is None
                ):
                    continue
                per_model[model] = round(east.pressure_msl - west.pressure_msl, 3)
            if per_model:
                mean_gradient = sum(per_model.values()) / len(per_model)
                gradients.append(mean_gradient)
                hourly.append({
                    "time": timestamp.isoformat(),
                    "per_model_gradient_hpa": per_model,
                    "mean_gradient_hpa": round(mean_gradient, 3),
                })
            else:
                missing_timestamps += 1
                hourly.append({
                    "time": timestamp.isoformat(),
                    "per_model_gradient_hpa": {},
                    "mean_gradient_hpa": None,
                })

        data_complete = missing_timestamps == 0 and len(gradients) == len(window_times)

        if not data_complete or not gradients:
            completeness_rule = RuleEvaluation(
                name="data_completeness",
                observed=f"{len(gradients)}/{len(window_times)} timestamps with data",
                threshold=len(window_times),
                outcome="fail",
                message="Insufficient pressure data — opting out",
            )
            plugin_report = PluginReport(
                type="bise",
                config_snapshot=cfg.model_dump(mode="json"),
                inputs={
                    "contributing_models": contributing_models,
                    "west_location": cfg.pressure_reference_west.model_dump(),
                    "east_location": cfg.pressure_reference_east.model_dump(),
                },
                metrics={},
                hourly=hourly,
                rules=[completeness_rule],
            )
            return PluginScoringResult(sub_score=None, output={}, report=plugin_report)

        gradient = sum(gradients) / len(gradients)
        output = {"gradient_hpa": gradient}

        if gradient >= 3.0:
            sub_score = 100.0
            grad_outcome = "pass"
            grad_message = f"Strong gradient {gradient:.2f} hPa ≥ 3.0"
        elif gradient >= cfg.east_minus_west_pressure_hpa_min:
            sub_score = 75.0
            grad_outcome = "warn"
            grad_message = f"Gradient {gradient:.2f} hPa ≥ {cfg.east_minus_west_pressure_hpa_min} hPa (threshold)"
        else:
            sub_score = None
            grad_outcome = "fail"
            grad_message = f"Gradient {gradient:.2f} hPa < {cfg.east_minus_west_pressure_hpa_min} hPa — opting out"

        metrics = {
            "avg_gradient_hpa": round(gradient, 3),
            "min_gradient_hpa": round(min(gradients), 3),
            "max_gradient_hpa": round(max(gradients), 3),
        }

        rules: list[RuleEvaluation] = [
            RuleEvaluation(
                name="data_completeness",
                observed=f"{len(gradients)}/{len(window_times)} timestamps with data",
                threshold=len(window_times),
                outcome="pass",
            ),
            RuleEvaluation(
                name="gradient_threshold",
                observed=round(gradient, 3),
                threshold=cfg.east_minus_west_pressure_hpa_min,
                outcome=grad_outcome,
                message=grad_message,
            ),
        ]

        plugin_report = PluginReport(
            type="bise",
            summary=f"Avg gradient {gradient:.2f} hPa — {grad_outcome}",
            config_snapshot=cfg.model_dump(mode="json"),
            inputs={
                "contributing_models": contributing_models,
                "west_location": cfg.pressure_reference_west.model_dump(),
                "east_location": cfg.pressure_reference_east.model_dump(),
            },
            metrics=metrics,
            hourly=hourly,
            rules=rules,
        )

        return PluginScoringResult(sub_score=sub_score, output=output, report=plugin_report)
