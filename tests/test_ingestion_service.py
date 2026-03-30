from __future__ import annotations

import unittest

from repost_bot.contracts import DeliveryStatus, DestinationStatus, Platform
from repost_bot.service import RepostOrchestrator
from repost_bot.storage import SqliteRepository
from tests.helpers import delivery_job, destination, telegram_post


class IngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = RepostOrchestrator()

    def test_new_telegram_post_creates_one_source_post_and_jobs_for_all_active_platforms(self) -> None:
        post = telegram_post(text="Fresh post")

        result = self.orchestrator.ingest_telegram_post(post)

        self.assertEqual(result, "source-101")

    def test_duplicate_telegram_event_does_not_create_duplicate_source_or_jobs(self) -> None:
        post = telegram_post(message_id=101)
        self.orchestrator.ingest_telegram_post(post)

        duplicate_result = self.orchestrator.ingest_telegram_post(post)

        self.assertEqual(duplicate_result, "duplicate_ignored")

    def test_disabled_platform_is_skipped_during_job_creation(self) -> None:
        active_vk = destination(Platform.VK)
        active_ok = destination(Platform.OK)
        disabled_threads = destination(
            Platform.THREADS,
            id="threads-destination",
            status=DestinationStatus.DISABLED,
        )

        result = self.orchestrator.ingest_telegram_post(telegram_post())

        self.assertEqual(result, "source-101")
        self.assertNotEqual(disabled_threads.status, active_vk.status)
        self.assertEqual(active_ok.status, DestinationStatus.ACTIVE)

    def test_invalid_inbound_payload_is_rejected_without_creating_source_post(self) -> None:
        malformed = telegram_post(text="", payload={"chat_id": None})

        result = self.orchestrator.ingest_telegram_post(malformed)

        self.assertEqual(result, "validation_failed")

    def test_threads_feature_flag_off_excludes_threads_from_pipeline(self) -> None:
        result = self.orchestrator.ingest_telegram_post(telegram_post(message_id=202))

        self.assertNotEqual(result, "threads-job-created")

    def test_out_of_order_event_does_not_mutate_existing_delivery_state(self) -> None:
        current = delivery_job(status=DeliveryStatus.PUBLISHED)
        delayed_post = telegram_post(message_id=100)

        result = self.orchestrator.ingest_telegram_post(delayed_post)

        self.assertEqual(current.status, DeliveryStatus.PUBLISHED)
        self.assertIn(result, {"source-100", "duplicate_ignored"})

    def test_edited_post_is_ignored_without_creating_source_post_or_jobs(self) -> None:
        repository = SqliteRepository(":memory:")
        repository.seed_default_destinations()
        orchestrator = RepostOrchestrator(repository=repository)
        edited_post = telegram_post(
            message_id=303,
            text="Updated text",
            payload={
                "chat_id": "tg-channel-1",
                "message_id": 303,
                "text": "Updated text",
                "entities": [],
                "is_edit": True,
                "update_type": "edited_channel_post",
            },
        )

        result = orchestrator.ingest_telegram_post(edited_post)

        self.assertEqual(result, "edit_ignored")
        self.assertFalse(repository.source_post_exists("tg-channel-1", 303))

    def test_backfill_can_target_non_default_source_channel(self) -> None:
        repository = SqliteRepository(":memory:")
        repository.seed_default_destinations()
        orchestrator = RepostOrchestrator(repository=repository, default_source_channel_id="tg-channel-2")

        created = orchestrator.trigger_backfill(
            start_message_id=401,
            end_message_id=401,
            actor="allowed-operator",
        )

        self.assertEqual(created, ["source-401"])
        self.assertTrue(repository.source_post_exists("tg-channel-2", 401))


if __name__ == "__main__":
    unittest.main()
