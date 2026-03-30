from __future__ import annotations

import os
import tempfile
import unittest

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import DeliveryStatus, Platform, RetryPolicy
from repost_bot.errors import TransientPublishError
from repost_bot.rendering import PlatformRenderer
from repost_bot.service import DeliveryWorker, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from repost_bot.vk_adapter import VkPublisher
from tests.helpers import canonical_post, telegram_post


class VkPublisherTests(unittest.TestCase):
    def test_publish_text_payload_returns_publish_result(self) -> None:
        calls: list[dict] = []

        def transport(payload: dict) -> dict:
            calls.append(payload)
            return {"post_id": "vk-post-123", "permalink": "https://vk.example/post/123"}

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
            transport=transport,
        )

        result = publisher.publish({"text": "Hello VK", "media": []})

        self.assertEqual(result.remote_post_id, "vk-post-123")
        self.assertEqual(calls[0]["owner_id"], "vk-community-1")
        self.assertEqual(calls[0]["message"], "Hello VK")

    def test_publish_photo_payload_passes_attachments_to_transport(self) -> None:
        captured: list[dict] = []

        def transport(payload: dict) -> dict:
            captured.append(payload)
            return {"post_id": "vk-post-456"}

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
            transport=transport,
        )

        publisher.publish(
            {
                "text": "Photo post",
                "media": [{"type": "photo", "file_id": "photo-1"}],
            }
        )

        self.assertEqual(captured[0]["attachments"], ["photo:photo-1"])


class VkWorkerIntegrationTests(unittest.TestCase):
    def test_worker_uses_vk_publisher_and_persists_remote_post(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "vk.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1005, text="Hello VK")
            )
            renderer = PlatformRenderer()

            publisher = VkPublisher(
                credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
                transport=lambda payload: {
                    "post_id": "vk-post-789",
                    "permalink": "https://vk.example/post/789",
                },
            )

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=renderer,
                publishers={Platform.VK: publisher},
            )

            results = worker.process_due_jobs(limit=10)
            vk_job = repository.get_delivery_job(f"{source_post_id}:vk-destination")

            self.assertIn("published", results)
            self.assertEqual(vk_job.status, DeliveryStatus.PUBLISHED)
            published_row = repository.get_published_post(f"{source_post_id}:vk-destination")
            self.assertEqual(published_row["remote_post_id"], "vk-post-789")

    def test_worker_schedules_retry_when_vk_publisher_raises_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "vk.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1006, text="Hello retry")
            )

            def failing_transport(payload: dict) -> dict:
                raise TransientPublishError("vk temporary outage")

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.VK: VkPublisher(
                        credentials=PlatformCredentials(
                            target_id="vk-community-1",
                            access_token="vk-secret",
                        ),
                        transport=failing_transport,
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            vk_job = repository.get_delivery_job(f"{source_post_id}:vk-destination")

            self.assertIn("retry_scheduled", results)
            self.assertEqual(vk_job.status, DeliveryStatus.RETRY_SCHEDULED)
            self.assertEqual(vk_job.last_error_code, "transient_failure")


if __name__ == "__main__":
    unittest.main()
