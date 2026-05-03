from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parames.domain import HourForecast
from parames.plugins.laminar import (
    LaminarPlugin,
    LaminarPluginConfig,
    LaminarPrefetched,
)

ZURICH = ZoneInfo("Europe/Zurich")

# Base timestamp: one hour slot used by single-hour window tests.
TS = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)

# Four consecutive hours for multi-hour window tests.
TS4 = [TS + timedelta(hours=i) for i in range(4)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(**kwargs) -> LaminarPluginConfig:
    return LaminarPluginConfig(**kwargs)


def _hour(
    ts: datetime,
    *,
    wind_speed: float = 20.0,
    wind_direction: float = 60.0,
    wind_gusts: float = 24.0,
    precipitation: float = 0.0,
    showers: float = 0.0,
    cape: float = 10.0,
    pressure_msl: float = 1015.0,
) -> HourForecast:
    return HourForecast(
        time=ts,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        wind_gusts=wind_gusts,
        precipitation=precipitation,
        showers=showers,
        cape=cape,
        pressure_msl=pressure_msl,
    )


def _prefetched(
    primary_hours: dict[datetime, HourForecast],
    secondary_hours: dict[datetime, HourForecast] | None = None,
    primary_model: str = "icon_d2",
    secondary_model: str = "ecmwf_ifs",
) -> LaminarPrefetched:
    data: dict[str, dict[datetime, HourForecast]] = {primary_model: primary_hours}
    if secondary_hours is not None:
        data[secondary_model] = secondary_hours
    return LaminarPrefetched(data=data)


def _score(
    cfg: LaminarPluginConfig | None = None,
    hours: dict[datetime, HourForecast] | None = None,
    secondary_hours: dict[datetime, HourForecast] | None = None,
    window_times: list[datetime] | None = None,
    contributing_models: list[str] | None = None,
    primary_model: str = "icon_d2",
    secondary_model: str = "ecmwf_ifs",
) -> tuple[float | None, dict]:
    if cfg is None:
        cfg = _config()
    if hours is None:
        hours = {TS: _hour(TS)}
    if window_times is None:
        window_times = [TS]
    if contributing_models is None:
        models = [primary_model]
        if secondary_hours is not None:
            models.append(secondary_model)
        contributing_models = models
    pre = _prefetched(
        hours,
        secondary_hours,
        primary_model=primary_model,
        secondary_model=secondary_model,
    )
    plugin = LaminarPlugin(cfg)
    result = plugin.score_window(
        window_times=window_times,
        prefetched=pre,
        contributing_models=contributing_models,
    )
    return result.sub_score, result.output


# ---------------------------------------------------------------------------
# Gust factor scoring
# ---------------------------------------------------------------------------


def test_gust_factor_good_tier_no_penalty() -> None:
    """max_gust_factor ≤ 1.35 → 0 penalty from gust_factor, reason low_gust_factor."""
    # gust_factor = 24 / max(20, 1) = 1.20 → good tier → no gust_factor penalty
    sub, out = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=24.0)})
    assert sub is not None
    assert "low_gust_factor" in out["reasons"]
    assert "very_gusty" not in out["reasons"]
    assert "high_gust_factor" not in out["reasons"]


def test_gust_factor_marginal_tier_penalty_15() -> None:
    """max_gust_factor > 1.35, ≤ 1.60 → 15 penalty."""
    # gust_factor = 30 / 20 = 1.50
    sub, out = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=30.0)})
    assert sub is not None
    assert "high_gust_factor" in out["reasons"]
    # Base 100, −15 gust_factor; other metrics at default-good values
    assert sub <= 100.0 - 15 + 0.5  # some slack for other signals


def test_gust_factor_bad_tier_penalty_35() -> None:
    """max_gust_factor > 1.60 → 35 penalty, reason very_gusty."""
    # gust_factor = 40 / 20 = 2.00
    sub, out = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=40.0)})
    assert sub is not None
    assert "very_gusty" in out["reasons"]


# ---------------------------------------------------------------------------
# Direction stability
# ---------------------------------------------------------------------------


def test_direction_stable_no_penalty() -> None:
    """All hours same direction → direction_variability = 0 → reason stable_direction."""
    hours = {ts: _hour(ts, wind_direction=60.0) for ts in TS4}
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "stable_direction" in out["reasons"]


def test_direction_shifting_penalty() -> None:
    """Directions spread > 20° but ≤ 40° → 10 penalty, reason shifting_direction."""
    # Mean ~60°; one hour at 90° → variability ~30°
    hours = {
        TS4[0]: _hour(TS4[0], wind_direction=50.0),
        TS4[1]: _hour(TS4[1], wind_direction=60.0),
        TS4[2]: _hour(TS4[2], wind_direction=60.0),
        TS4[3]: _hour(TS4[3], wind_direction=85.0),
    }
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "shifting_direction" in out["reasons"]


