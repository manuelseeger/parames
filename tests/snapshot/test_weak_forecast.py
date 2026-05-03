from __future__ import annotations

from pathlib import Path

from parames.evaluation import evaluate
from snapshot_fixtures import SnapshotForecastClient

FIXTURE_DIR = Path("tests/fixtures/open_meteo/mainz_finthen_2026-05-01")
FIXTURE_DIR_2026_05_03 = Path("tests/fixtures/open_meteo/mainz_finthen_2026-05-03")


def test_mainz_finthen_weak_forecast(default_config) -> None:
    profile = next(a for a in default_config.alerts if a.name == "mainz_finthen")
    snapshot_client = SnapshotForecastClient(FIXTURE_DIR)

    try:
        windows = evaluate(
            profile,
            client=snapshot_client,
            now=snapshot_client.captured_at,
            scoring=default_config.scoring,
        )
    finally:
        snapshot_client.close()

    assert len(windows) == 1
    window = windows[0]
    expected = snapshot_client.expected_windows[0]

    assert window.alert_name == expected["alert_name"]
    assert window.start.isoformat() == expected["start"]
    assert window.end.isoformat() == expected["end"]
    assert window.score == expected["score"]

    strong_min = default_config.scoring.tiers.strong_min
    assert window.score < strong_min, (
        f"Expected below-strong forecast (score < {strong_min}), got {window.score}"
    )
    assert window.classification.value == expected["classification"]


def test_mainz_finthen_2026_05_03_weak_laminar(default_config) -> None:
    """2026-05-03: gusty, model-disagreeing conditions → weak laminar signal.

    With strict model agreement, no window passes (speed delta 13+ km/h at peak).
    Relaxing `required=False` surfaces the 15–17 window so the laminar quality
    can be inspected directly.
    """
    profile = next(a for a in default_config.alerts if a.name == "mainz_finthen")
    snapshot_client = SnapshotForecastClient(FIXTURE_DIR_2026_05_03)

    # Relax model agreement to surface the gusty 15-17 window that normally fails
    # the speed-delta check (icon_d2 ~12 km/h vs ecmwf_ifs ~22-26 km/h).
    agreement = profile.model_agreement.model_copy(update={"required": False})
    loose_profile = profile.model_copy(update={"model_agreement": agreement})
    scoring = default_config.scoring.model_copy(update={"emit_threshold": 0})

    try:
        windows = evaluate(
            loose_profile,
            client=snapshot_client,
            now=snapshot_client.captured_at,
            scoring=scoring,
        )
    finally:
        snapshot_client.close()

    assert len(windows) >= 1, (
        "Expected at least one candidate window with relaxed agreement"
    )
    window = windows[0]

    laminar = window.plugin_outputs.get("laminar", {})
    assert laminar.get("label") in ("poor", "marginal"), (
        f"Expected weak laminar signal (poor/marginal), got {laminar.get('label')!r}"
    )
