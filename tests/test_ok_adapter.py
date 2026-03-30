from __future__ import annotations

import os
import tempfile
import unittest

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import DeliveryStatus, Platform, RetryPolicy
from repost_bot.errors import PermanentPublishError, TransientPublishError
from repost_bot.ok_adapter import OkPublisher
from repost_bot.rendering import PlatformRenderer
from repost_bot.service import DeliveryWorker, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from tests.helpers import telegram_post


class OkPublisherTests(unittest.TestCase):
    def test_publish_text_payload_returns_publish_result(self) -> None:
        calls: list[dict] = []

        def transport(payload: dict) -> dict:
            calls.append(payload)
            return {"post_id": "ok-post-123", "permalink": "https://ok.example/post/123"}

        publisher = OkPublisher(
            credentials=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
            transport=transport,
        )

        result = publisher.publish({"text": "Hello OK", "media": []})

        self.assertEqual(result.remote_post_id, "ok-post-123")
        self.assertEqual(calls[0]["group_id"], "ok-group-1")
        self.assertEqual(calls[0]["text"], "Hello OK")

    def test_publish_photo_payload_passes_media_to_transport(self) -> None:
        captured: list[dict] = []

        def transport(payload: dict) -> dict:
            captured.append(payload)
            return {"post_id": "ok-post-456"}

        publisher = OkPublisher(
            credentials=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
            transport=transport,
        )

        publisher.publish(
            {
                "text": "Photo post",
                "media": [{"type": "photo", "file_id": "photo-1"}],
            }
        )

        self.assertEqual(captured[0]["media"], [{"type": "photo", "file_id": "photo-1"}])


class OkWorkerIntegrationTests(unittest.TestCase):
    def test_worker_uses_ok_publisher_and_persists_remote_post(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "ok.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1105, text="Hello OK")
            )

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.OK: OkPublisher(
                        credentials=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
                        transport=lambda payload: {
                            "post_id": "ok-post-789",
                            "permalink": "https://ok.example/post/789",
                        },
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            ok_job = repository.get_delivery_job(f"{source_post_id}:ok-destination")

            self.assertIn("published", results)
            self.assertEqual(ok_job.status, DeliveryStatus.PUBLISHED)
            published_row = repository.get_published_post(f"{source_post_id}:ok-destination")
            self.assertEqual(published_row["remote_post_id"], "ok-post-789")

    def test_worker_schedules_retry_when_ok_publisher_raises_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "ok.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1106, text="Hello retry")
            )

            def failing_transport(payload: dict) -> dict:
                raise TransientPublishError("ok temporary outage")

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.OK: OkPublisher(
                        credentials=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
                        transport=failing_transport,
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            ok_job = repository.get_delivery_job(f"{source_post_id}:ok-destination")

            self.assertIn("retry_scheduled", results)
            self.assertEqual(ok_job.status, DeliveryStatus.RETRY_SCHEDULED)
            self.assertEqual(ok_job.last_error_code, "transient_failure")

    def test_worker_marks_failed_when_ok_publisher_raises_permanent_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "ok.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1107, text="Broken OK")
            )

            def failing_transport(payload: dict) -> dict:
                raise PermanentPublishError("ok payload rejected")

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.OK: OkPublisher(
                        credentials=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
                        transport=failing_transport,
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            ok_job = repository.get_delivery_job(f"{source_post_id}:ok-destination")

            self.assertIn("failed", results)
            self.assertEqual(ok_job.status, DeliveryStatus.FAILED)
            self.assertEqual(ok_job.last_error_code, "permanent_failure")


if __name__ == "__main__":
    unittest.main()