def test_direction_wrap_through_north() -> None:
    """Directions straddling 0°/360° are handled correctly by vector mean."""
    # 350°, 0°, 10°, 355° — mean ~0°, all within 15° → stable
    hours = {
        TS4[0]: _hour(TS4[0], wind_direction=350.0),
        TS4[1]: _hour(TS4[1], wind_direction=0.0),
        TS4[2]: _hour(TS4[2], wind_direction=10.0),
        TS4[3]: _hour(TS4[3], wind_direction=355.0),
    }
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "stable_direction" in out["reasons"]


def test_direction_very_shifty_penalty() -> None:
    """direction_variability > 40° → 25 penalty, reason very_shifty."""
    # 0°, 90°, 90°, 0° → vector mean ≈ 45° → max variability = 45° > 40°
    hours = {
        TS4[0]: _hour(TS4[0], wind_direction=0.0),
        TS4[1]: _hour(TS4[1], wind_direction=90.0),
        TS4[2]: _hour(TS4[2], wind_direction=90.0),
        TS4[3]: _hour(TS4[3], wind_direction=0.0),
    }
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "very_shifty" in out["reasons"]


# ---------------------------------------------------------------------------
# Speed stability
# ---------------------------------------------------------------------------


def test_speed_range_good() -> None:
    """speed_range ≤ 4 km/h → 0 penalty, reason low_speed_range."""
    hours = {
        TS4[0]: _hour(TS4[0], wind_speed=20.0),
        TS4[1]: _hour(TS4[1], wind_speed=22.0),
        TS4[2]: _hour(TS4[2], wind_speed=21.0),
        TS4[3]: _hour(TS4[3], wind_speed=22.0),
    }
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "low_speed_range" in out["reasons"]


def test_speed_range_high() -> None:
    """speed_range > 7 km/h → 20 penalty, reason high_speed_range."""
    hours = {
        TS4[0]: _hour(TS4[0], wind_speed=15.0),
        TS4[1]: _hour(TS4[1], wind_speed=25.0),
        TS4[2]: _hour(TS4[2], wind_speed=24.0),
        TS4[3]: _hour(TS4[3], wind_speed=16.0),
    }
    sub, out = _score(hours=hours, window_times=TS4)
    assert sub is not None
    assert "high_speed_range" in out["reasons"]


# ---------------------------------------------------------------------------
# CAPE
# ---------------------------------------------------------------------------


def test_cape_good_tier_no_penalty() -> None:
    """max_cape ≤ 50 → 0 penalty, reason low_cape."""
    sub, out = _score(hours={TS: _hour(TS, cape=30.0)})
    assert sub is not None
    assert "low_cape" in out["reasons"]


def test_cape_moderate_tier_penalty_10() -> None:
    """50 < max_cape ≤ 200 → 10 penalty, reason moderate_cape."""
    sub, out = _score(hours={TS: _hour(TS, cape=100.0)})
    assert sub is not None
    assert "moderate_cape" in out["reasons"]


def test_cape_high_tier_penalty_25() -> None:
    """max_cape > 200 → 25 penalty, reason high_cape."""
    sub, out = _score(hours={TS: _hour(TS, cape=300.0)})
    assert sub is not None
    assert "high_cape" in out["reasons"]


def test_cape_missing_skips_penalty() -> None:
    """cape is None for >50% of hours → penalty skipped, reason cape_unavailable."""
    hours = {
        TS: HourForecast(
            time=TS,
            wind_speed=20.0,
            wind_direction=60.0,
            wind_gusts=24.0,
            precipitation=0.0,
            pressure_msl=1015.0,
            cape=None,
        )
    }
    sub, out = _score(hours=hours)
    assert sub is not None
    assert "cape_unavailable" in out["reasons"]


# ---------------------------------------------------------------------------
# Precipitation / showers
# ---------------------------------------------------------------------------


def test_precipitation_triggers_penalty() -> None:
    """max_precipitation > 0 → 30 penalty, reason precipitation_risk."""
    sub, out = _score(hours={TS: _hour(TS, precipitation=0.5)})
    assert sub is not None
    assert "precipitation_risk" in out["reasons"]


def test_showers_triggers_penalty_when_precip_zero() -> None:
    """showers > 0 while precipitation == 0 → 30 penalty, reason showers_risk."""
    sub, out = _score(hours={TS: _hour(TS, precipitation=0.0, showers=0.3)})
    assert sub is not None
    assert "showers_risk" in out["reasons"]


