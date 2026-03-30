from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


def _read_env_file(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    if not os.path.exists(path):
        return data

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def _load_value(name: str, file_values: dict[str, str], default: str | None = None) -> str | None:
    return os.getenv(name, file_values.get(name, default))


def _require(name: str, file_values: dict[str, str]) -> str:
    value = _load_value(name, file_values)
    if value in (None, ""):
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def mask_secret(secret: str) -> str:
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


@dataclass(slots=True)
class PlatformCredentials:
    target_id: str
    access_token: str

    def masked(self) -> dict[str, str]:
        return {
            "target_id": self.target_id,
            "access_token": mask_secret(self.access_token),
        }


@dataclass(slots=True)
class AppConfig:
    app_env: str
    log_level: str
    telegram_channel_id: str
    telegram_bot_token: str
    vk: PlatformCredentials
    ok: PlatformCredentials
    threads: PlatformCredentials
    allowed_operators: tuple[str, ...]

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "AppConfig":
        file_values = _read_env_file(env_file)
        app_env = _load_value("APP_ENV", file_values, "dev")
        if app_env not in {"dev", "prod"}:
            raise ConfigurationError("APP_ENV must be one of: dev, prod")

        log_level = _load_value("LOG_LEVEL", file_values, "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ConfigurationError("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR")

        operators_raw = _load_value("ALLOWED_OPERATORS", file_values, "allowed-operator")
        allowed_operators = tuple(
            operator.strip() for operator in operators_raw.split(",") if operator.strip()
        )
        if not allowed_operators:
            raise ConfigurationError("ALLOWED_OPERATORS must contain at least one operator")

        return cls(
            app_env=app_env,
            log_level=log_level,
            telegram_channel_id=_require("TELEGRAM_CHANNEL_ID", file_values),
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN", file_values),
            vk=PlatformCredentials(
                target_id=_require("VK_COMMUNITY_ID", file_values),
                access_token=_require("VK_ACCESS_TOKEN", file_values),
            ),
            ok=PlatformCredentials(
                target_id=_require("OK_GROUP_ID", file_values),
                access_token=_require("OK_ACCESS_TOKEN", file_values),
            ),
            threads=PlatformCredentials(
                target_id=_require("THREADS_ACCOUNT_ID", file_values),
                access_token=_require("THREADS_ACCESS_TOKEN", file_values),
            ),
            allowed_operators=allowed_operators,
        )

    def masked(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "telegram_channel_id": self.telegram_channel_id,
            "telegram_bot_token": mask_secret(self.telegram_bot_token),
            "vk": self.vk.masked(),
            "ok": self.ok.masked(),
            "threads": self.threads.masked(),
            "allowed_operators": list(self.allowed_operators),
        }
