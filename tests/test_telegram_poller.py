from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from repost_bot.config import AppConfig, PlatformCredentials
from repost_bot.runtime import build_application
from repost_bot.telegram_adapter import TelegramUpdateAdapter
from repost_bot.telegram_poller import TelegramBotApiClient, TelegramPollingLoop


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.ingested: list[tuple[str, int]] = []

    def ingest_telegram_post(self, post) -> str:
        self.ingested.append((post.chat_id, post.message_id))
        return f"source-{post.message_id}"


class _FakeWorker:
    def __init__(self) -> None:
        self.calls = 0
        self.last_limit: int | None = None

    def process_due_jobs(self, limit: int = 100) -> list[str]:
        self.calls += 1
        self.last_limit = limit
        return ["published"]


class TelegramPollerTests(unittest.TestCase):
    def test_run_once_fetches_updates_ingests_posts_and_processes_due_jobs(self) -> None:
        requests: list[dict] = []

        def transport(method: str, payload: dict) -> dict:
            requests.append({"method": method, "payload": payload})
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 101,
                        "channel_post": {
                            "message_id": 7001,
                            "chat": {"id": "tg-channel-1", "type": "channel"},
                            "date": 1710001000,
                            "text": "Hello from polling",
                        },
                    },
                    {
                        "update_id": 102,
                        "message": {
                            "message_id": 1,
                            "chat": {"id": "user-1", "type": "private"},
                            "text": "ignore me",
                        },
                    },
                ],
            }

        client = TelegramBotApiClient(
            bot_token="telegram-secret",
            transport=transport,
            poll_timeout_seconds=30,
        )
        orchestrator = _FakeOrchestrator()
        worker = _FakeWorker()
        loop = TelegramPollingLoop(
            client=client,
            adapter=TelegramUpdateAdapter(expected_channel_ids=("tg-channel-1",)),
            orchestrator=orchestrator,
            delivery_worker=worker,
            delivery_batch_limit=25,
        )

        result = loop.run_once()

        self.assertEqual(orchestrator.ingested, [("tg-channel-1", 7001)])
        self.assertEqual(worker.calls, 1)
        self.assertEqual(worker.last_limit, 25)
        self.assertEqual(client.next_offset, 103)
        self.assertEqual(result["updates_received"], 2)
        self.assertEqual(result["posts_ingested"], 1)
        self.assertEqual(result["delivery_results"], ["published"])
        self.assertEqual(requests[0]["method"], "getUpdates")
        self.assertEqual(requests[0]["payload"]["offset"], 0)

    def test_run_once_returns_without_processing_when_no_updates_arrive(self) -> None:
        client = TelegramBotApiClient(
            bot_token="telegram-secret",
            transport=lambda method, payload: {"ok": True, "result": []},
            poll_timeout_seconds=30,
        )
        orchestrator = _FakeOrchestrator()
        worker = _FakeWorker()
        loop = TelegramPollingLoop(
            client=client,
            adapter=TelegramUpdateAdapter(expected_channel_ids=("tg-channel-1",)),
            orchestrator=orchestrator,
            delivery_worker=worker,
        )

        result = loop.run_once()

        self.assertEqual(result["updates_received"], 0)
        self.assertEqual(result["posts_ingested"], 0)
        self.assertEqual(result["delivery_results"], [])
        self.assertEqual(worker.calls, 0)

    def test_cli_run_poller_once_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "poller.sqlite3")
            config = AppConfig(
                app_env="dev",
                log_level="INFO",
                database_path=database_path,
                threads_enabled=False,
                telegram_channel_ids=("tg-channel-1",),
                telegram_bot_token="telegram-secret",
                vk=PlatformCredentials("vk-community-1", "vk-secret"),
                ok=PlatformCredentials("ok-group-1", "ok-secret"),
                threads=PlatformCredentials("threads-account-1", "threads-secret"),
                allowed_operators=("allowed-operator",),
                telegram_poll_timeout_seconds=30,
                telegram_poll_interval_seconds=1,
                delivery_batch_limit=10,
            )

            from repost_bot.__main__ import main

            with patch("repost_bot.__main__.AppConfig.from_env", return_value=config):
                with patch("repost_bot.__main__.build_application", return_value=build_application(config)):
                    with patch("repost_bot.__main__.TelegramPollingLoop.run_once", return_value={
                        "updates_received": 1,
                        "posts_ingested": 1,
                        "delivery_results": ["published"],
                    }):
                        buffer = io.StringIO()
                        with redirect_stdout(buffer):
                            exit_code = main(["run-poller", "--once"])

        self.assertEqual(exit_code, 0)
        self.assertIn("updates_received", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
