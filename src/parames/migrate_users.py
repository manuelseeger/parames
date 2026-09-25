from __future__ import annotations

import asyncio
import os

import click
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from parames.api.auth import hash_password
from parames.config import RuntimeSettings
from parames.persistence import build_engine
from parames.persistence.models import ADMIN_EMAIL, User


async def migrate_legacy(engine, password: str) -> None:
    db = engine._db
    await db["users"].create_index("email", unique=True, name="user_email_unique")
    existing = await engine.find_one(Model=User, query=User.email == ADMIN_EMAIL)
    if existing is not None and (existing.role != "admin" or not existing.migration_owner):
        raise ValueError("Admin email belongs to an account not created by this migration")
    if existing is None:
        user = User(email=ADMIN_EMAIL, password_hash=hash_password(password), role="admin", migration_owner=True)
        try:
            await engine.save(user)
        except DuplicateKeyError as exc:
            raise ValueError("Admin account was created concurrently; retry migration") from exc
    else:
        user = existing

    for collection in ("alert_definitions", "detections"):
        await db[collection].update_many({"owner_id": {"$exists": False}}, {"$set": {"owner_id": user.id}})

    await db["alert_definitions"].create_index(
        [("owner_id", ASCENDING), ("name", ASCENDING)], unique=True, name="owner_name_unique"
    )
    indexes = await db["alert_definitions"].index_information()
    if "alert_definition_name_unique" in indexes:
        await db["alert_definitions"].drop_index("alert_definition_name_unique")
    await db["detections"].create_index([("owner_id", ASCENDING), ("start", -1)], name="owner_start")
    await db["sessions"].create_index("token_digest", unique=True, name="session_digest_unique")
    await db["sessions"].create_index("expires_at", expireAfterSeconds=0, name="session_expiry")


@click.command("migrate-users")
def migrate_users_command() -> None:
    """Assign legacy records to the admin account and install owner indexes."""
    password = os.getenv("PARAMES_ADMIN_PASSWORD", "")
    if len(password) < 8:
        raise click.ClickException("Set PARAMES_ADMIN_PASSWORD to at least 8 characters")
    try:
        asyncio.run(migrate_legacy(build_engine(RuntimeSettings().mongo_uri), password))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("User migration complete.")
