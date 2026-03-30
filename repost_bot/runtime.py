from __future__ import annotations

from dataclasses import dataclass

from repost_bot.config import AppConfig
from repost_bot.service import DeliveryWorker, HealthService, RepostOrchestrator


@dataclass(slots=True)
class Application:
    config: AppConfig
    orchestrator: RepostOrchestrator
    delivery_worker: DeliveryWorker
    health_service: HealthService


def build_application(config: AppConfig | None = None) -> Application:
    resolved_config = config or AppConfig.from_env()
    orchestrator = RepostOrchestrator(allowed_operators=set(resolved_config.allowed_operators))
    return Application(
        config=resolved_config,
        orchestrator=orchestrator,
        delivery_worker=DeliveryWorker(),
        health_service=HealthService(),
    )
