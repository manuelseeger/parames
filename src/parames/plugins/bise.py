from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import Field

from parames.common import LocationConfig
from parames.domain import HourForecast
from parames.forecast import OpenMeteoForecastClient
from parames.plugins.base import PluginConfigBase, register_plugin


class BisePluginConfig(PluginConfigBase):
    type: Literal["bise"] = "bise"
    east_minus_west_pressure_hpa_min: float = Field(default=1.5, ge=0)
    boost_if_bise: bool = True
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
    """East-minus-West pressure gradient. Applies a +1/+2 score boost."""

    type: ClassVar[str] = "bise"

    def __init__(self, config: BisePluginConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def prefetch(self, *, client: OpenMeteoForecastClient, models: list[str]) -> BisePrefetched:
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
    ) -> tuple[int, dict[str, Any]]:
        gradients: list[float] = []
        for timestamp in window_times:
            per_model: list[float] = []
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
                per_model.append(east.pressure_msl - west.pressure_msl)
            if per_model:
                gradients.append(sum(per_model) / len(per_model))

        if len(gradients) != len(window_times) or not gradients:
            return 0, {}

        gradient = sum(gradients) / len(gradients)
        boost = 0
        if self.config.boost_if_bise:
            if gradient >= 3.0:
                boost = 2
            elif gradient >= self.config.east_minus_west_pressure_hpa_min:
                boost = 1
        return boost, {"gradient_hpa": gradient}
