from __future__ import annotations

from pydantic import Field
from pyodmongo import MainBaseModel


class LocationConfig(MainBaseModel):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
