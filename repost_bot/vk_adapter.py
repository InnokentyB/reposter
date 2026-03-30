from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import PublishResult
from repost_bot.errors import PermanentPublishError, TransientPublishError


TransportFn = Callable[[dict], dict]


@dataclass(slots=True)
class VkPublisher:
    credentials: PlatformCredentials
    transport: TransportFn

    def publish(self, payload: dict) -> PublishResult:
        request_payload = {
            "owner_id": self.credentials.target_id,
            "access_token": self.credentials.access_token,
            "message": payload.get("text", ""),
            "attachments": self._attachments_from_media(payload.get("media", [])),
        }
        try:
            response = self.transport(request_payload)
        except TransientPublishError:
            raise
        except PermanentPublishError:
            raise
        except Exception as exc:  # pragma: no cover - defensive mapping
            raise TransientPublishError(str(exc)) from exc

        post_id = response.get("post_id")
        if not post_id:
            raise PermanentPublishError("vk response missing post_id")
        return PublishResult(
            remote_post_id=str(post_id),
            remote_permalink=response.get("permalink"),
        )

    def _attachments_from_media(self, media: list[dict]) -> list[str]:
        attachments: list[str] = []
        for item in media:
            media_type = item.get("type")
            file_id = item.get("file_id")
            if media_type == "photo" and file_id:
                attachments.append(f"photo:{file_id}")
            elif media_type and file_id:
                attachments.append(f"{media_type}:{file_id}")
        return attachments
