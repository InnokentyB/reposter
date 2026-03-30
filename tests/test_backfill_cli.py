from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from repost_bot.service import RepostOrchestrator
from repost_bot.storage import SqliteRepository
from tests.helpers import telegram_post


class BackfillTests(unittest.TestCase):
    def test_backfill_creates_only_missing_source_posts_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "backfill.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)

            orchestrator.ingest_telegram_post(telegram_post(message_id=101))
            created = orchestrator.trigger_backfill(100, 103, actor="allowed-operator")

            self.assertEqual(created, ["source-100", "source-102", "source-103"])
            self.assertEqual(repository.count_rows("source_posts"), 4)

    def test_backfill_is_rejected_for_unauthorized_operator(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "backfill.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(repository=repository)

            created = orchestrator.trigger_backfill(100, 103, actor="intruder")

            self.assertEqual(created, [])

    def test_backfill_command_prints_created_source_posts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "backfill.sqlite3")
            repository = SqliteRepository(database_path)
            repository.seed_default_destinations(threads_enabled=False)
            RepostOrchestrator(repository=repository).ingest_telegram_post(telegram_post(message_id=101))

            from repost_bot.__main__ import main

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(
                    [
                        "backfill",
                        "--database",
                        database_path,
                        "--start-message-id",
                        "100",
                        "--end-message-id",
                        "103",
                        "--actor",
                        "allowed-operator",
                    ]
                )

            output = buffer.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("source-100", output)
            self.assertIn("source-103", output)


if __name__ == "__main__":
    unittest.main()
