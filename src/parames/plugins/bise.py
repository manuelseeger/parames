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
    and denominator of the weighted-mean composite — a windless dry day is
    not penalised for "no Bise gradient".
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
    ) -> tuple[float | None, dict[str, Any]]:
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
            return None, {}

        gradient = sum(gradients) / len(gradients)
        # Always emit the gradient for display, even when corroboration is absent.
        output = {"gradient_hpa": gradient}

        if gradient >= 3.0:
            return 100.0, output
        if gradient >= self.config.east_minus_west_pressure_hpa_min:
            return 75.0, output
        # Below threshold — gradient is real but not corroborating. Opt out.
        return None, output
