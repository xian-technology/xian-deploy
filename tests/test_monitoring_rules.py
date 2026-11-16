"""Monitoring templates rendered by Ansible for real profiles, checked with promtool.

promtool runs from the example inventory's Prometheus image in Docker, so these
tests need ansible-core and Docker (`make validate`).
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    load_yaml,
    requires_ansible,
    run_play,
)

TEMPLATES = REPO_ROOT / "roles/xian_runtime/templates"
RULE_TESTS = REPO_ROOT / "tests/monitoring"
INVENTORY = REPO_ROOT / "inventories/example/group_vars/all/main.yml"
STALL_ALERT = "alert: XianBlockProductionStalled"


def shared_network_profile(block_policy_mode: str = "idle_interval") -> dict:
    return canonical_profile(
        operator_profile="shared_network",
        block_policy_mode=block_policy_mode,
        block_policy_interval="0s" if block_policy_mode == "on_demand" else "5s",
    )


@requires_ansible
class MonitoringTemplatesTest(PlaybookTestCase):
    def render(self, template: str, profile: dict, **variables) -> Path:
        destination = self.workdir / template.removesuffix(".j2")
        result = run_play(
            self.workdir,
            profile=profile,
            variables=variables,
            tasks=[
                {
                    "ansible.builtin.template": {
                        "src": str(TEMPLATES / template),
                        "dest": str(destination),
                        "mode": "0644",
                    }
                }
            ],
        )
        self.assertPlaySucceeded(result)
        return destination

    def promtool(self, *args: str) -> None:
        image = load_yaml(INVENTORY)["xian_prometheus_image"]
        result = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "--entrypoint", "promtool"]
            # The workdir is a private temporary directory: read it as its owner
            # (the image's default user cannot enter it on a Linux host).
            + ["--user", f"{os.getuid()}:{os.getgid()}"]
            + ["-v", f"{self.workdir}:/xian-prometheus:ro", "-w", "/xian-prometheus"]
            + [image, *args],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shared_network_rules_pass_their_promtool_tests(self) -> None:
        rules = self.render("prometheus.rules.yml.j2", shared_network_profile())
        rules.rename(self.workdir / "rules.yml")
        tests = sorted(RULE_TESTS.glob("*.test.yml"))
        for test in tests:
            (self.workdir / test.name).write_text(test.read_text(encoding="utf-8"))

        self.promtool("check", "rules", "rules.yml")
        self.promtool("test", "rules", *(test.name for test in tests))

    def test_on_demand_chain_gets_no_stall_alert(self) -> None:
        rules = self.render("prometheus.rules.yml.j2", shared_network_profile("on_demand"))

        self.promtool("check", "rules", rules.name)
        self.assertNotIn(STALL_ALERT, rules.read_text(encoding="utf-8"))
        self.assertIn("alert: XianNoPeers", rules.read_text(encoding="utf-8"))

    def test_development_profiles_get_no_alerts(self) -> None:
        rules = self.render("prometheus.rules.yml.j2", canonical_profile())

        self.assertEqual(
            load_yaml(rules), {"groups": [{"name": "xian_monitoring_none", "rules": []}]}
        )

    def test_prometheus_scrapes_node_exporter_in_both_topologies(self) -> None:
        for topology in ("integrated", "fidelity"):
            with self.subTest(topology=topology):
                config = self.render(
                    "prometheus.yml.j2", canonical_profile(), xian_deploy_topology=topology
                )
                self.promtool("check", "config", "--syntax-only", config.name)
                jobs = {job["job_name"]: job for job in load_yaml(config)["scrape_configs"]}
                self.assertEqual(
                    jobs["xian_node"]["static_configs"], [{"targets": ["node-exporter:9100"]}]
                )

    def test_alertmanager_targets_render_the_alerting_section(self) -> None:
        config = self.render(
            "prometheus.yml.j2",
            canonical_profile(),
            xian_deploy_topology="integrated",
            xian_alertmanager_targets=["alertmanager.ops.internal:9093"],
        )

        self.promtool("check", "config", "--syntax-only", config.name)
        self.assertEqual(
            load_yaml(config)["alerting"],
            {
                "alertmanagers": [
                    {"static_configs": [{"targets": ["alertmanager.ops.internal:9093"]}]}
                ]
            },
        )

    def test_alertmanager_targets_must_be_host_port_strings(self) -> None:
        for index, targets in enumerate(
            ("alertmanager:9093", ["http://alertmanager:9093"], ["alertmanager"])
        ):
            with self.subTest(targets=targets):
                workdir = self.workdir / str(index)
                workdir.mkdir()
                result = run_play(
                    workdir, variables={"xian_alertmanager_targets": targets}, tasks=[]
                )
                self.assertPlayFailed(result, "xian_alertmanager_targets must be a list")

    def test_no_alertmanager_by_default(self) -> None:
        config = self.render("prometheus.yml.j2", canonical_profile(), xian_deploy_topology="fidelity")

        self.assertNotIn("alerting", load_yaml(config))

    def test_node_exporter_reads_the_host_read_only_and_publishes_no_port(self) -> None:
        compose = self.render(
            "docker-compose.monitoring.yml.j2",
            canonical_profile(),
            **{
                key: value
                for key, value in load_yaml(INVENTORY).items()
                if key.startswith(("xian_prometheus_", "xian_grafana_", "xian_node_exporter_"))
                or key == "xian_project_name"
            },
            xian_docker_log_max_file_mb=50,
            xian_docker_log_max_files=5,
            xian_prometheus_config_path="/srv/xian/monitoring/prometheus.yml",
            xian_prometheus_rules_path="/srv/xian/monitoring/rules.yml",
        )
        service = load_yaml(compose)["services"]["node-exporter"]

        self.assertEqual(service["image"], "prom/node-exporter:v1.12.1")
        self.assertEqual(service["command"], ["--path.rootfs=/host"])
        self.assertEqual(service["volumes"], ["/:/host:ro"])
        self.assertEqual(service["networks"], ["xian-net"])
        self.assertNotIn("ports", service)


if __name__ == "__main__":
    unittest.main()
