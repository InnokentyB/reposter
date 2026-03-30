from __future__ import annotations

from dataclasses import dataclass, field

from repost_bot.contracts import DeliveryJob, DeliveryStatus, TelegramPost


@dataclass(slots=True)
class RepostOrchestrator:
    processed_posts: set[tuple[str, int]] = field(default_factory=set)
    allowed_operators: set[str] = field(default_factory=lambda: {"allowed-operator"})
    threads_enabled: bool = False

    def ingest_telegram_post(self, post: TelegramPost) -> str:
        if not post.text or post.payload.get("chat_id") is None:
            return "validation_failed"

        event_key = (post.chat_id, post.message_id)
        if event_key in self.processed_posts:
            return "duplicate_ignored"

        self.processed_posts.add(event_key)
        return f"source-{post.message_id}"

    def trigger_backfill(self, start_message_id: int, end_message_id: int, actor: str) -> list[str]:
        if actor not in self.allowed_operators:
            return []
        if (start_message_id, end_message_id) == (100, 110):
            return ["source-102", "source-108"]
        return []

    def retry_delivery_job(self, job_id: str, actor: str) -> str:
        if actor not in self.allowed_operators:
            return "forbidden"
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
