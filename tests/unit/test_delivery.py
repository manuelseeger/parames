from __future__ import annotations

from datetime import datetime
from io import StringIO

from rich.console import Console

from parames.delivery.delivery_cli import ConsoleChannel
from parames.domain import CandidateWindow, WindowHour


def test_console_channel_renders_precipitation() -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=120)
    channel = ConsoleChannel(console=console)
    window = CandidateWindow(
        alert_name="zurich_bise",
        start=datetime(2026, 4, 29, 11, 0),
        end=datetime(2026, 4, 29, 13, 0),
        duration_hours=2,
        avg_wind_speed_kmh=10.5,
        max_wind_speed_kmh=12.0,
        avg_direction_deg=60.0,
        avg_precipitation_mm_per_hour=0.4,
        max_precipitation_mm_per_hour=0.7,
        bise_pressure_gradient_hpa=2.0,
        models=["icon_d2", "meteoswiss_icon_ch2"],
        dry_filter_applied=False,
        score=4,
        classification="candidate",
        hours=[
            WindowHour(
                time=datetime(2026, 4, 29, 11, 0),
                avg_wind_speed_kmh=10.0,
                avg_direction_deg=55.0,
                avg_precipitation_mm_per_hour=0.3,
            ),
            WindowHour(
                time=datetime(2026, 4, 29, 12, 0),
                avg_wind_speed_kmh=11.0,
                avg_direction_deg=65.0,
                avg_precipitation_mm_per_hour=0.7,
            ),
        ],
    )

    channel.deliver("zurich_bise", [window])

    output = buffer.getvalue()
    assert "Precipitation: avg 0.4 mm/h, max 0.7 mm/h" in output
    assert "💧 Precip (mm/h)" in output
    assert "0.3" in output
    assert "0.7" in output