from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from repost_bot.admin_cli import render_audit_report
from repost_bot.service import RepostOrchestrator
from repost_bot.storage import SqliteRepository


class AuditCliTests(unittest.TestCase):
    def test_authorized_operator_can_disable_destination_and_audit_action(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "audit.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(
                repository=repository,
                allowed_operators={"allowed-operator"},
            )

            result = orchestrator.disable_destination("ok-destination", actor="allowed-operator")

            self.assertEqual(result, "disabled")
            self.assertEqual(repository.get_destination("ok-destination")["status"], "disabled")
            self.assertEqual(repository.count_rows("audit_events"), 1)

    def test_authorized_operator_can_remap_target_and_audit_action(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "audit.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(
                repository=repository,
                allowed_operators={"allowed-operator"},
            )

            result = orchestrator.remap_destination_target(
                "vk-destination",
                target_id="vk-community-99",
                actor="allowed-operator",
            )

            self.assertEqual(result, "remapped")
            self.assertEqual(repository.get_destination("vk-destination")["target_id"], "vk-community-99")
            self.assertEqual(repository.count_rows("audit_events"), 1)

    def test_rotate_token_records_safe_audit_event_without_storing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = SqliteRepository(os.path.join(tempdir, "audit.sqlite3"))
            repository.seed_default_destinations(threads_enabled=False)
            orchestrator = RepostOrchestrator(
                repository=repository,
                allowed_operators={"allowed-operator"},
            )

            result = orchestrator.record_token_rotation(
                config_ref="vk-config",
                actor="allowed-operator",
                token_hint="super-secret-token",
            )

            self.assertEqual(result, "rotation_recorded")
            report = render_audit_report(repository, limit=10)
            self.assertIn("rotate_token", report)
            self.assertIn("rotation_recorded", report)
            self.assertNotIn("super-secret-token", report)

    def test_audit_commands_work_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = os.path.join(tempdir, "audit.sqlite3")
            repository = SqliteRepository(database_path)
            repository.seed_default_destinations(threads_enabled=False)

            from repost_bot.__main__ import main

            disable_buffer = io.StringIO()
            with redirect_stdout(disable_buffer):
                disable_exit = main(
                    [
                        "disable-destination",
                        "--database",
                        database_path,
                        "--destination-id",
                        "ok-destination",
                        "--actor",
                        "allowed-operator",
                    ]
                )

            remap_buffer = io.StringIO()
            with redirect_stdout(remap_buffer):
                remap_exit = main(
                    [
                        "remap-target",
                        "--database",
                        database_path,
                        "--destination-id",
                        "vk-destination",
                        "--target-id",
                        "vk-community-55",
                        "--actor",
                        "allowed-operator",
                    ]
                )

            rotate_buffer = io.StringIO()
            with redirect_stdout(rotate_buffer):
                rotate_exit = main(
                    [
                        "rotate-token",
                        "--database",
                        database_path,
                        "--config-ref",
                        "ok-config",
                        "--actor",
                        "allowed-operator",
                    ]
                )

            audit_buffer = io.StringIO()
            with redirect_stdout(audit_buffer):
                audit_exit = main(["audit-log", "--database", database_path, "--limit", "10"])

            self.assertEqual(disable_exit, 0)
            self.assertEqual(remap_exit, 0)
            self.assertEqual(rotate_exit, 0)
            self.assertEqual(audit_exit, 0)
            self.assertIn("disabled", disable_buffer.getvalue())
            self.assertIn("remapped", remap_buffer.getvalue())
            self.assertIn("rotation_recorded", rotate_buffer.getvalue())
            self.assertIn("Audit Log", audit_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
