from __future__ import annotations

from datetime import datetime

from repost_bot.contracts import CanonicalPost, Platform, TelegramPost


class TelegramNormalizer:
    def normalize(self, post: TelegramPost) -> CanonicalPost:
        media = post.payload.get("media", [])
        normalized_payload = {
            "text": post.text,
            "media": list(media),
            "entities": post.payload.get("entities", []),
        }
        return CanonicalPost(
            source_platform=Platform.TELEGRAM,
            source_channel_id=post.chat_id,
            source_message_id=post.message_id,
            raw_payload=post.payload,
            normalized_payload=normalized_payload,
            content_hash=f"{post.chat_id}:{post.message_id}",
            published_at=datetime(2026, 3, 30, 8, 0, 0),
        )
