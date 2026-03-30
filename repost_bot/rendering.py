from __future__ import annotations

import re

from repost_bot.contracts import CanonicalPost, Platform


class PlatformRenderer:
    def render(self, platform: Platform, post: CanonicalPost) -> dict:
        text = self._normalize_text(post.normalized_payload.get("text", ""))
        media = post.normalized_payload.get("media", [])

        if any(item.get("type") == "poll" for item in media if isinstance(item, dict)):
            return {"error_code": "content_not_supported", "platform": platform.value}

        text_limits = {
            Platform.VK: 50000,
            Platform.OK: 20000,
            Platform.THREADS: 500,
        }
        limit = text_limits.get(platform, 50000)
        if len(text) > limit:
            return {"error_code": "content_not_supported", "platform": platform.value}

        if not self._media_supported(platform, media):
            return {"error_code": "content_not_supported", "platform": platform.value}

        return {
            "platform": platform.value,
            "text": text,
            "media": media,
        }

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _media_supported(self, platform: Platform, media: list[dict]) -> bool:
        media_types = [item.get("type") for item in media if isinstance(item, dict)]

        if platform == Platform.OK:
            return all(media_type in {"photo"} for media_type in media_types)

        if platform == Platform.THREADS:
            if len(media_types) > 1:
                return False
            return all(media_type in {"photo"} for media_type in media_types)

        if platform == Platform.VK:
            return all(media_type in {"photo", "video"} for media_type in media_types)

        return True
