from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SECRET_REF = "$secret"
ENV_REF_PREFIX = "$env:"

# Fields stored in the secrets DB instead of config.yaml when using the web UI.
SECRET_FIELDS = frozenset({
    "password",
    "token_secret",
    "api_key",
    "auth_password",
    "priv_password",
})


class SecretsStore:
    """SQLite-backed store for credentials referenced from config.yaml."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS secrets (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    def get(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM secrets WHERE key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO secrets (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM secrets WHERE key = ?", (key,))

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def list_keys(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key FROM secrets ORDER BY key").fetchall()
        return [row[0] for row in rows]


def device_secret_key(device_name: str, field: str) -> str:
    return f"device.{device_name}.{field}"


def smtp_secret_key(field: str = "password") -> str:
    return f"smtp.{field}"


def snmp_v3_secret_key(field: str) -> str:
    return f"snmp.v3.{field}"


def auth_secret_key(field: str = "api_key") -> str:
    return f"auth.{field}"


def resolve_secret_value(raw: str | None, key: str, store: SecretsStore | None) -> str | None:
    if raw is None:
        if store and store.has(key):
            return store.get(key)
        return None
    if raw == SECRET_REF:
        if store is None:
            return None
        return store.get(key)
    if isinstance(raw, str) and raw.startswith(ENV_REF_PREFIX):
        env_name = raw[len(ENV_REF_PREFIX) :]
        return os.environ.get(env_name)
    return raw


def is_secret_reference(value: str | None) -> bool:
    if value is None:
        return False
    return value == SECRET_REF or value.startswith(ENV_REF_PREFIX)


_MASK = "********"
_ENV_PATTERN = re.compile(r"^\$env:[A-Za-z_][A-Za-z0-9_]*$")


def mask_value(value: str | None) -> str:
    if value is None or value == "":
        return ""
    if value == SECRET_REF or _ENV_PATTERN.match(value):
        return _MASK
    return _MASK
