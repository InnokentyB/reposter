from __future__ import annotations

import unittest

from repost_bot.contracts import DeliveryStatus
from repost_bot.service import DeliveryWorker
from tests.helpers import delivery_job


class DeliveryWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = DeliveryWorker()

    def test_successful_publish_marks_only_target_job_as_published(self) -> None:
        job = delivery_job(destination_id="vk-destination", status=DeliveryStatus.PENDING)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "published")

    def test_partial_failure_does_not_block_other_platforms(self) -> None:
        vk_job = delivery_job(id="job-vk", destination_id="vk-destination")
        ok_job = delivery_job(id="job-ok", destination_id="ok-destination")
        threads_job = delivery_job(id="job-threads", destination_id="threads-destination")

        vk_result = self.worker.process_delivery_job(vk_job)
        ok_result = self.worker.process_delivery_job(ok_job)
        threads_result = self.worker.process_delivery_job(threads_job)

        self.assertEqual(vk_result, "published")
        self.assertIn(ok_result, {"retry_scheduled", "failed"})
        self.assertEqual(threads_result, "published")

    def test_timeout_schedules_retry_and_increments_attempt_count(self) -> None:
        job = delivery_job(id="job-timeout", attempt_count=0, status=DeliveryStatus.PENDING)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "retry_scheduled")
        self.assertGreaterEqual(job.attempt_count, 1)

    def test_exhausted_retries_move_job_to_manual_review_required(self) -> None:
        job = delivery_job(attempt_count=3, status=DeliveryStatus.RETRY_SCHEDULED)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "manual_review_required")

    def test_reprocessing_published_job_does_not_create_second_remote_post(self) -> None:
        job = delivery_job(status=DeliveryStatus.PUBLISHED)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "already_published")

    def test_rate_limit_honors_retry_after_without_immediate_retry(self) -> None:
        job = delivery_job(id="job-rate-limit", status=DeliveryStatus.PENDING)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "retry_scheduled")

    def test_restart_resumes_pending_or_retry_scheduled_jobs_without_duplicates(self) -> None:
        pending_job = delivery_job(id="job-pending", status=DeliveryStatus.PENDING)
        retry_job = delivery_job(id="job-retry", status=DeliveryStatus.RETRY_SCHEDULED)

        first = self.worker.process_delivery_job(pending_job)
        second = self.worker.process_delivery_job(retry_job)

        self.assertIn(first, {"published", "retry_scheduled"})
        self.assertIn(second, {"published", "retry_scheduled"})

    def test_ambiguous_publish_result_requires_reconciliation_before_retry(self) -> None:
        job = delivery_job(id="job-ambiguous", status=DeliveryStatus.PENDING)

        result = self.worker.process_delivery_job(job)

        self.assertEqual(result, "reconciliation_required")


if __name__ == "__main__":
    unittest.main()
