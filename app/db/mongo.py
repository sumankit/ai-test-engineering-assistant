"""
MongoDB Atlas Tool
---------------------
Single responsibility: persist and retrieve job state so nothing lives
only in a process's memory. Three collections, matching the assignment's
own suggested shape:

  uploads          {job_id, filename, storage_url, storage_backend, status, created_at, updated_at}
  results          {job_id, requirements, scenarios, test_cases, boundary_cases,
                     edge_cases, acceptance_criteria, traceability, coverage}
  execution_logs    {job_id, started_at, completed_at, duration_seconds, node_timings, errors}

Real backend: MongoDB Atlas via pymongo (a plain cluster connection
string in MONGODB_URI -- Atlas is just "MongoDB, hosted", there is no
Atlas-specific SDK).

Fallback: a local JSON-file store with the identical method signatures,
used only when MONGODB_URI is unset, for the same offline-demoability
reason as the Supabase tool. See docs/approach.md, decision D1.
"""
from __future__ import annotations
import json
import os
import threading
import logging
from datetime import datetime, timezone
from app.config import settings

_LOCAL_PATH = os.path.join(settings.LOCAL_STORAGE_DIR, "mongo_fallback.json")
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _LocalJSONBackend:
    """Drop-in stand-in for the three Mongo collections, same call shape."""

    def __init__(self):
        os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)
        if not os.path.exists(_LOCAL_PATH):
            self._write({"uploads": {}, "results": {}, "execution_logs": {}})

    def _read(self) -> dict:
        with open(_LOCAL_PATH, "r") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        with open(_LOCAL_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def upsert(self, collection: str, job_id: str, doc: dict) -> None:
        with _lock:
            data = self._read()
            data.setdefault(collection, {})
            existing = data[collection].get(job_id, {})
            existing.update(doc)
            data[collection][job_id] = existing
            self._write(data)

    def get(self, collection: str, job_id: str) -> dict | None:
        data = self._read()
        return data.get(collection, {}).get(job_id)

    def list_all(self, collection: str) -> list[dict]:
        data = self._read()
        return list(data.get(collection, {}).values())

    def delete(self, collection: str, job_id: str) -> None:
        with _lock:
            data = self._read()
            data.get(collection, {}).pop(job_id, None)
            self._write(data)


class _AtlasBackend:
    def __init__(self):
        import ssl
        from pymongo import MongoClient

        # Fix for Docker (python:3.11-slim / Debian Bookworm) where OpenSSL 3.x
        # defaults to SECLEVEL=2, causing "TLSV1_ALERT_INTERNAL_ERROR" when
        # connecting to MongoDB Atlas. We build an explicit SSL context at
        # SECLEVEL=1 (still enforces TLS 1.2+, just allows a wider cipher set)
        # and back it with the certifi CA bundle so Atlas's cert chain validates.
        try:
            import certifi
            ca_file = certifi.where()
        except ImportError:
            ca_file = None

        ssl_ctx = ssl.create_default_context(cafile=ca_file)
        ssl_ctx.set_ciphers("DEFAULT@SECLEVEL=1")

        from pymongo.errors import ConfigurationError
        self._client = None
        try:
            self._client = MongoClient(
                settings.MONGODB_URI,
                tls=True,
                tlsCAFile=ca_file,
                ssl_context=ssl_ctx,
            )
        except (ConfigurationError, TypeError):
            # Older pymongo versions may not accept ssl_context. Fall back to
            # creating the client with tlsCAFile only (still validates using
            # the certifi bundle). This is a best-effort fallback for
            # environments where passing a custom SSLContext is unsupported.
            self._client = MongoClient(
                settings.MONGODB_URI,
                tls=True,
                tlsCAFile=ca_file,
            )

        # Verify connectivity early — if the client cannot complete a
        # simple ping we treat Atlas as unavailable and raise so callers
        # (the outer tool) can fall back to the local JSON backend.
        try:
            # Short timeout for quick failure rather than blocking startup.
            self._client.admin.command('ping', serverSelectionTimeoutMS=5000)
        except Exception:
            # close the client if it partially initialized
            try:
                if self._client is not None:
                    self._client.close()
            except Exception:
                pass
            # re-raise to signal failure to the caller
            raise

        self._db = self._client[settings.MONGODB_DB]


    def upsert(self, collection: str, job_id: str, doc: dict) -> None:
        self._db[collection].update_one({"job_id": job_id}, {"$set": doc}, upsert=True)

    def get(self, collection: str, job_id: str) -> dict | None:
        result = self._db[collection].find_one({"job_id": job_id}, {"_id": 0})
        return result

    def list_all(self, collection: str) -> list[dict]:
        return list(self._db[collection].find({}, {"_id": 0}))

    def delete(self, collection: str, job_id: str) -> None:
        self._db[collection].delete_one({"job_id": job_id})


class MongoDBAtlasTool:
    def __init__(self):
        if settings.mongo_enabled:
            try:
                backend = _AtlasBackend()
            except Exception as exc:  # connectivity or TLS failure
                logging.warning("MongoDB Atlas unavailable, falling back to local JSON backend: %s", exc)
                backend = _LocalJSONBackend()
                self._backend_name = "local_json_fallback"
            else:
                self._backend_name = "mongodb_atlas"

            self._backend = backend
        else:
            self._backend = _LocalJSONBackend()
            self._backend_name = "local_json_fallback"

    @property
    def backend(self) -> str:
        return self._backend_name

    # ---- uploads collection ----
    def create_job(self, job_id: str, filename: str, storage_url: str, storage_backend: str) -> None:
        self._backend.upsert("uploads", job_id, {
            "job_id": job_id,
            "filename": filename,
            "storage_url": storage_url,
            "storage_backend": storage_backend,
            "status": "uploaded",
            "created_at": _now(),
            "updated_at": _now(),
        })

    def update_job_status(self, job_id: str, status: str) -> None:
        self._backend.upsert("uploads", job_id, {"status": status, "updated_at": _now()})

    def get_job(self, job_id: str) -> dict | None:
        return self._backend.get("uploads", job_id)

    def list_jobs(self) -> list[dict]:
        return self._backend.list_all("uploads")

    def delete_job(self, job_id: str) -> None:
        self._backend.delete("uploads", job_id)
        self._backend.delete("results", job_id)
        self._backend.delete("execution_logs", job_id)

    # ---- results collection ----
    def save_results(self, job_id: str, results: dict) -> None:
        now = _now()
        existing = self._backend.get("results", job_id)
        created_at = existing.get("created_at") if existing else now
        self._backend.upsert("results", job_id, {
            "job_id": job_id,
            **results,
            "created_at": created_at,
            "updated_at": now,
        })

    def get_results(self, job_id: str) -> dict | None:
        return self._backend.get("results", job_id)

    # ---- execution_logs collection ----
    def save_execution_log(self, job_id: str, log: dict) -> None:
        now = _now()
        existing = self._backend.get("execution_logs", job_id)
        created_at = existing.get("created_at") if existing else now
        self._backend.upsert("execution_logs", job_id, {
            "job_id": job_id,
            **log,
            "created_at": created_at,
            "updated_at": now,
        })

    def get_execution_log(self, job_id: str) -> dict | None:
        return self._backend.get("execution_logs", job_id)


mongodb_tool = MongoDBAtlasTool()
