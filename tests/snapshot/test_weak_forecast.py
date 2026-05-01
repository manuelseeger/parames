from __future__ import annotations

from pathlib import Path

from parames.evaluation import evaluate
from snapshot_fixtures import SnapshotForecastClient

FIXTURE_DIR = Path("tests/fixtures/open_meteo/mainz_finthen_2026-05-01")


def test_mainz_finthen_weak_forecast(default_config) -> None:
    profile = next(a for a in default_config.alerts if a.name == "mainz_finthen")
    snapshot_client = SnapshotForecastClient(FIXTURE_DIR)

    try:
        windows = evaluate(profile, client=snapshot_client, now=snapshot_client.captured_at, scoring=default_config.scoring)
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
    assert window.score < strong_min, f"Expected weak forecast (score < {strong_min}), got {window.score}"
    assert window.classification == "weak"
