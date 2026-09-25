from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from pathlib import Path

from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from parames.api.auth import hash_password, verify_password
from parames.api.main import app
from parames.config import load_app_config
from parames.migrate_users import ADMIN_EMAIL, migrate_legacy
from parames.persistence.models import AlertDefinition, Session, User
from parames.persistence.repository import AlertRepository, build_engine
from parames.seed import _profile_to_definition
from parames.domain import CandidateWindow


class MemoryCollection:
    def __init__(self, docs=None):
        self.docs = docs if docs is not None else []
        self.indexes = {}

    async def create_index(self, keys, **kwargs):
        self.indexes[kwargs["name"]] = kwargs

    async def index_information(self):
        return self.indexes

    async def drop_index(self, name):
        del self.indexes[name]

    async def update_many(self, query, update):
        for doc in self.docs:
            if "owner_id" not in doc:
                doc.update(update["$set"])


class MemoryEngine:
    def __init__(self):
        self._db = {key: MemoryCollection() for key in ("users", "sessions", "alert_definitions", "detections", "runs")}

    def collection(self, model):
        return self._db[model._collection].docs

    async def save(self, obj, raw_query=None, upsert=True):
        if raw_query is not None:
            matched = await self.find_many(type(obj), raw_query=raw_query)
            if not matched:
                assert not upsert
                return type("Result", (), {"matched_count": 0})()
        if obj.id is None:
            obj.id = ObjectId()
        docs = self.collection(type(obj))
        if isinstance(obj, User) and any(d.email == obj.email and d.id != obj.id for d in docs):
            raise DuplicateKeyError("email")
        if isinstance(obj, AlertDefinition) and any(d.owner_id == obj.owner_id and d.name == obj.name and d.id != obj.id for d in docs):
            raise DuplicateKeyError("name")
        docs[:] = [d for d in docs if d.id != obj.id] + [obj]
        return type("Result", (), {"matched_count": len(matched) if raw_query is not None else 0})()

    async def find_one(self, Model, query=None, raw_query=None, **kwargs):
        matches = await self.find_many(Model, query=query, raw_query=raw_query)
        return matches[0] if matches else None

    async def find_many(self, Model, query=None, raw_query=None, **kwargs):
        if query is not None:
            return [obj for obj in self.collection(Model) if getattr(obj, "id" if query.path_str == "_id" else query.path_str) == query.value]
        return [obj for obj in self.collection(Model) if all(
            str(getattr(obj, "id" if key == "_id" else key)) == str(value) for key, value in (raw_query or {}).items()
        )]

    async def delete(self, Model, query=None, raw_query=None, **kwargs):
        docs = self.collection(Model)
        selected = await self.find_many(Model, query=query, raw_query=raw_query)
        docs[:] = [obj for obj in docs if obj not in selected]
        return type("Result", (), {"deleted_count": len(selected)})()


