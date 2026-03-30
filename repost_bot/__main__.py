from __future__ import annotations

import argparse
import json

from repost_bot.admin_cli import render_audit_report, render_dead_letter_report, render_status_report
from repost_bot.config import AppConfig
from repost_bot.runtime import build_application
from repost_bot.service import HealthService, RepostOrchestrator
from repost_bot.storage import SqliteRepository
from repost_bot.telegram_poller import TelegramPollingLoop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repost_bot")
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--database", dest="database_path")
    status_parser.add_argument("--limit", type=int, default=20)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--database", dest="database_path")

    poller_parser = subparsers.add_parser("run-poller")
    poller_parser.add_argument("--once", action="store_true")

    dead_letter_parser = subparsers.add_parser("dead-letter")
    dead_letter_parser.add_argument("--database", dest="database_path")
    dead_letter_parser.add_argument("--limit", type=int, default=20)

    audit_parser = subparsers.add_parser("audit-log")
    audit_parser.add_argument("--database", dest="database_path")
    audit_parser.add_argument("--limit", type=int, default=20)

    retry_parser = subparsers.add_parser("retry-job")
    retry_parser.add_argument("--database", dest="database_path")
    retry_parser.add_argument("--job-id", required=True)
    retry_parser.add_argument("--actor", required=True)

    disable_parser = subparsers.add_parser("disable-destination")
    disable_parser.add_argument("--database", dest="database_path")
    disable_parser.add_argument("--destination-id", required=True)
    disable_parser.add_argument("--actor", required=True)

    remap_parser = subparsers.add_parser("remap-target")
    remap_parser.add_argument("--database", dest="database_path")
    remap_parser.add_argument("--destination-id", required=True)
    remap_parser.add_argument("--target-id", required=True)
    remap_parser.add_argument("--actor", required=True)

    rotate_parser = subparsers.add_parser("rotate-token")
    rotate_parser.add_argument("--database", dest="database_path")
    rotate_parser.add_argument("--config-ref", required=True)
    rotate_parser.add_argument("--actor", required=True)

    backfill_parser = subparsers.add_parser("backfill")
    backfill_parser.add_argument("--database", dest="database_path")
    backfill_parser.add_argument("--start-message-id", type=int, required=True)
    backfill_parser.add_argument("--end-message-id", type=int, required=True)
    backfill_parser.add_argument("--channel-id")
    backfill_parser.add_argument("--actor", required=True)

    args = parser.parse_args(argv)

    if args.command == "status":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        print(render_status_report(repository, limit=args.limit))
        return 0

    if args.command == "health":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        print(json.dumps(HealthService(repository=repository).status(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-poller":
        app = build_application(AppConfig.from_env())
        poller = TelegramPollingLoop(
            client=app.telegram_client,
            adapter=app.telegram_adapter,
            orchestrator=app.orchestrator,
            delivery_worker=app.delivery_worker,
            delivery_batch_limit=app.config.delivery_batch_limit,
            poll_interval_seconds=app.config.telegram_poll_interval_seconds,
        )
        if args.once:
            print(json.dumps(poller.run_once(), ensure_ascii=False, indent=2))
            return 0
        try:
            poller.run_forever()
        except KeyboardInterrupt:
            print("poller_stopped")
        return 0

    if args.command == "dead-letter":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        print(render_dead_letter_report(repository, limit=args.limit))
        return 0

    if args.command == "audit-log":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        print(render_audit_report(repository, limit=args.limit))
        return 0

    if args.command == "retry-job":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        orchestrator = RepostOrchestrator(
            repository=repository,
            allowed_operators=set(AppConfig.from_env().allowed_operators)
            if not args.database_path
            else {"allowed-operator"},
        )
        result = orchestrator.retry_delivery_job(args.job_id, actor=args.actor)
        print(result)
        return 0

    if args.command == "disable-destination":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
            repository.seed_default_destinations(threads_enabled=False)
            allowed_operators = {"allowed-operator"}
        else:
            config = AppConfig.from_env()
            repository = SqliteRepository(config.database_path)
            repository.seed_default_destinations(threads_enabled=config.threads_enabled)
            allowed_operators = set(config.allowed_operators)
        orchestrator = RepostOrchestrator(repository=repository, allowed_operators=allowed_operators)
        print(orchestrator.disable_destination(args.destination_id, actor=args.actor))
        return 0

    if args.command == "remap-target":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
            repository.seed_default_destinations(threads_enabled=False)
            allowed_operators = {"allowed-operator"}
        else:
            config = AppConfig.from_env()
            repository = SqliteRepository(config.database_path)
            repository.seed_default_destinations(threads_enabled=config.threads_enabled)
            allowed_operators = set(config.allowed_operators)
        orchestrator = RepostOrchestrator(repository=repository, allowed_operators=allowed_operators)
        print(
            orchestrator.remap_destination_target(
                args.destination_id,
                target_id=args.target_id,
                actor=args.actor,
            )
        )
        return 0

    if args.command == "rotate-token":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
            allowed_operators = {"allowed-operator"}
        else:
            config = AppConfig.from_env()
            repository = SqliteRepository(config.database_path)
            allowed_operators = set(config.allowed_operators)
        orchestrator = RepostOrchestrator(repository=repository, allowed_operators=allowed_operators)
        print(orchestrator.record_token_rotation(args.config_ref, actor=args.actor))
        return 0

    if args.command == "backfill":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
            allowed_operators = {"allowed-operator"}
        else:
            config = AppConfig.from_env()
            repository = SqliteRepository(config.database_path)
            allowed_operators = set(config.allowed_operators)
        orchestrator = RepostOrchestrator(
            repository=repository,
            allowed_operators=allowed_operators,
            default_source_channel_id=config.telegram_channel_id if not args.database_path else "tg-channel-1",
        )
        created = orchestrator.trigger_backfill(
            start_message_id=args.start_message_id,
            end_message_id=args.end_message_id,
            actor=args.actor,
            source_channel_id=args.channel_id,
        )
        print(json.dumps({"created": created}, ensure_ascii=False, indent=2))
        return 0

    app = build_application()
    summary = {
        "status": "ready",
        "environment": app.config.app_env,
        "log_level": app.config.log_level,
        "targets": {
            "telegram_channel_ids": list(app.config.telegram_channel_ids),
            "telegram_channel_id": app.config.telegram_channel_id,
            "vk_target_id": app.config.vk.target_id,
            "ok_target_id": app.config.ok.target_id,
            "threads_target_id": app.config.threads.target_id,
        },
        "allowed_operators": list(app.config.allowed_operators),
        "masked_config": app.config.masked(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
