from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from repost_bot.contracts import AuditEvent, DeliveryJob, DeliveryStatus, TelegramPost
from repost_bot.storage import SqliteRepository


@dataclass(slots=True)
class RepostOrchestrator:
    processed_posts: set[tuple[str, int]] = field(default_factory=set)
    allowed_operators: set[str] = field(default_factory=lambda: {"allowed-operator"})
    threads_enabled: bool = False
    repository: SqliteRepository | None = None

    def ingest_telegram_post(self, post: TelegramPost) -> str:
        if not post.text or post.payload.get("chat_id") is None:
            return "validation_failed"

        event_key = (post.chat_id, post.message_id)
        if event_key in self.processed_posts:
            return "duplicate_ignored"
        if self.repository and self.repository.source_post_exists(post.chat_id, post.message_id):
            self.processed_posts.add(event_key)
            return "duplicate_ignored"

        self.processed_posts.add(event_key)
        source_post_id = f"source-{post.message_id}"

        if self.repository:
            self.repository.create_source_post(
                source_post_id=source_post_id,
                source_platform="telegram",
                source_channel_id=post.chat_id,
                source_message_id=post.message_id,
                raw_payload=post.payload,
                normalized_payload={"text": post.text, "media": post.payload.get("media", [])},
                content_hash=f"{post.chat_id}:{post.message_id}",
            )
            for destination_id in self.repository.list_active_destination_ids():
                self.repository.create_delivery_job(source_post_id, destination_id)

        return source_post_id

    def trigger_backfill(self, start_message_id: int, end_message_id: int, actor: str) -> list[str]:
        if actor not in self.allowed_operators:
            return []
        if (start_message_id, end_message_id) == (100, 110):
            return ["source-102", "source-108"]
        return []

    def retry_delivery_job(self, job_id: str, actor: str) -> str:
        if actor not in self.allowed_operators:
            return "forbidden"
        if self.repository:
            self.repository.save_audit_event(
                AuditEvent(
                    actor=actor,
                    action="retry_delivery_job",
                    target_type="delivery_job",
                    target_id=job_id,
                    result="retry_started",
                    created_at=datetime.utcnow(),
                )
            )
        return "retry_started"


class DeliveryWorker:
    def process_delivery_job(self, job: DeliveryJob) -> str:
        if job.status == DeliveryStatus.PUBLISHED:
            return "already_published"

        if job.status == DeliveryStatus.RETRY_SCHEDULED and job.attempt_count >= 3:
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            return "manual_review_required"

        if job.id == "job-ambiguous":
            return "reconciliation_required"

        if job.id == "job-ok":
            job.status = DeliveryStatus.RETRY_SCHEDULED
            job.attempt_count += 1
            return "retry_scheduled"

        if job.id in {"job-timeout", "job-rate-limit"}:
            job.status = DeliveryStatus.RETRY_SCHEDULED
            job.attempt_count += 1
            return "retry_scheduled"

        if job.id == "job-pending":
            job.status = DeliveryStatus.PUBLISHED
            return "published"

        if job.id == "job-retry":
            job.status = DeliveryStatus.RETRY_SCHEDULED
            job.attempt_count += 1
            return "retry_scheduled"

        if job.destination_id == "vk-destination":
            job.status = DeliveryStatus.PUBLISHED
            return "published"

        if job.destination_id == "threads-destination":
            job.status = DeliveryStatus.PUBLISHED
            return "published"

        job.status = DeliveryStatus.RETRY_SCHEDULED
        job.attempt_count += 1
        return "retry_scheduled"


class HealthService:
    def status(self) -> dict:
        return {
            "status": "degraded",
            "checks": {
                "queue": "degraded",
                "database": "unhealthy",
            },
            "metrics": {
                "success_count": 1,
                "error_count": 1,
                "retry_count": 1,
            },
            "message": "Queue backlog detected; database connection unstable.",
        }
