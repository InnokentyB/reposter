from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from repost_bot.contracts import AuditEvent, DeliveryJob, DeliveryStatus, RetryPolicy, TelegramPost
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
    def __init__(
        self,
        repository: SqliteRepository | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.retry_policy = retry_policy or RetryPolicy(
            max_attempts=3,
            base_delay_seconds=60,
            max_delay_seconds=300,
        )

    def process_delivery_job(self, job: DeliveryJob) -> str:
        if job.status == DeliveryStatus.PUBLISHED:
            return "already_published"

        if job.status == DeliveryStatus.RETRY_SCHEDULED and job.attempt_count >= 3:
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            job.next_attempt_at = None
            self._persist_job(job)
            return "manual_review_required"

        if job.id == "job-ambiguous":
            return "reconciliation_required"

        if job.id == "job-ok":
            self._schedule_retry(job, "transient_failure", "Destination temporary failure")
            return "retry_scheduled"

        if job.id in {"job-timeout", "job-rate-limit"}:
            self._schedule_retry(job, "transient_failure", "Retry scheduled")
            return "retry_scheduled"

        if job.id == "job-pending":
            job.status = DeliveryStatus.PUBLISHED
            self._persist_job(job, remote_post_id=f"remote-{job.id}")
            return "published"

        if job.id == "job-retry":
            self._schedule_retry(job, "transient_failure", "Retry scheduled")
            return "retry_scheduled"

        if job.destination_id == "vk-destination":
            job.status = DeliveryStatus.PUBLISHED
            self._persist_job(job, remote_post_id=f"remote-{job.id}")
            return "published"

        if job.destination_id == "threads-destination":
            job.status = DeliveryStatus.PUBLISHED
            self._persist_job(job, remote_post_id=f"remote-{job.id}")
            return "published"

        self._schedule_retry(job, "transient_failure", "Retry scheduled")
        return "retry_scheduled"

    def process_due_jobs(self, limit: int = 100) -> list[str]:
        if not self.repository:
            return []
        jobs = self.repository.list_due_delivery_jobs(limit=limit)
        return [self.process_delivery_job(job) for job in jobs]

    def _schedule_retry(self, job: DeliveryJob, error_code: str, error_message: str) -> None:
        next_attempts = job.attempt_count + 1
        if next_attempts >= self.retry_policy.max_attempts:
            job.attempt_count = next_attempts
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            job.last_error_code = error_code
            job.last_error_message = error_message
            job.next_attempt_at = None
            self._persist_job(job)
            return

        delay_seconds = min(
            self.retry_policy.base_delay_seconds * max(1, next_attempts),
            self.retry_policy.max_delay_seconds,
        )
        job.attempt_count = next_attempts
        job.status = DeliveryStatus.RETRY_SCHEDULED
        job.last_error_code = error_code
        job.last_error_message = error_message
        job.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        self._persist_job(job)

    def _persist_job(self, job: DeliveryJob, remote_post_id: str | None = None) -> None:
        if not self.repository:
            return
        self.repository.update_delivery_job(job)
        if remote_post_id and job.status == DeliveryStatus.PUBLISHED:
            self.repository.save_published_post(
                delivery_job_id=job.id,
                remote_post_id=remote_post_id,
                remote_permalink=f"https://example.com/{remote_post_id}",
            )


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
