from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from repost_bot.telegram_adapter import TelegramUpdateAdapter


TransportFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def _default_transport(bot_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    encoded_payload = urllib.parse.urlencode(
        {
            key: json.dumps(value) if isinstance(value, (list, dict)) else value
            for key, value in payload.items()
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url=f"https://api.telegram.org/bot{bot_token}/{method}",
        data=encoded_payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=payload.get("timeout", 30) + 5) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass(slots=True)
class TelegramBotApiClient:
    bot_token: str
    transport: TransportFn | None = None
    poll_timeout_seconds: int = 30
    next_offset: int = 0

    def __post_init__(self) -> None:
        if self.transport is None:
            object.__setattr__(
                self,
                "transport",
                lambda method, payload: _default_transport(self.bot_token, method, payload),
            )

    def get_updates(self) -> list[dict[str, Any]]:
        response = self.transport(
            "getUpdates",
            {
                "offset": self.next_offset,
                "timeout": self.poll_timeout_seconds,
                "allowed_updates": ["channel_post", "edited_channel_post"],
            },
        )
        if not response.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {response}")

        updates = response.get("result", [])
        if updates:
            highest_update_id = max(int(update.get("update_id", 0)) for update in updates)
            self.next_offset = highest_update_id + 1
        return updates


@dataclass(slots=True)
class TelegramPollingLoop:
    client: TelegramBotApiClient
    adapter: TelegramUpdateAdapter
    orchestrator: Any
    delivery_worker: Any
    delivery_batch_limit: int = 100
    poll_interval_seconds: int = 2
    sleep_fn: Callable[[float], None] = field(default=time.sleep, repr=False)

    def run_once(self) -> dict[str, Any]:
        updates = self.client.get_updates()
        posts_ingested = 0
        for update in updates:
            post = self.adapter.parse_update(update)
            if post is None:
                continue
            result = self.orchestrator.ingest_telegram_post(post)
            if result not in {"duplicate_ignored", "validation_failed", "edit_ignored"}:
                posts_ingested += 1

        delivery_results: list[str] = []
        if posts_ingested > 0:
            delivery_results = self.delivery_worker.process_due_jobs(limit=self.delivery_batch_limit)

        return {
            "updates_received": len(updates),
            "posts_ingested": posts_ingested,
            "delivery_results": delivery_results,
        }

    def run_forever(self) -> None:
        while True:
            self.run_once()
            self.sleep_fn(self.poll_interval_seconds)
