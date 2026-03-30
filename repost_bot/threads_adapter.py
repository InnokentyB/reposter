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
MediaResolverFn = Callable[[str], str]


@dataclass(slots=True)
class ThreadsPublisher:
    credentials: PlatformCredentials
    transport: TransportFn | None = None
    media_resolver: MediaResolverFn | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            object.__setattr__(self, "transport", self._default_transport)

    def publish(self, payload: dict) -> PublishResult:
        request_payload = {
            "account_id": self.credentials.target_id,
            "access_token": self.credentials.access_token,
            "text": payload.get("text", ""),
            "media": payload.get("media", []),
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
            raise PermanentPublishError("threads response missing post_id")
        return PublishResult(
            remote_post_id=str(post_id),
            remote_permalink=response.get("permalink"),
        )

    def _default_transport(self, payload: dict) -> dict:
        request_fields = {
            "access_token": payload["access_token"],
        }
        media = payload.get("media") or []
        if media:
            if len(media) != 1 or media[0].get("type") != "photo":
                raise PermanentPublishError("Threads default media baseline supports only one photo")
            if self.media_resolver is None:
                raise PermanentPublishError(
                    "Threads media publishing requires public media_resolver configured with MEDIA_BASE_URL"
                )
            file_id = media[0].get("file_id")
            if not file_id:
                raise PermanentPublishError("Threads photo publish requires Telegram file_id")
            request_fields.update(
                {
                    "media_type": "IMAGE",
                    "image_url": self.media_resolver(file_id),
                    "text": payload.get("text", ""),
                }
            )
        else:
            request_fields.update(
                {
                    "media_type": "TEXT",
                    "text": payload.get("text", ""),
                }
            )

        account_id = payload["account_id"]
        create_request = urllib.request.Request(
            url=f"https://graph.threads.net/v1.0/{account_id}/threads",
            data=urllib.parse.urlencode(request_fields).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(create_request, timeout=30) as create_response:
            create_body = json.loads(create_response.read().decode("utf-8"))
        creation_id = create_body.get("id")
        if not creation_id:
            raise PermanentPublishError("threads create container response missing id")

        publish_request = urllib.request.Request(
            url=f"https://graph.threads.net/v1.0/{account_id}/threads_publish",
            data=urllib.parse.urlencode(
                {
                    "creation_id": creation_id,
                    "access_token": payload["access_token"],
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(publish_request, timeout=30) as publish_response:
            publish_body = json.loads(publish_response.read().decode("utf-8"))
        post_id = publish_body.get("id")
        if not post_id:
            raise PermanentPublishError("threads publish response missing id")
        return {
            "post_id": str(post_id),
        }
