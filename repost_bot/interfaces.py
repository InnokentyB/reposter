from __future__ import annotations

from typing import Protocol

from repost_bot.contracts import (
    AuditEvent,
    CanonicalPost,
    DeliveryJob,
    Destination,
    MetricsSnapshot,
    Platform,
    PublishResult,
    TelegramPost,
)


class TelegramNormalizerProtocol(Protocol):
    def normalize(self, post: TelegramPost) -> CanonicalPost:
        ...


class PlatformRendererProtocol(Protocol):
    def render(self, platform: Platform, post: CanonicalPost) -> dict:
        ...


class PublisherProtocol(Protocol):
    def publish(self, payload: dict) -> PublishResult:
        ...


class RepositoryProtocol(Protocol):
    def list_destinations(self) -> list[Destination]:
        ...

    def save_source_post(self, post: CanonicalPost) -> str:
        ...

    def save_delivery_jobs(self, jobs: list[DeliveryJob]) -> None:
        ...

    def save_audit_event(self, event: AuditEvent) -> None:
        ...


class MetricsProtocol(Protocol):
    def snapshot(self) -> MetricsSnapshot:
        ...

