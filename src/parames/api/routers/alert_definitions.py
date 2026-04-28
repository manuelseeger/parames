from __future__ import annotations

from fastapi import APIRouter, HTTPException

from parames.api.deps import Repo
from parames.persistence.models import AlertDefinition

router = APIRouter(prefix="/alert-definitions", tags=["alert-definitions"])


@router.get("", response_model=list[AlertDefinition])
async def list_alert_definitions(repo: Repo, enabled: bool | None = None) -> list[AlertDefinition]:
    return await repo.list_alert_definitions(enabled_only=enabled is True)


@router.post("", response_model=AlertDefinition, status_code=201)
async def create_alert_definition(definition: AlertDefinition, repo: Repo) -> AlertDefinition:
    existing = await repo.get_alert_definition_by_name(definition.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Alert definition '{definition.name}' already exists")
    return await repo.create_alert_definition(definition)


@router.get("/{definition_id}", response_model=AlertDefinition)
async def get_alert_definition(definition_id: str, repo: Repo) -> AlertDefinition:
    doc = await repo.get_alert_definition(definition_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Alert definition not found")
    return doc


@router.put("/{definition_id}", response_model=AlertDefinition)
async def update_alert_definition(definition_id: str, definition: AlertDefinition, repo: Repo) -> AlertDefinition:
    existing = await repo.get_alert_definition(definition_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Alert definition not found")
    definition.id = existing.id
    definition.created_at = existing.created_at
    return await repo.update_alert_definition(definition)


@router.patch("/{definition_id}", response_model=AlertDefinition)
async def patch_alert_definition(definition_id: str, body: dict, repo: Repo) -> AlertDefinition:
    existing = await repo.get_alert_definition(definition_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Alert definition not found")
    for field in ("enabled", "description", "delivery", "suppress_duplicates"):
        if field in body:
            setattr(existing, field, body[field])
    return await repo.update_alert_definition(existing)


@router.delete("/{definition_id}", status_code=204)
async def delete_alert_definition(definition_id: str, repo: Repo) -> None:
    deleted = await repo.delete_alert_definition(definition_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert definition not found")
