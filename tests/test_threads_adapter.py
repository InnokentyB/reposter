from __future__ import annotations

import os
import tempfile
import unittest

from repost_bot.config import AppConfig, PlatformCredentials
from repost_bot.contracts import DeliveryStatus, Platform, RetryPolicy
from repost_bot.errors import TransientPublishError
from repost_bot.rendering import PlatformRenderer
from repost_bot.runtime import build_application
from repost_bot.service import DeliveryWorker, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from repost_bot.threads_adapter import ThreadsPublisher
from tests.helpers import telegram_post


class ThreadsPublisherTests(unittest.TestCase):
    def test_publish_text_payload_returns_publish_result(self) -> None:
        calls: list[dict] = []

        def transport(payload: dict) -> dict:
            calls.append(payload)
            return {"post_id": "threads-post-123", "permalink": "https://threads.example/post/123"}

        publisher = ThreadsPublisher(
            credentials=PlatformCredentials(target_id="threads-account-1", access_token="threads-secret"),
            transport=transport,
        )

        result = publisher.publish({"text": "Hello Threads", "media": []})

        self.assertEqual(result.remote_post_id, "threads-post-123")
        self.assertEqual(calls[0]["account_id"], "threads-account-1")
        self.assertEqual(calls[0]["text"], "Hello Threads")


class ThreadsWorkerIntegrationTests(unittest.TestCase):
    def test_worker_uses_threads_publisher_when_feature_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "threads.sqlite3"))
            repository.seed_default_destinations(threads_enabled=True)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1405, text="Hello Threads")
            )

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.THREADS: ThreadsPublisher(
                        credentials=PlatformCredentials(
                            target_id="threads-account-1",
                            access_token="threads-secret",
                        ),
                        transport=lambda payload: {
                            "post_id": "threads-post-789",
                            "permalink": "https://threads.example/post/789",
                        },
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            threads_job = repository.get_delivery_job(f"{source_post_id}:threads-destination")

            self.assertIn("published", results)
            self.assertEqual(threads_job.status, DeliveryStatus.PUBLISHED)

    def test_worker_schedules_retry_when_threads_publisher_raises_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "threads.sqlite3"))
            repository.seed_default_destinations(threads_enabled=True)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1406, text="Hello retry")
            )

            def failing_transport(payload: dict) -> dict:
                raise TransientPublishError("threads temporary outage")

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.THREADS: ThreadsPublisher(
                        credentials=PlatformCredentials(
                            target_id="threads-account-1",
                            access_token="threads-secret",
                        ),
                        transport=failing_transport,
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            threads_job = repository.get_delivery_job(f"{source_post_id}:threads-destination")

            self.assertIn("retry_scheduled", results)
            self.assertEqual(threads_job.status, DeliveryStatus.RETRY_SCHEDULED)


class ThreadsFeatureFlagTests(unittest.TestCase):
    def test_runtime_keeps_threads_destination_disabled_when_flag_is_off(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            app = build_application(
                AppConfig(
                    app_env="dev",
                    log_level="INFO",
                    database_path=os.path.join(tempdir, "threads.sqlite3"),
                    telegram_channel_ids=("tg-channel-1",),
                    telegram_bot_token="telegram-secret",
                    vk=PlatformCredentials("vk-community-1", "vk-secret"),
                    ok=PlatformCredentials("ok-group-1", "ok-secret"),
                    threads=PlatformCredentials("threads-account-1", "threads-secret"),
                    allowed_operators=("allowed-operator",),
                    threads_enabled=False,
                )
            )

            self.assertEqual(app.repository.get_destination_status("threads-destination"), "disabled")

    def test_runtime_activates_threads_destination_when_flag_is_on(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            app = build_application(
                AppConfig(
                    app_env="dev",
                    log_level="INFO",
                    database_path=os.path.join(tempdir, "threads.sqlite3"),
                    telegram_channel_ids=("tg-channel-1",),
                    telegram_bot_token="telegram-secret",
                    vk=PlatformCredentials("vk-community-1", "vk-secret"),
                    ok=PlatformCredentials("ok-group-1", "ok-secret"),
                    threads=PlatformCredentials("threads-account-1", "threads-secret"),
                    allowed_operators=("allowed-operator",),
                    threads_enabled=True,
                )
            )

            self.assertEqual(app.repository.get_destination_status("threads-destination"), "active")


if __name__ == "__main__":
    unittest.main()
