from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from parames.api.auth import UserDependency, owner_scope, validate_delivery
from parames.api.deps import Repo
from parames.config import RuntimeSettings, load_app_config
from parames.persistence.models import AlertDefinition, User

router = APIRouter(prefix="/alert-definitions", tags=["alert-definitions"])
IMMUTABLE = {"id", "_id", "owner_id", "created_at", "updated_at"}
PATCHABLE = {"enabled", "description", "delivery", "suppress_duplicates"}


def parse_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(404, "Alert definition not found")
    return ObjectId(value)


def parse_definition(body: dict, owner_id, *, existing: AlertDefinition | None = None) -> AlertDefinition:
    if not isinstance(body, dict) or IMMUTABLE.intersection(body) or set(body) - set(AlertDefinition.model_fields):
        raise HTTPException(422, "Invalid definition fields")
    values = existing.model_dump() if existing else {}
    values.update(body)
    values["owner_id"] = owner_id
    try:
        return AlertDefinition.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc


async def check_delivery(definition: AlertDefinition, user: User, repo: Repo) -> None:
    owner = user
    if definition.owner_id != user.id:
        owner = await repo._engine.find_one(Model=User, query=User.id == definition.owner_id)
        if owner is None:
            raise HTTPException(422, "Alert owner not found")
    config = load_app_config(RuntimeSettings().config_path)
    validate_delivery(definition.delivery, owner, {n: c.type for n, c in config.delivery_channels.items()})


@router.get("", response_model=list[AlertDefinition])
async def list_alert_definitions(repo: Repo, user: UserDependency, enabled: bool | None = None) -> list[AlertDefinition]:
    return await repo.list_alert_definitions(enabled_only=enabled is True, owner_id=owner_scope(user))


@router.post("", response_model=AlertDefinition, status_code=201)
async def create_alert_definition(body: dict, repo: Repo, user: UserDependency) -> AlertDefinition:
    definition = parse_definition(body, user.id)
    await check_delivery(definition, user, repo)
    try:
        return await repo.create_alert_definition(definition)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Alert definition name already exists") from exc


@router.get("/{definition_id}", response_model=AlertDefinition)
async def get_alert_definition(definition_id: str, repo: Repo, user: UserDependency) -> AlertDefinition:
    doc = await repo.get_alert_definition(parse_id(definition_id), owner_id=owner_scope(user))
    if doc is None:
        raise HTTPException(404, "Alert definition not found")
    return doc


@router.put("/{definition_id}", response_model=AlertDefinition)
async def update_alert_definition(definition_id: str, body: dict, repo: Repo, user: UserDependency) -> AlertDefinition:
    existing = await get_alert_definition(definition_id, repo, user)
    definition = parse_definition(body, existing.owner_id, existing=existing)
    definition.id = existing.id
    definition.created_at = existing.created_at
    await check_delivery(definition, user, repo)
    try:
        return await repo.update_alert_definition(definition)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Alert definition name already exists") from exc
    except LookupError as exc:
        raise HTTPException(404, "Alert definition not found") from exc


@router.patch("/{definition_id}", response_model=AlertDefinition)
async def patch_alert_definition(definition_id: str, body: dict, repo: Repo, user: UserDependency) -> AlertDefinition:
    if not isinstance(body, dict) or set(body) - PATCHABLE:
        raise HTTPException(422, "Invalid patch fields")
    existing = await get_alert_definition(definition_id, repo, user)
    definition = parse_definition(body, existing.owner_id, existing=existing)
    definition.id = existing.id
    definition.created_at = existing.created_at
    await check_delivery(definition, user, repo)
    try:
        return await repo.update_alert_definition(definition)
    except LookupError as exc:
        raise HTTPException(404, "Alert definition not found") from exc


@router.delete("/{definition_id}", status_code=204)
async def delete_alert_definition(definition_id: str, repo: Repo, user: UserDependency) -> None:
    deleted = await repo.delete_alert_definition(parse_id(definition_id), owner_id=owner_scope(user))
    if not deleted:
        raise HTTPException(404, "Alert definition not found")
