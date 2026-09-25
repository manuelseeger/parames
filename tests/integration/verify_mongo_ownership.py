"""Check ownership and indexes in the MongoDB selected by PARAMES_MONGO_URI."""

import os

from bson import ObjectId
from pymongo import MongoClient

from parames.persistence.models import ADMIN_EMAIL


def main() -> None:
    uri = os.environ["PARAMES_MONGO_URI"]
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client.get_default_database()
    admin = db.users.find_one({"email": ADMIN_EMAIL})
    assert admin is not None and admin["role"] == "admin"
    assert db.alert_definitions.count_documents({"owner_id": admin["_id"]}) > 0
    for collection in ("alert_definitions", "detections"):
        assert db[collection].count_documents({"owner_id": {"$exists": False}}) == 0
        assert all(isinstance(doc["owner_id"], ObjectId) for doc in db[collection].find({}, {"owner_id": 1}))
    indexes = db.alert_definitions.index_information()
    assert indexes["owner_name_unique"]["unique"] is True
    assert "alert_definition_name_unique" not in indexes
    print("Admin ownership and MongoDB indexes verified")


if __name__ == "__main__":
    main()
