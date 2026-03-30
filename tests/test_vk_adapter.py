from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import DeliveryStatus, Platform, RetryPolicy
from repost_bot.errors import PermanentPublishError, TransientPublishError
from repost_bot.rendering import PlatformRenderer
from repost_bot.runtime import build_application
from repost_bot.service import DeliveryWorker, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from repost_bot.vk_adapter import VkPublisher
from tests.helpers import telegram_post


class VkPublisherTests(unittest.TestCase):
    def test_publish_text_payload_returns_publish_result(self) -> None:
        calls: list[dict] = []

        def transport(payload: dict) -> dict:
            calls.append(payload)
            return {"post_id": "vk-post-123", "permalink": "https://vk.example/post/123"}

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
            transport=transport,
        )

        result = publisher.publish({"text": "Hello VK", "media": []})

        self.assertEqual(result.remote_post_id, "vk-post-123")
        self.assertEqual(calls[0]["owner_id"], "vk-community-1")
        self.assertEqual(calls[0]["message"], "Hello VK")

    def test_publish_photo_payload_passes_attachments_to_transport(self) -> None:
        captured: list[dict] = []

        def transport(payload: dict) -> dict:
            captured.append(payload)
            return {"post_id": "vk-post-456"}

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
            transport=transport,
        )

        publisher.publish(
            {
                "text": "Photo post",
                "media": [{"type": "photo", "file_id": "photo-1"}],
            }
        )

        self.assertEqual(captured[0]["attachments"], ["photo:photo-1"])

    def test_default_http_transport_publishes_text_post_via_vk_api(self) -> None:
        captured_requests: list[tuple[str, dict]] = []

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"response":{"post_id":456}}'

        def fake_urlopen(request, timeout=0):
            body = request.data.decode("utf-8")
            captured_requests.append((request.full_url, dict(item.split("=", 1) for item in body.split("&"))))
            return _Response()

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="12345", access_token="vk-secret"),
        )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = publisher.publish({"text": "Hello VK", "media": []})

        self.assertEqual(result.remote_post_id, "456")
        self.assertEqual(captured_requests[0][0], "https://api.vk.com/method/wall.post")
        self.assertIn("message=Hello+VK", "&".join(f"{k}={v}" for k, v in captured_requests[0][1].items()))

    def test_default_http_transport_rejects_media_until_vk_upload_flow_exists(self) -> None:
        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="12345", access_token="vk-secret"),
        )

        with self.assertRaises(PermanentPublishError):
            publisher.publish({"text": "Photo post", "media": [{"type": "photo", "file_id": "tg-photo-1"}]})

    def test_default_http_transport_uploads_photo_when_media_resolver_is_configured(self) -> None:
        requests: list[tuple[str, bytes | None, dict | None]] = []

        class _Response:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return self.payload

        def fake_urlopen(request, timeout=0):
            data = getattr(request, "data", None)
            headers = dict(request.header_items()) if hasattr(request, "header_items") else {}
            requests.append((request.full_url, data, headers))
            if request.full_url.endswith("/photos.getWallUploadServer"):
                return _Response(b'{"response":{"upload_url":"https://upload.vk.example/wall"}}')
            if request.full_url == "https://upload.vk.example/wall":
                return _Response(b'{"server":1,"photo":"[]","hash":"photo-hash"}')
            if request.full_url.endswith("/photos.saveWallPhoto"):
                return _Response(
                    b'{"response":[{"owner_id":-12345,"id":67890,"sizes":[{"url":"https://vk.example/photo"}]}]}'
                )
            return _Response(b'{"response":{"post_id":456}}')

        publisher = VkPublisher(
            credentials=PlatformCredentials(target_id="12345", access_token="vk-secret"),
            media_resolver=lambda file_id: {
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "content": b"fake-image-bytes",
            },
        )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = publisher.publish(
                {"text": "Photo VK", "media": [{"type": "photo", "file_id": "tg-photo-1"}]}
            )

        self.assertEqual(result.remote_post_id, "456")
        self.assertTrue(any(url.endswith("/photos.getWallUploadServer") for url, _, _ in requests))
        self.assertTrue(any(url == "https://upload.vk.example/wall" for url, _, _ in requests))
        self.assertTrue(any(url.endswith("/photos.saveWallPhoto") for url, _, _ in requests))
        self.assertTrue(any(url.endswith("/wall.post") for url, _, _ in requests))


class RuntimePublisherWiringTests(unittest.TestCase):
    def test_build_application_wires_real_publishers_for_enabled_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            app = build_application(
                config=type("Config", (), {
                    "app_env": "dev",
                    "log_level": "INFO",
                    "database_path": os.path.join(tempdir, "runtime.sqlite3"),
                    "threads_enabled": True,
                    "telegram_channel_ids": ("tg-channel-1",),
                    "telegram_channel_id": "tg-channel-1",
                    "telegram_bot_token": "telegram-secret",
                    "vk": PlatformCredentials("12345", "vk-secret"),
                    "ok": PlatformCredentials("ok-group-1", "ok-secret"),
                    "threads": PlatformCredentials("threads-account-1", "threads-secret"),
                    "allowed_operators": ("allowed-operator",),
                    "telegram_poll_timeout_seconds": 30,
                    "telegram_poll_interval_seconds": 2,
                    "delivery_batch_limit": 100,
                })()
            )

        self.assertIn(Platform.VK, app.delivery_worker.publishers)
        self.assertIn(Platform.OK, app.delivery_worker.publishers)
        self.assertIn(Platform.THREADS, app.delivery_worker.publishers)


class VkWorkerIntegrationTests(unittest.TestCase):
    def test_worker_uses_vk_publisher_and_persists_remote_post(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "vk.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1005, text="Hello VK")
            )
            renderer = PlatformRenderer()

            publisher = VkPublisher(
                credentials=PlatformCredentials(target_id="vk-community-1", access_token="vk-secret"),
                transport=lambda payload: {
                    "post_id": "vk-post-789",
                    "permalink": "https://vk.example/post/789",
                },
            )

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=renderer,
                publishers={Platform.VK: publisher},
            )

            results = worker.process_due_jobs(limit=10)
            vk_job = repository.get_delivery_job(f"{source_post_id}:vk-destination")

            self.assertIn("published", results)
            self.assertEqual(vk_job.status, DeliveryStatus.PUBLISHED)
            published_row = repository.get_published_post(f"{source_post_id}:vk-destination")
            self.assertEqual(published_row["remote_post_id"], "vk-post-789")

    def test_worker_schedules_retry_when_vk_publisher_raises_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "vk.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            source_post_id = RepostOrchestrator(repository=repository).ingest_telegram_post(
                telegram_post(message_id=1006, text="Hello retry")
            )

            def failing_transport(payload: dict) -> dict:
                raise TransientPublishError("vk temporary outage")

            worker = DeliveryWorker(
                repository=repository,
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=300),
                renderer=PlatformRenderer(),
                publishers={
                    Platform.VK: VkPublisher(
                        credentials=PlatformCredentials(
                            target_id="vk-community-1",
                            access_token="vk-secret",
                        ),
                        transport=failing_transport,
                    )
                },
            )

            results = worker.process_due_jobs(limit=10)
            vk_job = repository.get_delivery_job(f"{source_post_id}:vk-destination")

            self.assertIn("retry_scheduled", results)
            self.assertEqual(vk_job.status, DeliveryStatus.RETRY_SCHEDULED)
            self.assertEqual(vk_job.last_error_code, "transient_failure")


if __name__ == "__main__":
    unittest.main()
