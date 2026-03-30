from __future__ import annotations

import os
import tempfile
import unittest

from repost_bot.config import AppConfig, PlatformCredentials
from repost_bot.runtime import build_application
from repost_bot.service import RepostOrchestrator
from repost_bot.storage import SqliteRepository
from tests.helpers import telegram_post


class StorageTests(unittest.TestCase):
    def _config(self, database_path: str) -> AppConfig:
        return AppConfig(
            app_env="dev",
            log_level="INFO",
            database_path=database_path,
            telegram_channel_id="tg-channel-1",
            telegram_bot_token="telegram-secret-123",
            vk=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
            ok=PlatformCredentials(target_id="ok-group-1", access_token="ok-secret"),
            threads=PlatformCredentials(target_id="threads-account-1", access_token="threads-secret"),
            allowed_operators=("allowed-operator",),
        )

    def test_runtime_build_creates_sqlite_schema_and_default_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "repost.sqlite3")
            app = build_application(self._config(database_path))

            self.assertEqual(app.repository.count_rows("destinations"), 3)

    def test_ingestion_persists_source_post_and_delivery_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "repost.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)

            source_post_id = orchestrator.ingest_telegram_post(telegram_post(message_id=555))

            self.assertEqual(source_post_id, "source-555")
            self.assertEqual(repository.count_rows("source_posts"), 1)
            self.assertEqual(repository.count_rows("delivery_jobs"), 2)

    def test_duplicate_ingestion_is_blocked_after_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "repost.sqlite3")
            repository = SqliteRepository(database_path)
            repository.seed_default_destinations(threads_enabled=False)

            first = RepostOrchestrator(repository=repository)
            second = RepostOrchestrator(repository=SqliteRepository(database_path))

            first_result = first.ingest_telegram_post(telegram_post(message_id=777))
            second_result = second.ingest_telegram_post(telegram_post(message_id=777))

            self.assertEqual(first_result, "source-777")
            self.assertEqual(second_result, "duplicate_ignored")
            self.assertEqual(repository.count_rows("source_posts"), 1)

    def test_retry_action_is_audited_in_persistent_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "repost.sqlite3"))
            orchestrator = RepostOrchestrator(repository=repository)

            result = orchestrator.retry_delivery_job("job-42", actor="allowed-operator")

            self.assertEqual(result, "retry_started")
            self.assertEqual(repository.count_rows("audit_events"), 1)


if __name__ == "__main__":
    unittest.main()
