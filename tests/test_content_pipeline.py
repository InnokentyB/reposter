from __future__ import annotations

import unittest

from repost_bot.contracts import Platform
from repost_bot.normalization import TelegramNormalizer
from repost_bot.rendering import PlatformRenderer
from tests.helpers import canonical_post, telegram_post


class TelegramNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer = TelegramNormalizer()

    def test_normalizer_converts_text_post_to_canonical_format(self) -> None:
        post = telegram_post(
            text="Hello *world* https://example.com",
            payload={"entities": [{"type": "bold"}]},
        )

        canonical = self.normalizer.normalize(post)

        self.assertEqual(canonical.source_message_id, 101)
        self.assertIn("text", canonical.normalized_payload)

    def test_normalizer_collapses_media_group_into_single_canonical_post(self) -> None:
        post = telegram_post(
            message_id=301,
            media_group_id="group-1",
            payload={"media": ["photo-1", "photo-2"]},
        )

        canonical = self.normalizer.normalize(post)

        self.assertEqual(canonical.source_message_id, 301)
        self.assertEqual(len(canonical.normalized_payload["media"]), 2)


class PlatformRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = PlatformRenderer()

    def test_renderer_rejects_unsupported_content_for_target_platform(self) -> None:
        post = canonical_post(
            normalized_payload={"text": "Hello", "media": [{"type": "poll"}]},
        )

        result = self.renderer.render(Platform.VK, post)

        self.assertEqual(result["error_code"], "content_not_supported")

    def test_renderer_handles_platform_specific_text_boundaries(self) -> None:
        post = canonical_post(
            normalized_payload={"text": "x" * 100_000, "media": []},
        )

        result = self.renderer.render(Platform.OK, post)

        self.assertEqual(result["error_code"], "content_not_supported")


if __name__ == "__main__":
    unittest.main()

