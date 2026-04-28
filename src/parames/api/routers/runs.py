from __future__ import annotations

from fastapi import APIRouter, HTTPException

from parames.api.deps import Repo
from parames.persistence.models import Run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[Run])
async def list_runs(repo: Repo, limit: int = 50) -> list[Run]:
    return await repo.list_runs(limit=limit)


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str, repo: Repo) -> Run:
    doc = await repo.get_run(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return doc