def test_http_isolation_and_auth(monkeypatch):
    engine = MemoryEngine()
    app.state.repo = AlertRepository(engine)
    origin = {"origin": "http://testserver"}
    definition = _profile_to_definition(load_app_config(Path("config/default.yaml")).alerts[0], ObjectId())
    body = {k: v for k, v in definition.model_dump(mode="json").items() if k not in {"id", "created_at", "updated_at", "owner_id"}}
    client = TestClient(app)
    assert client.post("/api/auth/signup", json={"email": "a@example.com", "password": "password123"}).status_code == 403
    assert client.post("/api/auth/signup", headers={"origin": "http://evil.example"}, json={"email": "a@example.com", "password": "password123"}).status_code == 403
    monkeypatch.setenv("PARAMES_ALLOWED_ORIGIN", "http://localhost:5173")
    assert client.post("/api/auth/signup", headers={"origin": "http://localhost:5173"}, json={"email": "not-an-email", "password": "password123"}).status_code == 422
    a = client.post("/api/auth/signup", headers=origin, json={"email": " A@Example.com ", "password": "password123"})
    assert a.status_code == 201, a.text
    assert a.json()["email"] == "a@example.com"
    assert "httponly" in a.headers["set-cookie"].lower()
    assert client.post("/api/auth/signup", headers=origin, json={"email": "a@example.com", "password": "password123"}).status_code == 409
    for bad in ({"owner_id": str(ObjectId())}, {"id": str(ObjectId())}, {"created_at": "2020-01-01T00:00:00Z"}):
        assert client.post("/api/alert-definitions", headers=origin, json=body | bad).status_code == 422
    created = client.post("/api/alert-definitions", headers=origin, json=body)
    assert created.status_code == 201, created.text
    doc_id = created.json()["id"]
    assert engine._db["alert_definitions"].docs[0].id == ObjectId(doc_id)
    assert engine._db["alert_definitions"].docs[0].owner_id == a.json()["id"]
    assert asyncio.run(engine.find_many(AlertDefinition, raw_query={"_id": ObjectId(doc_id), "owner_id": ObjectId(a.json()["id"])}))
    assert client.patch(f"/api/alert-definitions/{doc_id}", headers=origin, json={"owner_id": str(ObjectId())}).status_code == 422
    assert client.put(f"/api/alert-definitions/{doc_id}", headers=origin, json=body | {"id": str(ObjectId())}).status_code == 422
    assert client.patch(f"/api/alert-definitions/{doc_id}", headers=origin, json={"enabled": "not-a-bool"}).status_code == 422
    assert client.patch(f"/api/alert-definitions/{doc_id}", headers=origin, json={"enabled": False}).status_code == 200
    assert client.post("/api/alert-definitions", headers=origin, json=body | {"delivery": ["telegram"]}).status_code == 422
    assert client.get("/api/runs").status_code == 403
    client.post("/api/auth/logout", headers=origin)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/signup", headers=origin, json={"email": "b@example.com", "password": "password123", "role": "admin"}).status_code == 422
    b = client.post("/api/auth/signup", headers=origin, json={"email": "b@example.com", "password": "password123"})
    assert b.json()["role"] == "regular"
    assert client.get("/api/alert-definitions").json() == []
    assert client.get(f"/api/alert-definitions/{doc_id}").status_code == 404
    assert client.put(f"/api/alert-definitions/{doc_id}", headers=origin, json=body).status_code == 404
    assert client.delete(f"/api/alert-definitions/{doc_id}", headers=origin).status_code == 404
    assert client.post("/api/alert-definitions", headers=origin, json=body).status_code == 201
    owner_a = ObjectId(a.json()["id"])
    owner_b = ObjectId(b.json()["id"])
    window = CandidateWindow(
        alert_name="shared", start=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
        end=datetime(2026, 6, 1, 12, tzinfo=timezone.utc), duration_hours=3,
        avg_wind_speed_kmh=12, max_wind_speed_kmh=14, avg_direction_deg=60,
        avg_precipitation_mm_per_hour=0, max_precipitation_mm_per_hour=0,
        models=["icon_d2"], dry_filter_applied=False, score=50,
        classification="candidate", hours=[],
    )
    doc_a = asyncio.run(app.state.repo.upsert_detection(window, alert_definition_id=ObjectId(doc_id), owner_id=owner_a, run_id=ObjectId(), existing=None))
    doc_b = asyncio.run(app.state.repo.upsert_detection(window, alert_definition_id=ObjectId(), owner_id=owner_b, run_id=ObjectId(), existing=None))
    assert [d["id"] for d in client.get("/api/detections").json()] == [str(doc_b.id)]
    assert client.get(f"/api/detections/{doc_a.id}").status_code == 404
    assert client.post("/api/auth/login", headers=origin, json={"email": "a@example.com", "password": "password123"}).status_code == 200
    assert [d["id"] for d in client.get("/api/detections").json()] == [str(doc_a.id)]
    assert client.get("/api/alert-definitions").json()[0]["owner_id"] == a.json()["id"]
    assert client.post("/api/auth/login", headers=origin, json={"email": "a@example.com", "password": "wrongpass"}).status_code == 401
    asyncio.run(engine.save(User(email=ADMIN_EMAIL, password_hash=hash_password("adminpass"), role="admin")))
    assert client.post("/api/auth/login", headers=origin, json={"email": ADMIN_EMAIL, "password": "adminpass"}).json()["role"] == "admin"
    assert len(client.get("/api/alert-definitions").json()) == 2
    assert len(client.get("/api/detections").json()) == 2
    assert client.get("/api/runs").status_code == 200
    admin_update = client.patch(f"/api/alert-definitions/{doc_id}", headers=origin, json={"enabled": True})
    assert admin_update.status_code == 200
    assert admin_update.json()["owner_id"] == a.json()["id"]
    assert client.patch(f"/api/alert-definitions/{doc_id}", headers=origin, json={"delivery": ["telegram"]}).status_code == 422
    assert client.get(f"/api/alert-definitions/{doc_id}").json()["delivery"] == ["console"]
    assert client.post("/api/alert-definitions", headers=origin, json=body | {"delivery": ["telegram"]}).status_code == 201


