from __future__ import annotations

import argparse
import json

from repost_bot.admin_cli import render_status_report
from repost_bot.config import AppConfig
from repost_bot.runtime import build_application
from repost_bot.storage import SqliteRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repost_bot")
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--database", dest="database_path")
    status_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)

    if args.command == "status":
        if args.database_path:
            repository = SqliteRepository(args.database_path)
        else:
            repository = SqliteRepository(AppConfig.from_env().database_path)
        print(render_status_report(repository, limit=args.limit))
        return 0

    app = build_application()
    summary = {
        "status": "ready",
        "environment": app.config.app_env,
        "log_level": app.config.log_level,
        "targets": {
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
