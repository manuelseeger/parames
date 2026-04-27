from __future__ import annotations

# Wind direction is meteorological "from" direction.
# Arrows show where the wind is BLOWING TO (opposite of the source direction).
COMPASS_ARROWS = [
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
V_BARS = "▁▂▃▄▅▆▇█"
COL_W = 6


def compass(deg: float) -> tuple[str, str]:
    deg = deg % 360
    for threshold, arrow, label in COMPASS_ARROWS:
        if deg < threshold:
            return arrow, label
    return "↓", "N"


def vbar(value: float, max_value: float) -> str:
    """Single-char vertical bar (▁–█) scaled to max_value."""
    if max_value <= 0 or value <= 0:
        return " "
    idx = min(round(value / max_value * 7), 7)
    return V_BARS[max(0, idx)]
