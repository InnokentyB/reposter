from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from repost_bot.contracts import (
    AuditEvent,
    CanonicalPost,
    DeliveryJob,
    DeliveryStatus,
    DestinationStatus,
    Platform,
)


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class SqliteRepository:
    database_path: str
    _shared_connection: sqlite3.Connection | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._shared_connection = sqlite3.connect(self.database_path)
            self._shared_connection.row_factory = sqlite3.Row
        self._initialize()

    @contextmanager
    def connect(self):
        connection = self._shared_connection
        owns_connection = connection is None
        if connection is None:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            if owns_connection:
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

    def get_destination_status(self, destination_id: str) -> str:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM destinations
                WHERE id = ?
                """,
                (destination_id,),
            ).fetchone()
        if row is None:
            raise KeyError(destination_id)
        return str(row["status"])

    def get_source_post(self, source_post_id: str) -> CanonicalPost:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, source_platform, source_channel_id, source_message_id,
                       raw_payload, normalized_payload, content_hash, published_at
                FROM source_posts
                WHERE id = ?
                """,
                (source_post_id,),
            ).fetchone()
        if row is None:
            raise KeyError(source_post_id)
        published_at = row["published_at"]
        return CanonicalPost(
            source_platform=Platform(row["source_platform"]),
            source_channel_id=row["source_channel_id"],
            source_message_id=row["source_message_id"],
            raw_payload=json.loads(row["raw_payload"]),
            normalized_payload=json.loads(row["normalized_payload"]),
            content_hash=row["content_hash"],
            published_at=datetime.fromisoformat(published_at) if published_at else None,
        )

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

    def list_due_delivery_jobs(
        self,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[DeliveryJob]:
        reference_time = (now or datetime.utcnow()).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_post_id, destination_id, status, attempt_count,
                       next_attempt_at, last_error_code, last_error_message
                FROM delivery_jobs
                WHERE status = ?
                   OR (status = ? AND next_attempt_at IS NOT NULL AND next_attempt_at <= ?)
                ORDER BY created_at, destination_id
                LIMIT ?
                """,
                (
                    DeliveryStatus.PENDING.value,
                    DeliveryStatus.RETRY_SCHEDULED.value,
                    reference_time,
                    limit,
                ),
            ).fetchall()
        return [self._row_to_delivery_job(row) for row in rows]

    def get_delivery_job(self, job_id: str) -> DeliveryJob:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, source_post_id, destination_id, status, attempt_count,
                       next_attempt_at, last_error_code, last_error_message
                FROM delivery_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row_to_delivery_job(row)

    def update_delivery_job(self, job: DeliveryJob) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE delivery_jobs
                SET status = ?, attempt_count = ?, next_attempt_at = ?,
                    last_error_code = ?, last_error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    job.status.value,
                    job.attempt_count,
                    job.next_attempt_at.isoformat(timespec="seconds") if job.next_attempt_at else None,
                    job.last_error_code,
                    job.last_error_message,
                    _utcnow(),
                    job.id,
                ),
            )

    def mark_delivery_job_for_retry(
        self,
        job_id: str,
        attempt_count: int,
        next_attempt_at: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        job = self.get_delivery_job(job_id)
        job.status = DeliveryStatus.RETRY_SCHEDULED
        job.attempt_count = attempt_count
        job.next_attempt_at = next_attempt_at
        job.last_error_code = error_code
        job.last_error_message = error_message
        self.update_delivery_job(job)

    def save_published_post(
        self,
        delivery_job_id: str,
        remote_post_id: str,
        remote_permalink: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO published_posts (
                    delivery_job_id, remote_post_id, remote_permalink, published_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    delivery_job_id,
                    remote_post_id,
                    remote_permalink,
                    _utcnow(),
                ),
            )

    def get_published_post(self, delivery_job_id: str) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT delivery_job_id, remote_post_id, remote_permalink, published_at
                FROM published_posts
                WHERE delivery_job_id = ?
                """,
                (delivery_job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(delivery_job_id)
        return row

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

    def get_delivery_status_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM delivery_jobs
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}

    def database_is_healthy(self) -> bool:
        try:
            with self.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def get_queue_depth(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM delivery_jobs
                WHERE status IN (?, ?)
                """,
                (
                    DeliveryStatus.PENDING.value,
                    DeliveryStatus.RETRY_SCHEDULED.value,
                ),
            ).fetchone()
        return int(row["count"])

    def count_due_retry_jobs(self) -> int:
        reference_time = datetime.utcnow().isoformat(timespec="seconds")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM delivery_jobs
                WHERE status = ? AND next_attempt_at IS NOT NULL AND next_attempt_at <= ?
                """,
                (
                    DeliveryStatus.RETRY_SCHEDULED.value,
                    reference_time,
                ),
            ).fetchone()
        return int(row["count"])

    def list_stuck_delivery_jobs(self, limit: int = 20) -> list[sqlite3.Row]:
        reference_time = datetime.utcnow().isoformat(timespec="seconds")
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, source_post_id, destination_id, status, attempt_count,
                       next_attempt_at, last_error_code, last_error_message
                FROM delivery_jobs
                WHERE status = ?
                   OR (status = ? AND next_attempt_at IS NOT NULL AND next_attempt_at <= ?)
                ORDER BY updated_at DESC, id
                LIMIT ?
                """,
                (
                    DeliveryStatus.FAILED.value,
                    DeliveryStatus.RETRY_SCHEDULED.value,
                    reference_time,
                    limit,
                ),
            ).fetchall()

    def list_recent_delivery_errors(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, source_post_id, destination_id, status, last_error_code, last_error_message
                FROM delivery_jobs
                WHERE last_error_code IS NOT NULL OR last_error_message IS NOT NULL
                ORDER BY updated_at DESC, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def list_manual_review_jobs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, source_post_id, destination_id, status, attempt_count,
                       last_error_code, last_error_message, updated_at
                FROM delivery_jobs
                WHERE status = ?
                ORDER BY updated_at DESC, id
                LIMIT ?
                """,
                (
                    DeliveryStatus.MANUAL_REVIEW_REQUIRED.value,
                    limit,
                ),
            ).fetchall()

    def reset_delivery_job_for_manual_retry(self, job_id: str) -> DeliveryJob:
        job = self.get_delivery_job(job_id)
        job.status = DeliveryStatus.PENDING
        job.attempt_count = 0
        job.next_attempt_at = None
        job.last_error_code = None
        job.last_error_message = None
        self.update_delivery_job(job)
        return job

    def _row_to_delivery_job(self, row: sqlite3.Row) -> DeliveryJob:
        next_attempt_at = row["next_attempt_at"]
        return DeliveryJob(
            id=row["id"],
            source_post_id=row["source_post_id"],
            destination_id=row["destination_id"],
            status=DeliveryStatus(row["status"]),
            attempt_count=row["attempt_count"],
            next_attempt_at=datetime.fromisoformat(next_attempt_at) if next_attempt_at else None,
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
        )
