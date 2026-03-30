from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta

from repost_bot.service import HealthService
from repost_bot.storage import SqliteRepository


class HealthTests(unittest.TestCase):
    def test_health_is_healthy_when_database_and_queue_are_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "health.sqlite3"))
            service = HealthService(repository=repository)

            status = service.status()

            self.assertEqual(status["status"], "healthy")
            self.assertEqual(status["checks"]["database"], "healthy")
            self.assertEqual(status["checks"]["queue"], "healthy")

    def test_health_is_degraded_when_due_retry_jobs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "health.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-4001",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=4001,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:4001",
            )
            repository.create_delivery_job("source-4001", "vk-destination")
            repository.mark_delivery_job_for_retry(
                "source-4001:vk-destination",
                attempt_count=1,
                next_attempt_at=datetime.utcnow() - timedelta(minutes=1),
                error_code="transient_failure",
                error_message="late retry",
            )
            service = HealthService(repository=repository)

            status = service.status()

            self.assertEqual(status["status"], "degraded")
            self.assertEqual(status["checks"]["queue"], "degraded")
            self.assertGreaterEqual(status["metrics"]["queue_depth"], 1)

    def test_health_metrics_include_success_error_retry_and_queue_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "health.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-4002",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=4002,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:4002",
            )
            repository.create_delivery_job("source-4002", "vk-destination")
            repository.create_delivery_job("source-4002", "ok-destination")
            repository.mark_delivery_job_for_retry(
                "source-4002:ok-destination",
                attempt_count=1,
                next_attempt_at=datetime.utcnow() + timedelta(minutes=1),
                error_code="transient_failure",
                error_message="retry queued",
            )
            vk_job = repository.get_delivery_job("source-4002:vk-destination")
            vk_job.status = vk_job.status.PUBLISHED
            repository.update_delivery_job(vk_job)
            repository.save_published_post("source-4002:vk-destination", "remote-1")
            service = HealthService(repository=repository)

            status = service.status()

            self.assertEqual(status["metrics"]["success_count"], 1)
            self.assertEqual(status["metrics"]["retry_count"], 1)
            self.assertEqual(status["metrics"]["error_count"], 0)
            self.assertEqual(status["metrics"]["queue_depth"], 1)

    def test_cli_main_health_command_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "health.sqlite3")
            SqliteRepository(database_path)

            from repost_bot.__main__ import main

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(["health", "--database", database_path])

            output = buffer.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn('"status": "healthy"', output)
            self.assertIn('"checks"', output)


if __name__ == "__main__":
    unittest.main()
