from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from parames.api.deps import Repo
from parames.api.auth import UserDependency, owner_scope
from parames.persistence.models import Detection

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=list[Detection])
async def list_detections(
    repo: Repo,
    user: UserDependency,
    limit: int = 100,
    is_backtest: bool | None = None,
) -> list[Detection]:
    return await repo.list_detections(limit=limit, is_backtest=is_backtest, owner_id=owner_scope(user))


@router.get("/{detection_id}", response_model=Detection)
async def get_detection(detection_id: str, repo: Repo, user: UserDependency) -> Detection:
    if not ObjectId.is_valid(detection_id):
        raise HTTPException(404, "Detection not found")
    doc = await repo.get_detection(detection_id, owner_id=owner_scope(user))
    if doc is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    return doc
