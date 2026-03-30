from __future__ import annotations

import json
import uuid
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import PublishResult
from repost_bot.errors import PermanentPublishError, TransientPublishError


TransportFn = Callable[[dict], dict]
MediaResolverFn = Callable[[str], dict[str, Any]]


@dataclass(slots=True)
class VkPublisher:
    credentials: PlatformCredentials
    transport: TransportFn | None = None
    media_resolver: MediaResolverFn | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            object.__setattr__(self, "transport", self._default_transport)

    def publish(self, payload: dict) -> PublishResult:
        request_payload = {
            "owner_id": self.credentials.target_id,
            "access_token": self.credentials.access_token,
            "message": payload.get("text", ""),
            "media": payload.get("media", []),
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
        attachments = payload.get("attachments") or []
        if attachments:
            attachment_tokens = self._upload_media(payload.get("media", []))
            return self._post_to_wall(payload, attachment_tokens)

        return self._post_to_wall(payload, [])

    def _post_to_wall(self, payload: dict, attachment_tokens: list[str]) -> dict:
        encoded_payload = urllib.parse.urlencode(
            {
                "owner_id": self._wall_owner_id(),
                "access_token": payload["access_token"],
                "message": payload.get("message", ""),
                "attachments": ",".join(attachment_tokens),
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
            "permalink": f"https://vk.com/wall{self._wall_owner_id()}_{post_id}",
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

    def _upload_media(self, media: list[dict]) -> list[str]:
        if self.media_resolver is None:
            raise PermanentPublishError("VK media upload requires configured media_resolver")
        attachment_tokens: list[str] = []
        for item in media:
            media_type = item.get("type")
            if media_type != "photo":
                raise PermanentPublishError("VK default media upload baseline supports only photos")
            file_id = item.get("file_id")
            if not file_id:
                raise PermanentPublishError("VK photo upload requires Telegram file_id")
            attachment_tokens.append(self._upload_photo(file_id))
        return attachment_tokens

    def _upload_photo(self, file_id: str) -> str:
        media_file = self.media_resolver(file_id)
        upload_url = self._get_wall_upload_url()
        upload_response = self._upload_photo_bytes(upload_url, media_file)
        save_response = self._save_wall_photo(upload_response)
        owner_id = save_response.get("owner_id")
        photo_id = save_response.get("id")
        if owner_id is None or photo_id is None:
            raise PermanentPublishError("VK saveWallPhoto response missing owner_id or id")
        return f"photo{owner_id}_{photo_id}"

    def _get_wall_upload_url(self) -> str:
        encoded_payload = urllib.parse.urlencode(
            {
                "group_id": self._group_id(),
                "access_token": self.credentials.access_token,
                "v": "5.199",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url="https://api.vk.com/method/photos.getWallUploadServer",
            data=encoded_payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        if "error" in body:
            raise PermanentPublishError(body["error"].get("error_msg", "VK upload server error"))
        upload_url = body.get("response", {}).get("upload_url")
        if not upload_url:
            raise PermanentPublishError("VK getWallUploadServer response missing upload_url")
        return str(upload_url)

    def _upload_photo_bytes(self, upload_url: str, media_file: dict[str, Any]) -> dict[str, Any]:
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="{media_file["filename"]}"\r\n'
            f'Content-Type: {media_file["content_type"]}\r\n\r\n'
        ).encode("utf-8") + media_file["content"] + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            url=upload_url,
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def _save_wall_photo(self, upload_response: dict[str, Any]) -> dict[str, Any]:
        encoded_payload = urllib.parse.urlencode(
            {
                "group_id": self._group_id(),
                "server": upload_response.get("server"),
                "photo": upload_response.get("photo"),
                "hash": upload_response.get("hash"),
                "access_token": self.credentials.access_token,
                "v": "5.199",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url="https://api.vk.com/method/photos.saveWallPhoto",
            data=encoded_payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        if "error" in body:
            raise PermanentPublishError(body["error"].get("error_msg", "VK saveWallPhoto error"))
        response_items = body.get("response") or []
        if not response_items:
            raise PermanentPublishError("VK saveWallPhoto response missing photo item")
        return response_items[0]

    def _group_id(self) -> str:
        raw_target_id = str(self.credentials.target_id)
        normalized = raw_target_id.lstrip("-")
        if not normalized.isdigit():
            raise PermanentPublishError("VK target_id must be numeric community id for live API mode")
        return normalized

    def _wall_owner_id(self) -> str:
        return f"-{self._group_id()}"
