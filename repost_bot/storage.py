from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from repost_bot.contracts import AuditEvent, DeliveryStatus, DestinationStatus, Platform


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class SqliteRepository:
    database_path: str

    def __post_init__(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS destinations (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_ref TEXT
                );

                CREATE TABLE IF NOT EXISTS source_posts (
                    id TEXT PRIMARY KEY,
                    source_platform TEXT NOT NULL,
                    source_channel_id TEXT NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    raw_payload TEXT NOT NULL,
                    normalized_payload TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    published_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_channel_id, source_message_id)
                );

                CREATE TABLE IF NOT EXISTS delivery_jobs (
                    id TEXT PRIMARY KEY,
                    source_post_id TEXT NOT NULL,
                    destination_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_post_id, destination_id)
                );

                CREATE TABLE IF NOT EXISTS published_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_job_id TEXT NOT NULL UNIQUE,
                    remote_post_id TEXT NOT NULL,
                    remote_permalink TEXT,
                    published_at TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def seed_default_destinations(self, threads_enabled: bool = False) -> None:
        destinations = [
            ("vk-destination", Platform.VK.value, "vk-target", DestinationStatus.ACTIVE.value, "vk-config"),
            ("ok-destination", Platform.OK.value, "ok-target", DestinationStatus.ACTIVE.value, "ok-config"),
            (
                "threads-destination",
                Platform.THREADS.value,
                "threads-target",
                DestinationStatus.ACTIVE.value if threads_enabled else DestinationStatus.DISABLED.value,
                "threads-config",
            ),
        ]
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO destinations (id, platform, target_id, status, config_ref)
                VALUES (?, ?, ?, ?, ?)
                """,
                destinations,
            )

    def source_post_exists(self, source_channel_id: str, source_message_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM source_posts
                WHERE source_channel_id = ? AND source_message_id = ?
                """,
                (source_channel_id, source_message_id),
            ).fetchone()
        return row is not None

    def create_source_post(
        self,
        source_post_id: str,
        source_platform: str,
        source_channel_id: str,
        source_message_id: int,
        raw_payload: dict,
        normalized_payload: dict,
        content_hash: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_posts (
                    id, source_platform, source_channel_id, source_message_id,
                    raw_payload, normalized_payload, content_hash, published_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_post_id,
                    source_platform,
                    source_channel_id,
                    source_message_id,
                    json.dumps(raw_payload, ensure_ascii=False),
                    json.dumps(normalized_payload, ensure_ascii=False),
                    content_hash,
                    None,
                    _utcnow(),
                ),
            )

    def list_active_destination_ids(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM destinations
                WHERE status = ?
                ORDER BY id
                """,
                (DestinationStatus.ACTIVE.value,),
            ).fetchall()
        return [row["id"] for row in rows]

    def create_delivery_job(self, source_post_id: str, destination_id: str) -> str:
        job_id = f"{source_post_id}:{destination_id}"
        now = _utcnow()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO delivery_jobs (
                    id, source_post_id, destination_id, status, attempt_count, next_attempt_at,
                    last_error_code, last_error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    source_post_id,
                    destination_id,
                    DeliveryStatus.PENDING.value,
                    now,
                    now,
                ),
            )
        return job_id

    def list_delivery_jobs_for_source_post(self, source_post_id: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_post_id, destination_id, status
                FROM delivery_jobs
                WHERE source_post_id = ?
                ORDER BY destination_id
                """,
                (source_post_id,),
            ).fetchall()
        return rows

    def count_rows(self, table: str) -> int:
        with self.connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def save_audit_event(self, event: AuditEvent) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (actor, action, target_type, target_id, result, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.actor,
                    event.action,
                    event.target_type,
                    event.target_id,
                    event.result,
                    event.created_at.isoformat(timespec="seconds") if event.created_at else _utcnow(),
                ),
            )

