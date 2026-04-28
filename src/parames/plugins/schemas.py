from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from parames.plugins.bise import BisePluginConfig

PluginConfig = Annotated[
    Union[BisePluginConfig],
    Field(discriminator="type"),
]
