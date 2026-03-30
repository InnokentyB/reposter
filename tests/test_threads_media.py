from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from repost_bot.config import PlatformCredentials
from repost_bot.errors import PermanentPublishError
from repost_bot.media_store import LocalMediaStore
from repost_bot.threads_adapter import ThreadsPublisher


class LocalMediaStoreTests(unittest.TestCase):
    def test_store_file_writes_content_and_returns_public_url(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = LocalMediaStore(
                storage_path=tempdir,
                public_base_url="https://media.example.com/repost-media",
            )

            public_url = store.store_file(
                {
                    "filename": "photo.jpg",
                    "content_type": "image/jpeg",
                    "content": b"image-bytes",
                }
            )

            self.assertTrue(public_url.startswith("https://media.example.com/repost-media/"))
            stored_name = public_url.rsplit("/", 1)[-1]
            with open(os.path.join(tempdir, stored_name), "rb") as handle:
                self.assertEqual(handle.read(), b"image-bytes")


class ThreadsMediaPublisherTests(unittest.TestCase):
    def test_default_http_transport_publishes_image_post_when_media_resolver_is_configured(self) -> None:
        requests: list[tuple[str, str]] = []

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
            requests.append((request.full_url, request.data.decode("utf-8")))
            if request.full_url.endswith("/threads"):
                return _Response(b'{"id":"container-image-1"}')
            return _Response(b'{"id":"threads-post-image-1"}')

        publisher = ThreadsPublisher(
            credentials=PlatformCredentials(target_id="threads-account-1", access_token="threads-secret"),
            media_resolver=lambda file_id: "https://media.example.com/thread-photo.jpg",
        )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = publisher.publish(
                {"text": "Photo Threads", "media": [{"type": "photo", "file_id": "tg-photo-1"}]}
            )

        self.assertEqual(result.remote_post_id, "threads-post-image-1")
        self.assertIn("media_type=IMAGE", requests[0][1])
        self.assertIn("image_url=https%3A%2F%2Fmedia.example.com%2Fthread-photo.jpg", requests[0][1])

    def test_default_http_transport_rejects_media_without_public_media_resolver(self) -> None:
        publisher = ThreadsPublisher(
            credentials=PlatformCredentials(target_id="threads-account-1", access_token="threads-secret"),
        )

        with self.assertRaises(PermanentPublishError):
            publisher.publish({"text": "Photo Threads", "media": [{"type": "photo", "file_id": "tg-photo-1"}]})


if __name__ == "__main__":
    unittest.main()
