from __future__ import annotations

from repost_bot.contracts import CanonicalPost, Platform


class PlatformRenderer:
    def render(self, platform: Platform, post: CanonicalPost) -> dict:
        text = post.normalized_payload.get("text", "")
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

        return {
            "platform": platform.value,
            "text": text,
            "media": media,
        }
