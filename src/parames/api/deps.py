from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from parames.persistence import AlertRepository


def get_repo(request: Request) -> AlertRepository:
    return request.app.state.repo


Repo = Annotated[AlertRepository, Depends(get_repo)]
