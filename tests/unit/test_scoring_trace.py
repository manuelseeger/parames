from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parames.config import ScoringConfig, ScoringWeightsConfig
from parames.evaluation import score_window
from parames.evaluation.windows import EvaluatedHour

ZURICH = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 4, 29, 10, 0, tzinfo=ZURICH)


def _hours(count: int, speed: float) -> list[EvaluatedHour]:
    return [
        EvaluatedHour(
            time=NOW + timedelta(hours=i),
            avg_wind_speed_kmh=speed,
            max_wind_speed_kmh=speed + 1.0,
            avg_direction_deg=60.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.0,
        )
        for i in range(count)
    ]


def test_scoring_trace_contributions_included(default_config) -> None:
    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    hours = _hours(4, 16.0)
    window = score_window(profile, hours)

    assert window.report is not None
    trace = window.report.scoring
    assert "wind_speed" in trace.contributions
    assert "wind_duration" in trace.contributions

    for name, c in trace.contributions.items():
        assert "weight" in c
        assert "sub_score" in c
        assert "weighted_value" in c
        assert "included" in c


def test_scoring_trace_weight_total_and_raw_score(default_config) -> None:
    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    hours = _hours(4, 19.0)  # speed=100, dur=100
    window = score_window(profile, hours)

    assert window.report is not None
    trace = window.report.scoring

    assert trace.weight_total == pytest.approx(
        trace.weights["wind_speed"] + trace.weights["wind_duration"], abs=1e-4
    )
    assert trace.weighted_sum == pytest.approx(
        sum(
            c["weight"] * c["sub_score"]
            for c in trace.contributions.values()
            if c["included"]
        ),
        abs=1e-4,
    )
    expected_raw = trace.weighted_sum / trace.weight_total
    assert trace.raw_score == pytest.approx(expected_raw, abs=0.02)
    assert trace.final_score == max(0, min(100, round(expected_raw)))


def test_scoring_trace_opt_out_plugin_excluded(default_config) -> None:
    from typing import Any
    from parames.plugins.base import PluginScoringResult

    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    hours = _hours(4, 16.0)

    class _NullPlugin:
        type = "bise"
        enabled = True
        def prefetch(self, **_): return None
        def score_window(self, **_) -> PluginScoringResult:
            return PluginScoringResult(sub_score=None, output={})

    scoring = ScoringConfig(weights=ScoringWeightsConfig(wind_speed=1.0, wind_duration=1.0, plugins={"bise": 0.5}))
    window_with = score_window(profile, hours, plugins=[_NullPlugin()], scoring=scoring)
    window_without = score_window(profile, hours, scoring=scoring)

    assert window_with.score == window_without.score
    assert window_with.report is not None
    bise_contrib = window_with.report.scoring.contributions["bise"]
    assert bise_contrib["included"] is False
    assert bise_contrib["weighted_value"] is None


def test_scoring_trace_tiers_snapshot(default_config) -> None:
    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    window = score_window(profile, _hours(4, 16.0), scoring=default_config.scoring)

    assert window.report is not None
    tiers = window.report.scoring.tiers
    assert "candidate_min" in tiers
    assert "strong_min" in tiers
    assert "excellent_min" in tiers
    assert tiers["candidate_min"] < tiers["strong_min"] < tiers["excellent_min"]


def test_scoring_trace_classification_matches_score(default_config) -> None:
    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    window = score_window(profile, _hours(4, 16.0), scoring=default_config.scoring)

    assert window.report is not None
    assert window.report.scoring.classification == window.classification
    assert window.report.scoring.final_score == window.score