def test_showers_missing_alone_ok() -> None:
    """showers=None, precipitation=0 → no precipitation penalty."""
    hours = {
        TS: HourForecast(
            time=TS,
            wind_speed=20.0,
            wind_direction=60.0,
            wind_gusts=24.0,
            precipitation=0.0,
            pressure_msl=1015.0,
            showers=None,
            cape=10.0,
        )
    }
    sub, out = _score(hours=hours)
    assert sub is not None
    assert "precipitation_risk" not in out["reasons"]
    assert "showers_risk" not in out["reasons"]


# ---------------------------------------------------------------------------
# Model agreement
# ---------------------------------------------------------------------------


def test_model_agreement_good() -> None:
    """Primary and secondary agree well → 0 penalty, reason model_agreement_good."""
    primary = {TS: _hour(TS, wind_direction=60.0, wind_speed=20.0)}
    secondary = {TS: _hour(TS, wind_direction=63.0, wind_speed=21.0)}
    sub, out = _score(hours=primary, secondary_hours=secondary)
    assert sub is not None
    assert "model_agreement_good" in out["reasons"]


def test_model_agreement_marginal_penalty_10() -> None:
    """Direction delta ≤ 40°, speed delta ≤ 8 km/h → 10 penalty."""
    primary = {TS: _hour(TS, wind_direction=60.0, wind_speed=20.0)}
    secondary = {TS: _hour(TS, wind_direction=90.0, wind_speed=25.0)}
    sub, out = _score(hours=primary, secondary_hours=secondary)
    assert sub is not None
    assert "model_disagreement" in out["reasons"]


def test_model_agreement_bad_penalty_25() -> None:
    """Direction delta > 40° → 25 penalty, reason model_disagreement."""
    primary = {TS: _hour(TS, wind_direction=60.0, wind_speed=20.0)}
    secondary = {TS: _hour(TS, wind_direction=120.0, wind_speed=30.0)}
    sub, out = _score(hours=primary, secondary_hours=secondary)
    assert sub is not None
    assert "model_disagreement" in out["reasons"]


def test_secondary_model_unavailable_penalty_10() -> None:
    """No secondary model → 10 penalty, reason secondary_model_unavailable."""
    sub, out = _score(
        hours={TS: _hour(TS)},
        secondary_hours=None,
        contributing_models=["icon_d2"],
    )
    assert sub is not None
    assert "secondary_model_unavailable" in out["reasons"]


def test_model_agreement_uses_percentile_for_4h_window() -> None:
    """4h window uses 75th percentile; a single outlier hour should not dominate."""
    # Three hours agree well, one hour has large delta. Percentile should be low.
    primary = {ts: _hour(ts, wind_direction=60.0, wind_speed=20.0) for ts in TS4}
    secondary = {
        TS4[0]: _hour(TS4[0], wind_direction=62.0, wind_speed=21.0),
        TS4[1]: _hour(TS4[1], wind_direction=63.0, wind_speed=22.0),
        TS4[2]: _hour(TS4[2], wind_direction=61.0, wind_speed=20.0),
        TS4[3]: _hour(TS4[3], wind_direction=110.0, wind_speed=32.0),  # outlier
    }
    sub, out = _score(hours=primary, secondary_hours=secondary, window_times=TS4)
    # With percentile, p75 of [2°, 3°, 1°, 50°] ≈ 14° which is still within good_max
    assert sub is not None
    assert "model_agreement_good" in out["reasons"]


# ---------------------------------------------------------------------------
# Pressure tendency
# ---------------------------------------------------------------------------


def test_pressure_stable_no_penalty() -> None:
    """abs(pressure_tendency_3h) ≤ 1.5 → 0 penalty, reason pressure_stable."""
    # window_start + 3h exists in prefetched data
    ts_start = TS
    ts_3h = TS + timedelta(hours=3)
    hours = {
        ts_start: _hour(ts_start, pressure_msl=1015.0),
        ts_3h: _hour(ts_3h, pressure_msl=1015.5),
    }
    sub, out = _score(hours=hours, window_times=[ts_start])
    assert sub is not None
    assert "pressure_stable" in out["reasons"]
    assert out["metrics"]["pressure_tendency_3h_hpa"] == pytest.approx(0.5, abs=0.01)


def test_pressure_unstable_penalty() -> None:
    """abs(pressure_tendency_3h) > 2.5 → 15 penalty, reason pressure_unstable."""
    ts_start = TS
    ts_3h = TS + timedelta(hours=3)
    hours = {
        ts_start: _hour(ts_start, pressure_msl=1015.0),
        ts_3h: _hour(ts_3h, pressure_msl=1012.0),  # −3 hPa
    }
    sub, out = _score(hours=hours, window_times=[ts_start])
    assert sub is not None
    assert "pressure_unstable" in out["reasons"]


