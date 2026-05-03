from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parames.domain import CandidateWindow
from parames.persistence import is_same_event, local_date_for_window

ZURICH = ZoneInfo("Europe/Zurich")


def _window(
    *,
    alert_name: str = "zurich_bise",
    start: datetime,
    duration_hours: int = 3,
    score: int | None = 50,
    classification: str = "candidate",
) -> CandidateWindow:
    return CandidateWindow(
        alert_name=alert_name,
        start=start,
        end=start + timedelta(hours=duration_hours),
        duration_hours=duration_hours,
        avg_wind_speed_kmh=12.0,
        max_wind_speed_kmh=14.0,
        avg_direction_deg=60.0,
        avg_precipitation_mm_per_hour=0.0,
        max_precipitation_mm_per_hour=0.0,
        models=["icon_d2"],
        dry_filter_applied=False,
        score=score,
        classification=classification,
        hours=[],
    )


def test_local_date_uses_zurich_timezone() -> None:
    # 23:30 UTC on 2026-04-27 is 01:30 Zurich on 2026-04-28.
    window = _window(start=datetime(2026, 4, 27, 23, 30, tzinfo=ZoneInfo("UTC")))
    assert local_date_for_window(window) == "2026-04-28"


def test_overlapping_windows_same_day_match() -> None:
    a = _window(start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH), duration_hours=3)  # 09-12
    b = _window(start=datetime(2026, 4, 28, 11, 0, tzinfo=ZURICH), duration_hours=3)  # 11-14
    assert is_same_event(a, b)


def test_touching_but_non_overlapping_do_not_match() -> None:
    a = _window(start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH), duration_hours=2)  # 09-11
    b = _window(start=datetime(2026, 4, 28, 11, 0, tzinfo=ZURICH), duration_hours=2)  # 11-13
    assert not is_same_event(a, b)


def test_same_day_disjoint_windows_do_not_match() -> None:
    morning = _window(start=datetime(2026, 4, 28, 8, 0, tzinfo=ZURICH), duration_hours=2)
    afternoon = _window(start=datetime(2026, 4, 28, 17, 0, tzinfo=ZURICH), duration_hours=2)
    assert not is_same_event(morning, afternoon)


def test_different_local_dates_do_not_match() -> None:
    a = _window(start=datetime(2026, 4, 28, 18, 0, tzinfo=ZURICH), duration_hours=3)
    b = _window(start=datetime(2026, 4, 29, 18, 0, tzinfo=ZURICH), duration_hours=3)
    assert not is_same_event(a, b)


def test_different_alert_names_do_not_match() -> None:
    a = _window(alert_name="zurich_bise", start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH))
    b = _window(alert_name="berner_thermal", start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH))
    assert not is_same_event(a, b)


def test_classification_upgrade_still_dedupes() -> None:
    """v1 explicitly suppresses re-delivery on score upgrades; this guards that decision."""
    weak = _window(
        start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH),
        score=30,
        classification="weak",
    )
    strong = _window(
        start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH),
        score=75,
        classification="strong",
    )
    assert is_same_event(weak, strong)


@pytest.mark.parametrize(
    "candidate_start_hour,expected_match",
    [
        (8, True),  # candidate 08-11 vs prior 09-12 → overlap
        (10, True),  # candidate 10-13 vs prior 09-12 → overlap
        (12, False),  # candidate 12-15 vs prior 09-12 → touches at 12, no overlap
        (13, False),  # candidate 13-16 vs prior 09-12 → disjoint
    ],
)
def test_overlap_boundaries(candidate_start_hour: int, expected_match: bool) -> None:
    prior = _window(start=datetime(2026, 4, 28, 9, 0, tzinfo=ZURICH), duration_hours=3)
    candidate = _window(
        start=datetime(2026, 4, 28, candidate_start_hour, 0, tzinfo=ZURICH),
        duration_hours=3,
    )
    assert is_same_event(prior, candidate) is expected_match
