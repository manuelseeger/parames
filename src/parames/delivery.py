from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from parames.domain import CandidateWindow, WindowHour

# Wind direction is meteorological "from" direction.
# Arrows show where the wind is BLOWING TO (opposite of the source direction).
_COMPASS_ARROWS = [
    (11.25,  "↓", "N"),    # from N  → blows S
    (33.75,  "↙", "NNE"),  # from NNE → blows SSW
    (56.25,  "↙", "NE"),   # from NE  → blows SW
    (78.75,  "←", "ENE"),  # from ENE → blows WSW
    (101.25, "←", "E"),    # from E   → blows W
    (123.75, "↖", "ESE"),  # from ESE → blows WNW
    (146.25, "↖", "SE"),   # from SE  → blows NW
    (168.75, "↑", "SSE"),  # from SSE → blows NNW
    (191.25, "↑", "S"),    # from S   → blows N
    (213.75, "↗", "SSW"),  # from SSW → blows NNE
    (236.25, "↗", "SW"),   # from SW  → blows NE
    (258.75, "→", "WSW"),  # from WSW → blows ENE
    (281.25, "→", "W"),    # from W   → blows E
    (303.75, "↘", "WNW"),  # from WNW → blows ESE
    (326.25, "↘", "NW"),   # from NW  → blows SE
    (348.75, "↓", "NNW"),  # from NNW → blows SSW
]
_V_BARS = "▁▂▃▄▅▆▇█"
_COL_W = 6


def _compass(deg: float) -> tuple[str, str]:
    deg = deg % 360
    for threshold, arrow, label in _COMPASS_ARROWS:
        if deg < threshold:
            return arrow, label
    return "↓", "N"


def _vbar(value: float, max_value: float) -> str:
    """Single-char vertical bar (▁–█) scaled to max_value."""
    if max_value <= 0 or value <= 0:
        return " "
    idx = min(round(value / max_value * 7), 7)
    return _V_BARS[max(0, idx)]


def _render_horizontal_charts(console: Console, hours: list[WindowHour]) -> None:
    if not hours:
        return

    max_speed = max(h.avg_wind_speed_kmh for h in hours)

    def speed_style(h: WindowHour) -> str:
        if not h.in_window:
            return "dim"
        return "bold green" if h.avg_wind_speed_kmh >= 40 else "bold yellow"

    time_row  = Text("  ")
    bar_row   = Text("  ")
    speed_row = Text("  ")
    arrow_row = Text("  ")
    label_row = Text("  ")
    precip_row = Text("  ")

    for h in hours:
        col = _COL_W
        sty = speed_style(h)
        time_sty = "bold" if h.in_window else "dim"
        dir_sty  = "bold cyan" if h.in_window else "dim"

        arrow, label = _compass(h.avg_direction_deg)
        time_row.append(f"{h.time:%H:%M}".ljust(col), style=time_sty)
        bar_row.append(_vbar(h.avg_wind_speed_kmh, max_speed).ljust(col), style=sty)
        speed_row.append(f"{h.avg_wind_speed_kmh:.0f}".ljust(col), style=sty)
        arrow_row.append(arrow.ljust(col), style=sty)
        label_row.append(label.ljust(col), style=dir_sty)
        precipitation = "-" if h.avg_precipitation_mm_per_hour is None else f"{h.avg_precipitation_mm_per_hour:.1f}"
        precip_row.append(precipitation.ljust(col), style=("bold blue" if h.in_window else "dim"))

    console.print("  [bold]💨 Speed  🧭 Direction  💧 Precip (mm/h)[/bold]")
    console.print(time_row)
    console.print(bar_row)
    console.print(speed_row)
    console.print(arrow_row)
    console.print(label_row)
    console.print(precip_row)


class DeliveryChannel(Protocol):
    def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        ...


class ConsoleChannel:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        if not windows:
            self._console.print(f"🌬️  No candidate NE/E wind windows found for [bold]{alert_name}[/bold] in the forecast horizon.")
            return

        self._console.print(Rule(f"🪂 Wind Alert Candidates — {alert_name}"))
        for window in windows:
            classification = window.classification.upper()
            score = window.score
            score_style = "bold green" if score >= 5 else "bold yellow"
            medal = "🟢" if score >= 5 else "🟡"
            self._console.print(f"{medal} [bold]{classification}[/bold]", style=score_style)
            self._console.print(
                f"  📅 {window.start:%a %Y-%m-%d %H:%M} – {window.end:%H:%M}  "
                f"⏱ {window.duration_hours}h  "
                f"⭐ Score: {score}/7"
            )
            self._console.print(
                f"  💨 avg {window.avg_wind_speed_kmh:.1f} km/h, "
                f"max {window.max_wind_speed_kmh:.1f} km/h"
            )
            self._console.print(f"  🧭 Direction: avg {window.avg_direction_deg:.0f}°")
            if window.bise_pressure_gradient_hpa is None:
                self._console.print("  🌡  Bise gradient: unavailable")
            else:
                self._console.print(
                    f"  🌡  Bise gradient: +{window.bise_pressure_gradient_hpa:.1f} hPa east-west"
                )
            self._console.print(
                "  💧 Precipitation: "
                + (
                    "unavailable"
                    if window.avg_precipitation_mm_per_hour is None
                    else f"avg {window.avg_precipitation_mm_per_hour:.1f} mm/h, max {window.max_precipitation_mm_per_hour:.1f} mm/h"
                )
            )
            if window.hours:
                self._console.print()
                _render_horizontal_charts(self._console, window.hours)
            self._console.print()

