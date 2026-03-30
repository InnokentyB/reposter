from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta

from repost_bot.admin_cli import render_status_report
from repost_bot.contracts import DeliveryStatus
from repost_bot.storage import SqliteRepository


class AdminCliTests(unittest.TestCase):
    def test_render_status_report_shows_counts_stuck_jobs_and_recent_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "admin.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-2001",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=2001,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:2001",
            )
            repository.create_delivery_job("source-2001", "vk-destination")
            repository.create_delivery_job("source-2001", "ok-destination")
            repository.mark_delivery_job_for_retry(
                "source-2001:ok-destination",
                attempt_count=2,
                next_attempt_at=datetime.utcnow() - timedelta(minutes=10),
                error_code="transient_failure",
                error_message="temporary outage",
            )
            vk_job = repository.get_delivery_job("source-2001:vk-destination")
            vk_job.status = DeliveryStatus.FAILED
            vk_job.last_error_code = "permanent_failure"
            vk_job.last_error_message = "payload rejected"
            repository.update_delivery_job(vk_job)

            report = render_status_report(repository, limit=5)

            self.assertIn("Delivery Status Summary", report)
            self.assertIn("failed: 1", report)
            self.assertIn("retry_scheduled: 1", report)
            self.assertIn("source-2001:ok-destination", report)
            self.assertIn("payload rejected", report)

    def test_render_status_report_handles_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "admin.sqlite3"))

            report = render_status_report(repository, limit=5)

            self.assertIn("No delivery jobs found.", report)

    def test_cli_main_status_command_prints_report(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "admin.sqlite3")
            repository = SqliteRepository(database_path)
            repository.seed_default_destinations(threads_enabled=False)
            repository.create_source_post(
                source_post_id="source-3001",
                source_platform="telegram",
                source_channel_id="tg-channel-1",
                source_message_id=3001,
                raw_payload={"text": "hello"},
                normalized_payload={"text": "hello", "media": []},
                content_hash="tg-channel-1:3001",
            )
            repository.create_delivery_job("source-3001", "vk-destination")

            from repost_bot.__main__ import main

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(["status", "--database", database_path, "--limit", "3"])

            output = buffer.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Delivery Status Summary", output)
            self.assertIn("pending: 1", output)


if __name__ == "__main__":
    unittest.main()
