from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Platform(str, Enum):
    TELEGRAM = "telegram"
    VK = "vk"
    OK = "ok"
    THREADS = "threads"


class DestinationStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    SKIPPED = "skipped"


@dataclass(slots=True)
class TelegramPost:
    chat_id: str
    message_id: int
    text: str
    payload: dict[str, Any]
    media_group_id: str | None = None


@dataclass(slots=True)
class CanonicalPost:
    source_platform: Platform
    source_channel_id: str
    source_message_id: int
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]
    content_hash: str
    published_at: datetime | None = None


@dataclass(slots=True)
class Destination:
    id: str
    platform: Platform
    target_id: str
    status: DestinationStatus
    config_ref: str | None = None


@dataclass(slots=True)
class DeliveryJob:
    id: str
    source_post_id: str
    destination_id: str
    status: DeliveryStatus
    attempt_count: int = 0
    next_attempt_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


@dataclass(slots=True)
class PublishedPost:
    delivery_job_id: str
    remote_post_id: str
    remote_permalink: str | None = None
    published_at: datetime | None = None


@dataclass(slots=True)
class AuditEvent:
    actor: str
    action: str
    target_type: str
    target_id: str
    result: str
    created_at: datetime | None = None


@dataclass(slots=True)
class PublishResult:
    remote_post_id: str
    remote_permalink: str | None = None


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int
    jitter_seconds: int = 0


@dataclass(slots=True)
class MetricsSnapshot:
    success_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    queue_depth: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

