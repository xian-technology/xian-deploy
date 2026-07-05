from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class MonitoringSecurityTest(unittest.TestCase):
    def test_monitoring_compose_does_not_enable_prometheus_lifecycle(self) -> None:
        template = (
            REPO_ROOT
            / "roles"
            / "xian_runtime"
            / "templates"
            / "docker-compose.monitoring.yml.j2"
        )

        self.assertNotIn("--web.enable-lifecycle", template.read_text(encoding="utf-8"))

    def test_public_monitoring_requires_opt_in_and_auth_confirmation(self) -> None:
        profile_tasks = REPO_ROOT / "roles" / "xian_profile" / "tasks" / "main.yml"
        source = profile_tasks.read_text(encoding="utf-8")

        self.assertIn("xian_public_monitoring_enabled | bool", source)
        self.assertIn("xian_monitoring_public_auth_confirmed | bool", source)
        self.assertIn("xian_loopback_bind_hosts", source)

    def test_public_monitoring_defaults_are_closed(self) -> None:
        defaults = REPO_ROOT / "roles" / "xian_profile" / "defaults" / "main.yml"
        example = REPO_ROOT / "inventories" / "example" / "group_vars" / "all" / "main.yml"

        for path in (defaults, example):
            source = path.read_text(encoding="utf-8")
            self.assertIn("xian_public_monitoring_enabled: false", source)
            self.assertIn("xian_monitoring_public_auth_confirmed: false", source)


if __name__ == "__main__":
    unittest.main()