def test_pressure_tendency_fallback_near_horizon() -> None:
    """When window_start + 3h is not in prefetched data, fall back to scaling."""
    # Only two hours available, no t+3h slot
    ts_a = TS
    ts_b = TS + timedelta(hours=1)
    hours = {
        ts_a: _hour(ts_a, pressure_msl=1015.0),
        ts_b: _hour(ts_b, pressure_msl=1014.0),  # −1 hPa over 1h → −3 hPa/3h
    }
    sub, out = _score(hours=hours, window_times=[ts_a])
    assert sub is not None
    # Fallback: (1014 − 1015) * (3 / 1) = −3 → abs = 3 → unstable
    assert "pressure_unstable" in out["reasons"]


# ---------------------------------------------------------------------------
# Label mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score_val, expected_label",
    [
        (100, "excellent"),
        (85, "excellent"),
        (84, "good"),
        (70, "good"),
        (69, "marginal"),
        (55, "marginal"),
        (54, "poor"),
        (0, "poor"),
    ],
)
def test_label_boundaries(score_val: int, expected_label: str) -> None:
    """Label is assigned correctly at each boundary."""
    from parames.plugins.laminar import _score_to_label

    assert _score_to_label(float(score_val)) == expected_label


# ---------------------------------------------------------------------------
# Sub-score pass-through
# ---------------------------------------------------------------------------


def test_subscore_is_raw_float_not_rounded_int() -> None:
    """score_window tuple[0] is the raw float; output['score'] is the rounded int."""
    sub, out = _score(hours={TS: _hour(TS)})
    assert sub is not None
    assert isinstance(sub, float)
    assert isinstance(out["score"], int)
    assert out["score"] == round(sub)


# ---------------------------------------------------------------------------
# Missing required wind data
# ---------------------------------------------------------------------------


def test_missing_wind_speed_returns_none() -> None:
    """Missing wind_speed → (None, unavailable dict), no exception."""
    hours = {
        TS: HourForecast(time=TS, wind_speed=None, wind_direction=60.0, wind_gusts=24.0)
    }
    sub, out = _score(hours=hours)
    assert sub is None
    assert out["label"] == "unavailable"
    assert "missing_required_wind_data" in out["reasons"]


def test_missing_wind_direction_returns_none() -> None:
    hours = {
        TS: HourForecast(time=TS, wind_speed=20.0, wind_direction=None, wind_gusts=24.0)
    }
    sub, out = _score(hours=hours)
    assert sub is None


def test_missing_wind_gusts_returns_none() -> None:
    hours = {
        TS: HourForecast(time=TS, wind_speed=20.0, wind_direction=60.0, wind_gusts=None)
    }
    sub, out = _score(hours=hours)
    assert sub is None


# ---------------------------------------------------------------------------
# Disabled plugin
# ---------------------------------------------------------------------------


def test_disabled_plugin_reports_enabled_false() -> None:
    plugin = LaminarPlugin(_config(enabled=False))
    assert not plugin.enabled


# ---------------------------------------------------------------------------
# Primary model substitution
# ---------------------------------------------------------------------------


def test_primary_model_substituted_when_not_in_contributing() -> None:
    """Configured primary not in contributing_models → fallback + reason."""
    cfg = _config(primary_model="meteoswiss_icon_ch2")
    hours = {TS: _hour(TS)}
    pre = LaminarPrefetched(data={"icon_d2": hours})
    plugin = LaminarPlugin(cfg)
    result = plugin.score_window(
        window_times=[TS],
        prefetched=pre,
        contributing_models=["icon_d2"],  # configured primary is absent
    )
    assert result.sub_score is not None
    assert "primary_model_substituted" in result.output["reasons"]
    assert result.output["primary_model"] == "icon_d2"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_discriminator_routes_laminar() -> None:
    """Discriminated union correctly resolves type: laminar."""
    from parames.plugins.schemas import PluginConfig
    from pydantic import TypeAdapter

    adapter = TypeAdapter(PluginConfig)
    cfg = adapter.validate_python({"type": "laminar", "enabled": True})
    assert isinstance(cfg, LaminarPluginConfig)


def test_config_rejects_unknown_fields() -> None:
    """extra='forbid' from PluginConfigBase rejects unknown fields."""
    with pytest.raises(Exception):
        LaminarPluginConfig(type="laminar", unknown_field=99)
