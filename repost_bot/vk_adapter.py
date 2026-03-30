from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import PublishResult
from repost_bot.errors import PermanentPublishError, TransientPublishError


TransportFn = Callable[[dict], dict]


@dataclass(slots=True)
class VkPublisher:
    credentials: PlatformCredentials
    transport: TransportFn | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            object.__setattr__(self, "transport", self._default_transport)

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

    def _default_transport(self, payload: dict) -> dict:
        if payload.get("attachments"):
            raise PermanentPublishError("VK media upload flow is not implemented for Telegram-origin media")

        encoded_payload = urllib.parse.urlencode(
            {
                "owner_id": payload["owner_id"],
                "access_token": payload["access_token"],
                "message": payload.get("message", ""),
                "v": "5.199",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url="https://api.vk.com/method/wall.post",
            data=encoded_payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))

        if "error" in body:
            error = body["error"]
            error_code = error.get("error_code")
            error_message = error.get("error_msg", "VK API error")
            if error_code in {6, 9, 10}:
                raise TransientPublishError(error_message)
            raise PermanentPublishError(error_message)

        response_data = body.get("response", {})
        post_id = response_data.get("post_id")
        if not post_id:
            raise PermanentPublishError("vk response missing post_id")
        return {
            "post_id": str(post_id),
            "permalink": f"https://vk.com/wall{payload['owner_id']}_{post_id}",
        }

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
