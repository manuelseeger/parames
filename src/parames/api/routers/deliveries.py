from __future__ import annotations

from fastapi import APIRouter, HTTPException

from parames.api.deps import Repo
from parames.persistence.models import Delivery

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("", response_model=list[Delivery])
async def list_deliveries(repo: Repo, limit: int = 100) -> list[Delivery]:
    return await repo.list_deliveries(limit=limit)


@router.get("/{delivery_id}", response_model=Delivery)
async def get_delivery(delivery_id: str, repo: Repo) -> Delivery:
    doc = await repo.get_delivery(delivery_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return doc
