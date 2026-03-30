from __future__ import annotations

import json

from repost_bot.runtime import build_application


def main() -> int:
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
