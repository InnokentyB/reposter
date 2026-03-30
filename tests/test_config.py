from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from repost_bot.config import AppConfig, ConfigurationError, mask_secret
from repost_bot.runtime import build_application


class ConfigTests(unittest.TestCase):
    def _env_payload(self) -> str:
        return "\n".join(
            [
                "APP_ENV=dev",
                "LOG_LEVEL=INFO",
                "DATABASE_PATH=var/repost-bot.sqlite3",
                "THREADS_ENABLED=false",
                "TELEGRAM_CHANNEL_ID=tg-channel-1",
                "TELEGRAM_BOT_TOKEN=telegram-secret-123",
                "VK_COMMUNITY_ID=vk-community-1",
                "VK_ACCESS_TOKEN=vk-secret-456",
                "OK_GROUP_ID=ok-group-1",
                "OK_ACCESS_TOKEN=ok-secret-789",
                "THREADS_ACCOUNT_ID=threads-account-1",
                "THREADS_ACCESS_TOKEN=threads-secret-000",
                "ALLOWED_OPERATORS=allowed-operator,backup-operator",
            ]
        )

    def test_config_loads_from_env_file_and_supports_dev_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = os.path.join(tempdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(self._env_payload())

            config = AppConfig.from_env(env_path)

        self.assertEqual(config.app_env, "dev")
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.database_path, "var/repost-bot.sqlite3")
        self.assertFalse(config.threads_enabled)
        self.assertEqual(config.allowed_operators, ("allowed-operator", "backup-operator"))
        self.assertEqual(config.vk.target_id, "vk-community-1")

    def test_env_variables_override_env_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = os.path.join(tempdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(self._env_payload())

            with patch.dict(os.environ, {"APP_ENV": "prod", "LOG_LEVEL": "DEBUG"}, clear=False):
                config = AppConfig.from_env(env_path)

        self.assertEqual(config.app_env, "prod")
        self.assertEqual(config.log_level, "DEBUG")

    def test_config_raises_when_required_secret_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = os.path.join(tempdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("APP_ENV=dev\n")

            with self.assertRaises(ConfigurationError):
                AppConfig.from_env(env_path)

    def test_masked_config_hides_sensitive_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = os.path.join(tempdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(self._env_payload())

            config = AppConfig.from_env(env_path)

        masked = config.masked()
        self.assertNotIn("telegram-secret-123", str(masked))
        self.assertTrue(str(masked["telegram_bot_token"]).startswith("te"))

    def test_build_application_uses_configured_allowed_operators(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = os.path.join(tempdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(self._env_payload())

            config = AppConfig.from_env(env_path)
            app = build_application(config)

        self.assertIn("backup-operator", app.orchestrator.allowed_operators)

    def test_mask_secret_keeps_only_prefix_and_suffix_visible(self) -> None:
        self.assertEqual(mask_secret("abcd"), "****")
        self.assertEqual(mask_secret("abcdef"), "ab**ef")


if __name__ == "__main__":
    unittest.main()