def test_expired_cookie_is_rejected():
    engine = MemoryEngine()
    app.state.repo = AlertRepository(engine)
    client = TestClient(app)
    response = client.post(
        "/api/auth/signup", headers={"origin": "http://testserver"},
        json={"email": "expires@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 201
    session = engine.collection(Session)[0]
    session.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert client.get("/api/auth/me").status_code == 401


def test_update_rejects_record_deleted_after_lookup():
    engine = MemoryEngine()
    definition = _profile_to_definition(load_app_config(Path("config/default.yaml")).alerts[0], ObjectId())
    definition.id = ObjectId()
    with pytest.raises(LookupError, match="no longer exists"):
        asyncio.run(AlertRepository(engine).update_alert_definition(definition))


def test_detection_dedup_query_scopes_owner_and_definition():
    class CaptureEngine:
        def __init__(self):
            self.query = None

        async def find_one(self, Model, query):
            self.query = query
            return None

    engine = CaptureEngine()
    window = CandidateWindow(
        alert_name="shared", start=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
        end=datetime(2026, 6, 1, 12, tzinfo=timezone.utc), duration_hours=3,
        avg_wind_speed_kmh=12, max_wind_speed_kmh=14, avg_direction_deg=60,
        avg_precipitation_mm_per_hour=0, max_precipitation_mm_per_hour=0,
        models=["icon_d2"], dry_filter_applied=False, score=50,
        classification="candidate", hours=[],
    )
    definition_id, owner_id = ObjectId(), ObjectId()
    asyncio.run(AlertRepository(engine).find_matching_detection(definition_id, owner_id, window))
    query = build_engine("mongodb://localhost:27017/parames")._query(query=engine.query, raw_query=None)
    def clauses(node):
        return [entry for item in node.get("$and", [node]) for entry in clauses(item)] if "$and" in node else [node]

    assert {"alert_definition_id": {"$eq": definition_id}} in clauses(query)
    assert {"owner_id": {"$eq": owner_id}} in clauses(query)
    assert {"start": {"$lt": window.end}} in clauses(query)
    assert {"end": {"$gt": window.start}} in clauses(query)


def test_migration_preserves_history_and_retries():
    asyncio.run(check_migration())


async def check_migration():
    engine = MemoryEngine()
    legacy_id, detection_id = ObjectId(), ObjectId()
    engine._db["alert_definitions"].docs.append({"_id": legacy_id, "name": "old"})
    engine._db["detections"].docs.append({"_id": detection_id, "alert_definition_id": legacy_id})
    another_owner = ObjectId()
    engine._db["detections"].docs.append({"_id": ObjectId(), "owner_id": another_owner})
    engine._db["alert_definitions"].indexes["alert_definition_name_unique"] = {"unique": True}
    await migrate_legacy(engine, "testpassword")
    user = engine._db["users"].docs[0]
    assert user.email == ADMIN_EMAIL and user.role == "admin"
    assert verify_password("testpassword", user.password_hash)
    assert not verify_password("otherpassword", user.password_hash)
    assert engine._db["detections"].docs[0] == {"_id": detection_id, "alert_definition_id": legacy_id, "owner_id": user.id}
    assert engine._db["detections"].docs[1]["owner_id"] == another_owner
    assert engine._db["alert_definitions"].docs[0] == {"_id": legacy_id, "name": "old", "owner_id": user.id}
    assert "alert_definition_name_unique" not in engine._db["alert_definitions"].indexes
    await migrate_legacy(engine, "testpassword")
    assert len(engine._db["users"].docs) == 1
    engine2 = MemoryEngine()
    await engine2.save(User(email=ADMIN_EMAIL, password_hash="irrelevant", role="regular"))
    with pytest.raises(ValueError, match="not created by this migration"):
        await migrate_legacy(engine2, "testpassword")
    engine3 = MemoryEngine()
    await engine3.save(User(email=ADMIN_EMAIL, password_hash="irrelevant", role="admin"))
    with pytest.raises(ValueError, match="not created by this migration"):
        await migrate_legacy(engine3, "testpassword")
