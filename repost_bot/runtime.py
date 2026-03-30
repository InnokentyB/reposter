from __future__ import annotations

from dataclasses import dataclass

from repost_bot.config import AppConfig
from repost_bot.contracts import Platform
from repost_bot.ok_adapter import OkPublisher
from repost_bot.service import DeliveryWorker, HealthService, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from repost_bot.telegram_adapter import TelegramUpdateAdapter
from repost_bot.telegram_poller import TelegramBotApiClient, TelegramPollingLoop
from repost_bot.threads_adapter import ThreadsPublisher
from repost_bot.vk_adapter import VkPublisher


@dataclass(slots=True)
class Application:
    config: AppConfig
    repository: SqliteRepository
    telegram_adapter: TelegramUpdateAdapter
    telegram_client: TelegramBotApiClient
    telegram_poller: TelegramPollingLoop
    orchestrator: RepostOrchestrator
    delivery_worker: DeliveryWorker
    health_service: HealthService


def build_application(config: AppConfig | None = None) -> Application:
    resolved_config = config or AppConfig.from_env()
    repository = SqliteRepository(resolved_config.database_path)
    repository.seed_default_destinations(threads_enabled=resolved_config.threads_enabled)
    telegram_adapter = TelegramUpdateAdapter(expected_channel_ids=resolved_config.telegram_channel_ids)
    orchestrator = RepostOrchestrator(
        allowed_operators=set(resolved_config.allowed_operators),
        default_source_channel_id=resolved_config.telegram_channel_id,
        repository=repository,
    )
    publishers = {
        Platform.VK: VkPublisher(credentials=resolved_config.vk),
        Platform.OK: OkPublisher(credentials=resolved_config.ok),
    }
    if resolved_config.threads_enabled:
        publishers[Platform.THREADS] = ThreadsPublisher(credentials=resolved_config.threads)
    delivery_worker = DeliveryWorker(repository=repository, publishers=publishers)
    telegram_client = TelegramBotApiClient(
        bot_token=resolved_config.telegram_bot_token,
        poll_timeout_seconds=resolved_config.telegram_poll_timeout_seconds,
    )
    telegram_poller = TelegramPollingLoop(
        client=telegram_client,
        adapter=telegram_adapter,
        orchestrator=orchestrator,
        delivery_worker=delivery_worker,
        delivery_batch_limit=resolved_config.delivery_batch_limit,
        poll_interval_seconds=resolved_config.telegram_poll_interval_seconds,
    )
    return Application(
        config=resolved_config,
        repository=repository,
        telegram_adapter=telegram_adapter,
        telegram_client=telegram_client,
        telegram_poller=telegram_poller,
        orchestrator=orchestrator,
        delivery_worker=delivery_worker,
        health_service=HealthService(repository=repository),
    )
