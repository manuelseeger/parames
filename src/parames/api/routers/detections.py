from __future__ import annotations

from fastapi import APIRouter, HTTPException

from parames.api.deps import Repo
from parames.persistence.models import Detection

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=list[Detection])
async def list_detections(repo: Repo, limit: int = 100) -> list[Detection]:
    return await repo.list_detections(limit=limit)


@router.get("/{detection_id}", response_model=Detection)
async def get_detection(detection_id: str, repo: Repo) -> Detection:
    doc = await repo.get_detection(detection_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    return doc
