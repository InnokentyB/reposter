from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from repost_bot.config import PlatformCredentials
from repost_bot.contracts import PublishResult
from repost_bot.errors import PermanentPublishError, TransientPublishError


TransportFn = Callable[[dict], dict]


@dataclass(slots=True)
class OkPublisher:
    credentials: PlatformCredentials
    transport: TransportFn | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            object.__setattr__(self, "transport", self._default_transport)

    def publish(self, payload: dict) -> PublishResult:
        request_payload = {
            "group_id": self.credentials.target_id,
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
            raise PermanentPublishError("ok response missing post_id")
        return PublishResult(
            remote_post_id=str(post_id),
            remote_permalink=response.get("permalink"),
        )

    def _default_transport(self, payload: dict) -> dict:
        raise PermanentPublishError(
            "Official Odnoklassniki group publishing requires WidgetMediatopicPost user flow; "
            "server-side automatic posting is not configured in this baseline"
        )
