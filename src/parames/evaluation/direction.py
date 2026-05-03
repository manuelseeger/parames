from __future__ import annotations

import math


def direction_in_range(direction: float, min_deg: float, max_deg: float) -> bool:
    if max_deg - min_deg >= 360:
        return True
    direction = direction % 360
    min_deg = min_deg % 360
    max_deg = max_deg % 360
    if min_deg <= max_deg:
        return min_deg <= direction <= max_deg
    return direction >= min_deg or direction <= max_deg


def angular_distance(first: float, second: float) -> float:
    delta = abs((first - second) % 360)
    return min(delta, 360 - delta)


def vector_average_direction(directions: list[float]) -> float:
    if not directions:
        raise ValueError("directions must not be empty")
    sin_sum = sum(math.sin(math.radians(d)) for d in directions)
    cos_sum = sum(math.cos(math.radians(d)) for d in directions)
    average = math.degrees(math.atan2(sin_sum, cos_sum))
    return (average + 360) % 360
