from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from parames.plugins.bise import BisePluginConfig
from parames.plugins.laminar import LaminarPluginConfig

PluginConfig = Annotated[
    Union[BisePluginConfig, LaminarPluginConfig],
    Field(discriminator="type"),
]
