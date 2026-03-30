from __future__ import annotations

from dataclasses import dataclass

from repost_bot.config import AppConfig
from repost_bot.service import DeliveryWorker, HealthService, RepostOrchestrator
from repost_bot.storage import SqliteRepository


@dataclass(slots=True)
class Application:
    config: AppConfig
    repository: SqliteRepository
    orchestrator: RepostOrchestrator
    delivery_worker: DeliveryWorker
    health_service: HealthService


def build_application(config: AppConfig | None = None) -> Application:
    resolved_config = config or AppConfig.from_env()
    repository = SqliteRepository(resolved_config.database_path)
    repository.seed_default_destinations()
    orchestrator = RepostOrchestrator(
        allowed_operators=set(resolved_config.allowed_operators),
        repository=repository,
    )
    return Application(
        config=resolved_config,
        repository=repository,
        orchestrator=orchestrator,
        delivery_worker=DeliveryWorker(),
        health_service=HealthService(),
    )
