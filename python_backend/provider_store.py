from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

from .config import STATE_DB_PATH
from .provider_models import ProviderProfile


class ProviderStore:
    """Small local SQLite repository for provider profiles and capability metadata."""

    def __init__(self, path: str | Path = STATE_DB_PATH) -> None:
        self._database = str(path)
        self.path = Path(path)
        self._lock = threading.RLock()
        self._memory_connection: sqlite3.Connection | None = None
        if self._database != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self._database, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    builtin INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(providers)").fetchall()}
            if "builtin" not in columns:
                connection.execute("ALTER TABLE providers ADD COLUMN builtin INTEGER NOT NULL DEFAULT 0")
            connection.commit()

    def list(self) -> list[ProviderProfile]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT payload FROM providers ORDER BY id").fetchall()
        return [ProviderProfile.model_validate(json.loads(row["payload"])) for row in rows]

    def get(self, provider_id: str) -> ProviderProfile | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if row is None:
            return None
        return ProviderProfile.model_validate(json.loads(row["payload"]))

    def upsert(self, profile: ProviderProfile) -> ProviderProfile:
        payload = json.dumps(profile.model_dump(), ensure_ascii=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO providers (id, payload, builtin) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, builtin = excluded.builtin, updated_at = CURRENT_TIMESTAMP",
                (profile.id, payload, int(profile.builtin)),
            )
            connection.commit()
        return profile

    def delete(self, provider_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM providers WHERE id = ? AND builtin = 0", (provider_id,))
            connection.commit()
        return cursor.rowcount > 0

    def seed(self, profiles: Iterable[ProviderProfile]) -> None:
        for profile in profiles:
            if self.get(profile.id) is None:
                self.upsert(profile)
