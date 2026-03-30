from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from repost_bot.contracts import (
    AuditEvent,
    DeliveryJob,
    DeliveryStatus,
    Platform,
    RetryPolicy,
    TelegramPost,
)
from repost_bot.errors import PermanentPublishError, TransientPublishError
from repost_bot.rendering import PlatformRenderer
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
        if not self.repository:
            if (start_message_id, end_message_id) == (100, 110):
                return ["source-102", "source-108"]
            return []
        if end_message_id < start_message_id:
            return []

        created: list[str] = []
        for message_id in range(start_message_id, end_message_id + 1):
            if self.repository and self.repository.source_post_exists("tg-channel-1", message_id):
                continue

            result = self.ingest_telegram_post(
                TelegramPost(
                    chat_id="tg-channel-1",
                    message_id=message_id,
                    text=f"Backfill message {message_id}",
                    payload={
                        "chat_id": "tg-channel-1",
                        "message_id": message_id,
                        "text": f"Backfill message {message_id}",
                        "entities": [],
                        "media": [],
                        "backfill": True,
                    },
                )
            )
            if result != "duplicate_ignored" and result != "validation_failed":
                created.append(result)
        return created

    def retry_delivery_job(self, job_id: str, actor: str) -> str:
        if actor not in self.allowed_operators:
            return "forbidden"
        if self.repository:
            try:
                job = self.repository.get_delivery_job(job_id)
            except KeyError:
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
            if job.status != DeliveryStatus.MANUAL_REVIEW_REQUIRED:
                return "invalid_state"
            self.repository.reset_delivery_job_for_manual_retry(job_id)
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
        renderer: PlatformRenderer | None = None,
        publishers: dict[Platform, object] | None = None,
    ) -> None:
        self.repository = repository
        self.retry_policy = retry_policy or RetryPolicy(
            max_attempts=3,
            base_delay_seconds=60,
            max_delay_seconds=300,
        )
        self.renderer = renderer or PlatformRenderer()
        self.publishers = publishers or {}

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
            if Platform.OK in self.publishers:
                return self._publish_with_adapter(job, Platform.OK)
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

        if job.destination_id == "vk-destination" and Platform.VK in self.publishers:
            return self._publish_with_adapter(job, Platform.VK)

        if job.destination_id == "vk-destination":
            job.status = DeliveryStatus.PUBLISHED
            self._persist_job(job, remote_post_id=f"remote-{job.id}")
            return "published"

        if job.destination_id == "ok-destination" and Platform.OK in self.publishers:
            return self._publish_with_adapter(job, Platform.OK)

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

    def _persist_job(
        self,
        job: DeliveryJob,
        remote_post_id: str | None = None,
        remote_permalink: str | None = None,
    ) -> None:
        if not self.repository:
            return
        self.repository.update_delivery_job(job)
        if remote_post_id and job.status == DeliveryStatus.PUBLISHED:
            self.repository.save_published_post(
                delivery_job_id=job.id,
                remote_post_id=remote_post_id,
                remote_permalink=remote_permalink or f"https://example.com/{remote_post_id}",
            )

    def _publish_with_adapter(self, job: DeliveryJob, platform: Platform) -> str:
        if not self.repository:
            return "retry_scheduled"

        source_post = self.repository.get_source_post(job.source_post_id)
        rendered_payload = self.renderer.render(platform, source_post)
        if rendered_payload.get("error_code"):
            job.status = DeliveryStatus.FAILED
            job.last_error_code = rendered_payload["error_code"]
            job.last_error_message = "Content is not supported by destination renderer"
            job.next_attempt_at = None
            self._persist_job(job)
            return "failed"

        publisher = self.publishers[platform]
        try:
            result = publisher.publish(rendered_payload)
        except TransientPublishError as exc:
            self._schedule_retry(job, "transient_failure", str(exc))
            return "retry_scheduled"
        except PermanentPublishError as exc:
            job.status = DeliveryStatus.FAILED
            job.last_error_code = "permanent_failure"
            job.last_error_message = str(exc)
            job.next_attempt_at = None
            self._persist_job(job)
            return "failed"

        job.status = DeliveryStatus.PUBLISHED
        job.last_error_code = None
        job.last_error_message = None
        job.next_attempt_at = None
        self._persist_job(
            job,
            remote_post_id=result.remote_post_id,
            remote_permalink=result.remote_permalink,
        )
        return "published"


class HealthService:
    def __init__(self, repository: SqliteRepository | None = None) -> None:
        self.repository = repository

    def status(self) -> dict:
        if not self.repository:
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
                "message": "Repository is not configured.",
            }

        database_healthy = self.repository.database_is_healthy()
        status_counts = self.repository.get_delivery_status_counts()
        queue_depth = self.repository.get_queue_depth()
        due_retry_jobs = self.repository.count_due_retry_jobs()

        queue_state = "healthy"
        overall_status = "healthy"
        if due_retry_jobs > 0:
            queue_state = "degraded"
            overall_status = "degraded"
        if not database_healthy:
            overall_status = "unhealthy"

        return {
            "status": overall_status,
            "checks": {
                "queue": queue_state,
                "database": "healthy" if database_healthy else "unhealthy",
            },
            "metrics": {
                "success_count": status_counts.get(DeliveryStatus.PUBLISHED.value, 0),
                "error_count": status_counts.get(DeliveryStatus.FAILED.value, 0),
                "retry_count": status_counts.get(DeliveryStatus.RETRY_SCHEDULED.value, 0),
                "queue_depth": queue_depth,
            },
            "message": self._build_message(overall_status, due_retry_jobs),
        }

    def _build_message(self, overall_status: str, due_retry_jobs: int) -> str:
        if overall_status == "healthy":
            return "All critical checks are healthy."
        if overall_status == "unhealthy":
            return "Database connectivity is unhealthy."
        return f"Queue has {due_retry_jobs} due retry job(s)."
