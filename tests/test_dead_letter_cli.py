from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from repost_bot.admin_cli import render_dead_letter_report
from repost_bot.contracts import DeliveryStatus
from repost_bot.service import RepostOrchestrator
from repost_bot.storage import SqliteRepository


class DeadLetterCliTests(unittest.TestCase):
    def test_render_dead_letter_report_lists_manual_review_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "dead-letter.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-5001",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=5001,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:5001",
            )
            repository.create_delivery_job("source-5001", "ok-destination")
            job = repository.get_delivery_job("source-5001:ok-destination")
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            job.attempt_count = 3
            job.last_error_code = "transient_failure"
            job.last_error_message = "needs operator review"
            repository.update_delivery_job(job)

            report = render_dead_letter_report(repository, limit=10)

            self.assertIn("Manual Review Queue", report)
            self.assertIn("source-5001:ok-destination", report)
            self.assertIn("needs operator review", report)

    def test_authorized_manual_retry_resets_job_to_pending_and_audits_action(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "dead-letter.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-5002",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=5002,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:5002",
            )
            repository.create_delivery_job("source-5002", "ok-destination")
            job = repository.get_delivery_job("source-5002:ok-destination")
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            job.attempt_count = 3
            job.last_error_code = "transient_failure"
            job.last_error_message = "operator retry needed"
            repository.update_delivery_job(job)

            orchestrator = RepostOrchestrator(
                repository=repository,
                allowed_operators={"allowed-operator"},
            )

            result = orchestrator.retry_delivery_job("source-5002:ok-destination", actor="allowed-operator")
            updated = repository.get_delivery_job("source-5002:ok-destination")

            self.assertEqual(result, "retry_started")
            self.assertEqual(updated.status, DeliveryStatus.PENDING)
            self.assertEqual(updated.attempt_count, 0)
            self.assertIsNone(updated.last_error_code)
            self.assertEqual(repository.count_rows("audit_events"), 1)

    def test_dead_letter_command_and_retry_job_command_work_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "dead-letter.sqlite3")
            repository = SqliteRepository(database_path)
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-5003",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=5003,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:5003",
            )
            repository.create_delivery_job("source-5003", "ok-destination")
            job = repository.get_delivery_job("source-5003:ok-destination")
            job.status = DeliveryStatus.MANUAL_REVIEW_REQUIRED
            job.attempt_count = 3
            job.last_error_message = "needs retry"
            repository.update_delivery_job(job)

            from repost_bot.__main__ import main

            dead_letter_buffer = io.StringIO()
            with redirect_stdout(dead_letter_buffer):
                dead_letter_exit = main(["dead-letter", "--database", database_path, "--limit", "10"])

            retry_buffer = io.StringIO()
            with redirect_stdout(retry_buffer):
                retry_exit = main(
                    [
                        "retry-job",
                        "--database",
                        database_path,
                        "--job-id",
                        "source-5003:ok-destination",
                        "--actor",
                        "allowed-operator",
                    ]
                )

            self.assertEqual(dead_letter_exit, 0)
            self.assertEqual(retry_exit, 0)
            self.assertIn("Manual Review Queue", dead_letter_buffer.getvalue())
            self.assertIn("retry_started", retry_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
