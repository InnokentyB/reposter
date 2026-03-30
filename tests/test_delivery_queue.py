from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from repost_bot.contracts import DeliveryStatus, RetryPolicy
from repost_bot.service import DeliveryWorker, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from tests.helpers import telegram_post


class DeliveryQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300)

    def test_lists_only_due_delivery_jobs_from_persistent_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "queue.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)
            source_post_id = orchestrator.ingest_telegram_post(telegram_post(message_id=901))

            ok_job_id = f"{source_post_id}:ok-destination"
            repository.mark_delivery_job_for_retry(
                ok_job_id,
                attempt_count=1,
                next_attempt_at=datetime.utcnow() + timedelta(hours=1),
                error_code="rate_limited",
                error_message="retry later",
            )

            due_jobs = repository.list_due_delivery_jobs(limit=10)

            self.assertEqual(len(due_jobs), 1)
            self.assertEqual(due_jobs[0].destination_id, "vk-destination")

    def test_process_due_jobs_publishes_successful_jobs_and_persists_remote_post(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "queue.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)
            source_post_id = orchestrator.ingest_telegram_post(telegram_post(message_id=902))
            worker = DeliveryWorker(repository=repository, retry_policy=self.retry_policy)

            results = worker.process_due_jobs(limit=10)
            vk_job = repository.get_delivery_job(f"{source_post_id}:vk-destination")

            self.assertIn("published", results)
            self.assertEqual(vk_job.status, DeliveryStatus.PUBLISHED)
            self.assertEqual(repository.count_rows("published_posts"), 1)

    def test_process_due_jobs_schedules_retry_for_transient_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "queue.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)
            source_post_id = orchestrator.ingest_telegram_post(telegram_post(message_id=903))
            worker = DeliveryWorker(repository=repository, retry_policy=self.retry_policy)

            worker.process_due_jobs(limit=10)
            ok_job = repository.get_delivery_job(f"{source_post_id}:ok-destination")

            self.assertEqual(ok_job.status, DeliveryStatus.RETRY_SCHEDULED)
            self.assertEqual(ok_job.attempt_count, 1)
            self.assertIsNotNone(ok_job.next_attempt_at)

    def test_exhausted_retry_job_moves_to_manual_review_in_persistent_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "queue.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)
            source_post_id = orchestrator.ingest_telegram_post(telegram_post(message_id=904))
            ok_job_id = f"{source_post_id}:ok-destination"
            repository.mark_delivery_job_for_retry(
                ok_job_id,
                attempt_count=3,
                next_attempt_at=datetime.utcnow() - timedelta(minutes=1),
                error_code="timeout",
                error_message="still failing",
            )
            worker = DeliveryWorker(repository=repository, retry_policy=self.retry_policy)

            results = worker.process_due_jobs(limit=10)
            ok_job = repository.get_delivery_job(ok_job_id)

            self.assertIn("manual_review_required", results)
            self.assertEqual(ok_job.status, DeliveryStatus.MANUAL_REVIEW_REQUIRED)


if __name__ == "__main__":
    unittest.main()
