from __future__ import annotations

from datetime import datetime, timedelta

from repost_bot.contracts import (
    CanonicalPost,
    DeliveryJob,
    DeliveryStatus,
    Destination,
    DestinationStatus,
    MetricsSnapshot,
    Platform,
    TelegramPost,
)


def telegram_post(**overrides) -> TelegramPost:
    payload = {
        "chat_id": "tg-channel-1",
        "message_id": 101,
        "text": "Hello from Telegram",
        "entities": [],
    }
    payload.update(overrides.pop("payload", {}))
    return TelegramPost(
        chat_id=overrides.pop("chat_id", "tg-channel-1"),
        message_id=overrides.pop("message_id", 101),
        text=overrides.pop("text", "Hello from Telegram"),
        payload=payload,
        media_group_id=overrides.pop("media_group_id", None),
    )


def canonical_post(**overrides) -> CanonicalPost:
    return CanonicalPost(
        source_platform=overrides.pop("source_platform", Platform.TELEGRAM),
        source_channel_id=overrides.pop("source_channel_id", "tg-channel-1"),
        source_message_id=overrides.pop("source_message_id", 101),
        raw_payload=overrides.pop("raw_payload", {"text": "Hello from Telegram"}),
        normalized_payload=overrides.pop(
            "normalized_payload",
            {"text": "Hello from Telegram", "media": []},
        ),
        content_hash=overrides.pop("content_hash", "hash-101"),
        published_at=overrides.pop("published_at", datetime(2026, 3, 30, 8, 0, 0)),
    )


def destination(platform: Platform, **overrides) -> Destination:
    return Destination(
        id=overrides.pop("id", f"{platform.value}-destination"),
        platform=platform,
        target_id=overrides.pop("target_id", f"{platform.value}-target"),
        status=overrides.pop("status", DestinationStatus.ACTIVE),
        config_ref=overrides.pop("config_ref", f"{platform.value}-config"),
    )


def delivery_job(**overrides) -> DeliveryJob:
    return DeliveryJob(
        id=overrides.pop("id", "job-1"),
        source_post_id=overrides.pop("source_post_id", "source-101"),
        destination_id=overrides.pop("destination_id", "vk-destination"),
        status=overrides.pop("status", DeliveryStatus.PENDING),
        attempt_count=overrides.pop("attempt_count", 0),
        next_attempt_at=overrides.pop(
            "next_attempt_at",
            datetime(2026, 3, 30, 8, 0, 0) + timedelta(minutes=5),
        ),
        last_error_code=overrides.pop("last_error_code", None),
        last_error_message=overrides.pop("last_error_message", None),
    )


def metrics_snapshot(**overrides) -> MetricsSnapshot:
    return MetricsSnapshot(
        success_count=overrides.pop("success_count", 0),
        error_count=overrides.pop("error_count", 0),
        retry_count=overrides.pop("retry_count", 0),
        queue_depth=overrides.pop("queue_depth", 0),
        extra=overrides.pop("extra", {}),
    )

