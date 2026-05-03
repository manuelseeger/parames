from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import ConfigDict
from pyodmongo import MainBaseModel

from parames.common import LocationConfig


class PluginConfigBase(MainBaseModel):
    """Base for all plugin config blocks. Concrete plugins set a Literal `type`."""

    type: str
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


class PluginScoringResult(MainBaseModel):
    sub_score: float | None
    output: dict[str, Any] = {}
    report: Any | None = None  # PluginReport — typed as Any to avoid circular import


@runtime_checkable
class EvaluationPlugin(Protocol):
    """A pluggable extra evaluation slotted into an alert profile.

    Lifecycle per evaluation run:
      1. `prefetch` — fetch any extra forecast data the plugin needs.
      2. `score_window` — at window-scoring time, return a PluginScoringResult.
         `sub_score` is a float in [0, 100] that participates in the weighted-mean
         aggregator, or `None` to opt out of this window.
         `output` is stored on `CandidateWindow.plugin_outputs[type]`.
         `report` is appended to `EvaluationReport.plugin_reports`.

    Per-plugin weight is global config, looked up from
    `ScoringConfig.weights.plugins[type]` at aggregation time.
    """

    type: ClassVar[str]

    @property
    def enabled(self) -> bool: ...

    def prefetch(self, *, client: Any, models: list[str], location: LocationConfig) -> Any: ...

    def score_window(
        self,
        *,
        window_times: list[datetime],
        prefetched: Any,
        contributing_models: list[str],
    ) -> PluginScoringResult: ...


PLUGIN_REGISTRY: dict[str, type[EvaluationPlugin]] = {}


def register_plugin(cls: type[EvaluationPlugin]) -> type[EvaluationPlugin]:
    PLUGIN_REGISTRY[cls.type] = cls
    return cls


def build_plugins(plugin_configs: list[PluginConfigBase]) -> list[EvaluationPlugin]:
    """Instantiate plugin runtimes for each config entry whose plugin is registered."""
    instances: list[EvaluationPlugin] = []
    for cfg in plugin_configs:
        plugin_cls = PLUGIN_REGISTRY.get(cfg.type)
        if plugin_cls is None:
            raise ValueError(f"Unknown plugin type: {cfg.type!r}")
        instances.append(plugin_cls(cfg))  # type: ignore[arg-type]
    return instances
