from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repost_bot.contracts import TelegramPost


@dataclass(slots=True)
class TelegramUpdateAdapter:
    expected_channel_id: str

    def parse_update(self, update: dict[str, Any]) -> TelegramPost | None:
        update_type = "channel_post"
        channel_post = update.get("channel_post")
        if not isinstance(channel_post, dict):
            update_type = "edited_channel_post"
            channel_post = update.get("edited_channel_post")
        if not isinstance(channel_post, dict):
            return None

        chat = channel_post.get("chat", {})
        if chat.get("type") != "channel":
            return None

        chat_id = str(chat.get("id"))
        if chat_id != self.expected_channel_id:
            return None

        message_id = channel_post.get("message_id")
        if not isinstance(message_id, int):
            return None

        text = channel_post.get("text") or channel_post.get("caption") or ""
        media = self._extract_media(channel_post)
        entities = channel_post.get("entities") or channel_post.get("caption_entities") or []

        if not text and not media:
            return None

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "entities": entities,
            "media": media,
            "date": channel_post.get("date"),
            "edit_date": channel_post.get("edit_date"),
            "is_edit": update_type == "edited_channel_post",
            "update_type": update_type,
        }

        return TelegramPost(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            payload=payload,
            media_group_id=channel_post.get("media_group_id"),
        )

    def _extract_media(self, channel_post: dict[str, Any]) -> list[dict[str, Any]]:
        media: list[dict[str, Any]] = []

        for photo in channel_post.get("photo", []):
            file_id = photo.get("file_id")
            if file_id:
                media.append({"type": "photo", "file_id": file_id})

        video = channel_post.get("video")
        if isinstance(video, dict) and video.get("file_id"):
            media.append({"type": "video", "file_id": video["file_id"]})

        return media
