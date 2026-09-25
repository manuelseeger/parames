from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from parames.api.deps import Repo
from parames.persistence.models import Session, User

COOKIE = "parames_session"
SESSION_AGE = 60 * 60 * 24 * 30
router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str = Field(min_length=8, max_length=1024)


class Identity(BaseModel):
    id: str
    email: str
    role: Literal["regular", "admin"]


def normalize_email(email: str) -> str:
    email = email.strip().casefold()
    parts = email.split("@")
    if (len(parts) != 2 or not parts[0] or "." not in parts[1] or
            parts[1].startswith(".") or parts[1].endswith(".") or
            len(email) > 254 or any(c.isspace() for c in email)):
        raise HTTPException(422, "Invalid email")
    return email


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, cost, salt, expected = stored.split("$")
        if algorithm != "scrypt" or cost != "16384":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


_TIMING_DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def identity(user: User) -> Identity:
    return Identity(id=str(user.id), email=user.email, role=user.role)


async def current_user(request: Request, repo: Repo) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Authentication required")
    session = await repo._engine.find_one(Model=Session, query=Session.token_digest == token_digest(token))
    if session is None:
        raise HTTPException(401, "Authentication required")
    expiry = session.expires_at
    if (expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry.astimezone(timezone.utc)) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Authentication required")
    user = await repo._engine.find_one(Model=User, query=User.id == session.user_id)
    if user is None:
        raise HTTPException(401, "Authentication required")
    return user


UserDependency = Annotated[User, Depends(current_user)]


async def admin_user(user: UserDependency) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin required")
    return user


AdminDependency = Annotated[User, Depends(admin_user)]


def owner_scope(user: User):
    return None if user.role == "admin" else user.id


def validate_delivery(delivery: list[str], user: User, channel_types: dict[str, str]) -> None:
    if any(name not in channel_types for name in delivery):
        raise HTTPException(422, "Unknown delivery channel")
    if user.role == "regular" and any(channel_types[name] != "console" for name in delivery):
        raise HTTPException(422, "Regular accounts can use only console delivery")


def set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=SESSION_AGE, httponly=True,
        secure=request.url.scheme == "https" or os.getenv("PARAMES_COOKIE_SECURE") == "1",
        samesite="lax", path="/api",
    )


async def issue_session(user: User, request: Request, response: Response, repo: Repo) -> Identity:
    token = secrets.token_urlsafe(32)
    await repo._engine.save(Session(
        token_digest=token_digest(token), user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=SESSION_AGE),
    ))
    set_session(response, request, token)
    return identity(user)


@router.post("/signup", response_model=Identity, status_code=201)
async def signup(body: Credentials, request: Request, response: Response, repo: Repo) -> Identity:
    user = User(email=normalize_email(body.email), password_hash=hash_password(body.password), role="regular")
    try:
        await repo._engine.save(user)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Email already registered") from exc
    return await issue_session(user, request, response, repo)


@router.post("/login", response_model=Identity)
async def login(body: Credentials, request: Request, response: Response, repo: Repo) -> Identity:
    email = normalize_email(body.email)
    user = await repo._engine.find_one(Model=User, query=User.email == email)
    if not verify_password(body.password, user.password_hash if user is not None else _TIMING_DUMMY_HASH) or user is None:
        raise HTTPException(401, "Invalid credentials")
    return await issue_session(user, request, response, repo)


@router.get("/me", response_model=Identity)
async def me(user: UserDependency) -> Identity:
    return identity(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, repo: Repo, user: UserDependency) -> None:
    token = request.cookies.get(COOKIE)
    await repo._engine.delete(Model=Session, query=Session.token_digest == token_digest(token))
    response.delete_cookie(COOKIE, path="/api")


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    allowed = os.getenv("PARAMES_ALLOWED_ORIGIN", "").rstrip("/")
    return origin.rstrip("/") in (f"{request.url.scheme}://{request.headers.get('host', '')}", allowed)
