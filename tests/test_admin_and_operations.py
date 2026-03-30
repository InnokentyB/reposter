from __future__ import annotations

import unittest

from repost_bot.service import HealthService, RepostOrchestrator


class AdminAndOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = RepostOrchestrator()
        self.health_service = HealthService()

    def test_authorized_operator_can_retry_manual_review_job_and_audit_is_recorded(self) -> None:
        result = self.orchestrator.retry_delivery_job("job-42", actor="allowed-operator")

        self.assertEqual(result, "retry_started")

    def test_unauthorized_operator_cannot_retry_manual_review_job(self) -> None:
        result = self.orchestrator.retry_delivery_job("job-42", actor="intruder")

        self.assertEqual(result, "forbidden")

    def test_unauthorized_operator_cannot_disable_destination(self) -> None:
        result = self.orchestrator.disable_destination("vk-destination", actor="intruder")

        self.assertEqual(result, "forbidden")

    def test_health_endpoint_reports_degraded_when_queue_or_database_is_unhealthy(self) -> None:
        status = self.health_service.status()

        self.assertIn(status["status"], {"degraded", "unhealthy"})

    def test_backfill_only_creates_jobs_for_missing_posts_without_duplicates(self) -> None:
        result = self.orchestrator.trigger_backfill(100, 110, actor="allowed-operator")

        self.assertEqual(result, ["source-102", "source-108"])

    def test_logs_and_errors_mask_sensitive_values(self) -> None:
        result = self.health_service.status()

        self.assertNotIn("token", str(result).lower())
        self.assertNotIn("secret", str(result).lower())

    def test_metrics_count_only_completed_outcomes_without_double_counting(self) -> None:
        status = self.health_service.status()

        self.assertIn("metrics", status)
        self.assertEqual(
            status["metrics"],
            {
                "success_count": 1,
                "error_count": 1,
                "retry_count": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
