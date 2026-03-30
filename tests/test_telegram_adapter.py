from __future__ import annotations

import unittest

from repost_bot.telegram_adapter import TelegramUpdateAdapter


class TelegramUpdateAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TelegramUpdateAdapter(expected_channel_id="tg-channel-1")

    def test_parses_channel_text_post_into_telegram_post(self) -> None:
        update = {
            "update_id": 1,
            "channel_post": {
                "message_id": 1001,
                "chat": {"id": "tg-channel-1", "type": "channel"},
                "date": 1710000000,
                "text": "Hello from channel",
                "entities": [{"type": "bold", "offset": 0, "length": 5}],
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNotNone(post)
        self.assertEqual(post.chat_id, "tg-channel-1")
        self.assertEqual(post.message_id, 1001)
        self.assertEqual(post.text, "Hello from channel")
        self.assertEqual(post.payload["entities"][0]["type"], "bold")

    def test_parses_photo_post_and_uses_caption_as_text(self) -> None:
        update = {
            "update_id": 2,
            "channel_post": {
                "message_id": 1002,
                "chat": {"id": "tg-channel-1", "type": "channel"},
                "date": 1710000001,
                "caption": "Photo caption",
                "photo": [
                    {"file_id": "small"},
                    {"file_id": "large"},
                ],
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNotNone(post)
        self.assertEqual(post.text, "Photo caption")
        self.assertEqual(len(post.payload["media"]), 2)
        self.assertEqual(post.payload["media"][0]["type"], "photo")

    def test_parses_media_group_id_for_album_posts(self) -> None:
        update = {
            "update_id": 3,
            "channel_post": {
                "message_id": 1003,
                "chat": {"id": "tg-channel-1", "type": "channel"},
                "date": 1710000002,
                "caption": "Album caption",
                "media_group_id": "album-42",
                "photo": [{"file_id": "photo-1"}],
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNotNone(post)
        self.assertEqual(post.media_group_id, "album-42")

    def test_parses_edited_channel_post_and_marks_it_as_edit_event(self) -> None:
        update = {
            "update_id": 7,
            "edited_channel_post": {
                "message_id": 1004,
                "chat": {"id": "tg-channel-1", "type": "channel"},
                "date": 1710000005,
                "edit_date": 1710000100,
                "text": "Edited text",
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNotNone(post)
        self.assertEqual(post.message_id, 1004)
        self.assertEqual(post.text, "Edited text")
        self.assertTrue(post.payload["is_edit"])
        self.assertEqual(post.payload["update_type"], "edited_channel_post")

    def test_ignores_updates_from_other_channels(self) -> None:
        update = {
            "update_id": 4,
            "channel_post": {
                "message_id": 2001,
                "chat": {"id": "foreign-channel", "type": "channel"},
                "date": 1710000003,
                "text": "Ignore me",
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNone(post)

    def test_ignores_non_channel_updates(self) -> None:
        update = {
            "update_id": 5,
            "message": {
                "message_id": 3001,
                "chat": {"id": "tg-channel-1", "type": "private"},
                "text": "Private chat",
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNone(post)

    def test_rejects_empty_or_unsupported_channel_posts(self) -> None:
        update = {
            "update_id": 6,
            "channel_post": {
                "message_id": 4001,
                "chat": {"id": "tg-channel-1", "type": "channel"},
                "date": 1710000004,
                "poll": {"question": "Question?"},
            },
        }

        post = self.adapter.parse_update(update)

        self.assertIsNone(post)


if __name__ == "__main__":
    unittest.main()
