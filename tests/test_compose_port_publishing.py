from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ComposePortPublishingTest(unittest.TestCase):
    def test_compose_ports_use_long_syntax_for_bind_hosts(self) -> None:
        templates = [
            REPO_ROOT / "roles" / "xian_runtime" / "templates" / "docker-compose.yml.j2",
            REPO_ROOT
            / "roles"
            / "xian_runtime"
            / "templates"
            / "docker-compose.monitoring.yml.j2",
        ]

        for template in templates:
            source = template.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"xian_[a-z_]*bind_host\s*~\s*':'")

        combined = "\n".join(template.read_text(encoding="utf-8") for template in templates)
        for bind_var in (
            "xian_rpc_bind_host",
            "xian_p2p_bind_host",
            "xian_comet_metrics_bind_host",
            "xian_app_metrics_bind_host",
            "xian_dashboard_bind_host",
            "xian_prometheus_bind_host",
            "xian_grafana_bind_host",
        ):
            self.assertIn(
                f"host_ip: {{{{ ({bind_var} | string | regex_replace",
                combined,
            )

    def test_long_port_entries_keep_expected_published_ports(self) -> None:
        main_template = (
            REPO_ROOT / "roles" / "xian_runtime" / "templates" / "docker-compose.yml.j2"
        ).read_text(encoding="utf-8")
        monitoring_template = (
            REPO_ROOT
            / "roles"
            / "xian_runtime"
            / "templates"
            / "docker-compose.monitoring.yml.j2"
        ).read_text(encoding="utf-8")

        for expected in (
            "published: {{ (xian_rpc_port | string) | to_json }}",
            "published: {{ (xian_p2p_port | string) | to_json }}",
            "published: {{ (xian_comet_metrics_port | string) | to_json }}",
            "published: {{ (xian_metrics_port | string) | to_json }}",
            "published: {{ (xian_dashboard_port | string) | to_json }}",
        ):
            self.assertIn(expected, main_template)

        for expected in (
            "published: {{ (xian_prometheus_port | string) | to_json }}",
            "published: {{ (xian_grafana_port | string) | to_json }}",
        ):
            self.assertIn(expected, monitoring_template)

        self.assertGreaterEqual(len(re.findall(r"^\s+- target:", main_template, re.MULTILINE)), 8)
        self.assertEqual(
            len(re.findall(r"^\s+- target:", monitoring_template, re.MULTILINE)),
            2,
        )

    def test_monitoring_loopback_validation_normalizes_ipv6_hosts(self) -> None:
        source = (
            REPO_ROOT / "roles" / "xian_profile" / "tasks" / "main.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("xian_normalized_prometheus_bind_host", source)
        self.assertIn("xian_normalized_grafana_bind_host", source)
        self.assertIn("regex_replace('^\\\\[(.*)\\\\]$', '\\\\1') | lower", source)
        for loopback_host in (
            '"::1"',
            '"0:0:0:0:0:0:0:1"',
            '"0000:0000:0000:0000:0000:0000:0000:0001"',
            '"ip6-localhost"',
            '"ip6-loopback"',
            '"localhost6"',
        ):
            self.assertIn(loopback_host, source)


if __name__ == "__main__":
    unittest.main()
