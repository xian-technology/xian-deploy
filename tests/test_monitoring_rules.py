"""Monitoring assets installed by Ansible for real profiles, checked with promtool.

promtool runs from the example inventory's Prometheus image in Docker, so these
tests need ansible-core and Docker (`make validate`).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
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
INVENTORY = REPO_ROOT / "inventories/example/group_vars/all/main.yml"
BUNDLE_FILES = (
    "alertmanager/alertmanager.example.yml",
    "grafana/dashboards/xian-bds-recovery.json",
    "grafana/dashboards/xian-overview.json",
    "grafana/dashboards/xian-shared-network.json",
    "grafana/dashboards/xian-vm-runtime.json",
    "grafana/provisioning/dashboards/xian.yml",
    "grafana/provisioning/datasources/xian.yml",
    "prometheus/rules/block-cadence.yml",
    "prometheus/rules/shared-network.yml",
)
COMMON_RULES = "/etc/prometheus/rules/shared-network.yml"
CADENCE_RULES = "/etc/prometheus/rules/block-cadence.yml"


def create_bundle(path: Path, contents: bytes = b"sample monitoring asset\n") -> Path:
    with tarfile.open(path, "w") as bundle:
        for name in BUNDLE_FILES:
            data = b"groups: []\n" if name.startswith("prometheus/") else contents
            member = tarfile.TarInfo(name)
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
    return path


def role_tasks(name: str) -> list[dict]:
    return [
        {"ansible.builtin.include_role": {"name": "xian_runtime", "tasks_from": name}}
    ]


def shared_network_profile(block_policy_mode: str = "idle_interval") -> dict:
    return canonical_profile(
        operator_profile="shared_network",
        block_policy_mode=block_policy_mode,
        block_policy_interval="0s" if block_policy_mode == "on_demand" else "5s",
        services={"monitoring": {"enabled": True}, "bds": {}, "dashboard": {}},
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

    def install(self, profile: dict, bundle: Path, **overrides):
        inventory = load_yaml(INVENTORY)
        image_names = (
            "xian_prometheus_image",
            "xian_grafana_image",
            "xian_node_exporter_image",
            "xian_postgres_image",
        )
        return run_play(
            self.workdir,
            profile=profile,
            variables={
                **{
                    key: inventory[key]
                    for key in inventory
                    if key.startswith(("xian_prometheus_", "xian_grafana_"))
                },
                **{key: inventory[key] + "@sha256:" + "a" * 64 for key in image_names},
                "xian_project_name": "xian-test",
                "xian_monitoring_dir": str(self.workdir / "monitoring"),
                "xian_monitoring_compose_path": str(
                    self.workdir / "monitoring-compose.yml"
                ),
                "xian_monitoring_bundle_source": str(bundle),
                "xian_monitoring_bundle_sha256": hashlib.sha256(
                    bundle.read_bytes()
                ).hexdigest(),
                **overrides,
            },
            tasks=role_tasks("monitoring"),
        )

    def test_installs_pinned_assets_and_updates_policy_and_dashboard_selection(
        self,
    ) -> None:
        published = os.environ.get("XIAN_MONITORING_TEST_BUNDLE")
        bundle = (
            Path(published).resolve()
            if published
            else create_bundle(self.workdir / "bundle.tar")
        )
        profile = shared_network_profile()
        monitoring = self.workdir / "monitoring"
        config = monitoring / "prometheus/prometheus.yml"
        compose = self.workdir / "monitoring-compose.yml"

        self.assertPlaySucceeded(self.install(profile, bundle))
        self.assertEqual(load_yaml(config)["rule_files"], [COMMON_RULES, CADENCE_RULES])
        with tarfile.open(bundle) as archive:
            for name in BUNDLE_FILES:
                self.assertEqual(
                    (monitoring / name).read_bytes(), archive.extractfile(name).read()
                )
        first_labels = load_yaml(compose)["services"]["prometheus"]["labels"]
        self.assertEqual(
            first_labels["io.xian.monitoring.bundle-sha256"],
            hashlib.sha256(bundle.read_bytes()).hexdigest(),
        )

        alertmanager = ["alertmanager.ops.internal:9093"]
        on_demand = shared_network_profile("on_demand")
        on_demand["services"]["bds"] = {"enabled": True}
        self.assertPlaySucceeded(
            self.install(
                on_demand,
                bundle,
                xian_bds_password="fixture-password",
                xian_alertmanager_targets=alertmanager,
            )
        )
        self.assertEqual(load_yaml(config)["rule_files"], [COMMON_RULES])
        self.assertEqual(
            load_yaml(config)["alerting"]["alertmanagers"][0]["static_configs"],
            [{"targets": alertmanager}],
        )
        self.assertIn(
            "xian-bds-recovery.json",
            {p.name for p in (monitoring / "grafana/dashboards").iterdir()},
        )
        second_labels = load_yaml(compose)["services"]["prometheus"]["labels"]
        self.assertNotEqual(first_labels, second_labels)

        development = canonical_profile()
        development["services"]["monitoring"]["enabled"] = True
        updated_bundle = create_bundle(
            self.workdir / "updated.tar", b"updated monitoring asset\n"
        )
        self.assertPlaySucceeded(self.install(development, updated_bundle))
        self.assertNotIn("rule_files", load_yaml(config))
        self.assertFalse(
            (monitoring / "grafana/dashboards/xian-shared-network.json").exists()
        )
        self.assertEqual(
            (monitoring / "grafana/dashboards/xian-overview.json").read_bytes(),
            b"updated monitoring asset\n",
        )
        self.assertNotEqual(
            load_yaml(compose)["services"]["prometheus"]["labels"][
                "io.xian.monitoring.bundle-sha256"
            ],
            second_labels["io.xian.monitoring.bundle-sha256"],
        )

    def test_rejects_missing_or_mismatched_pins_before_installing_any_assets(
        self,
    ) -> None:
        bundle = create_bundle(self.workdir / "bundle.tar")
        for pin, message in (
            ("", "Monitoring requires xian_monitoring_bundle_source"),
            ("0" * 64, "does not match xian_monitoring_bundle_sha256"),
        ):
            with self.subTest(pin=pin):
                result = self.install(
                    shared_network_profile(), bundle, xian_monitoring_bundle_sha256=pin
                )
                self.assertPlayFailed(result, message)
                self.assertFalse((self.workdir / "monitoring").exists())

    def test_disabling_and_reenabling_preserves_existing_prometheus_data_mount(
        self,
    ) -> None:
        main = self.workdir / "main-compose.yml"
        monitoring = self.workdir / "monitoring-compose.yml"
        project = self.workdir.name.lower()
        image = load_yaml(INVENTORY)["xian_prometheus_image"]
        idle = {
            "image": image,
            "entrypoint": ["/bin/sh", "-c", "exec sleep 3600"],
            "stop_grace_period": "1s",
        }
        services = {
            name: {**idle, "restart": "always"}
            for name in ("prometheus", "grafana", "node-exporter")
        }
        main.write_text(json.dumps({"services": {"abci": idle}}), encoding="utf-8")

        def write_monitoring() -> None:
            monitoring.write_text(json.dumps({"services": services}), encoding="utf-8")

        def compose(*args: str, enabled: bool = True) -> str:
            command = ["docker", "compose", "-p", project, "-f", str(main)]
            if enabled:
                command += ["-f", str(monitoring)]
            return subprocess.check_output(command + list(args), text=True).strip()

        def cleanup() -> None:
            write_monitoring()
            compose("down", "--volumes")

        def inspect(container: str) -> dict:
            return json.loads(
                subprocess.check_output(["docker", "inspect", container], text=True)
            )[0]

        def prometheus_volume(container: str) -> str:
            return next(
                mount["Name"]
                for mount in inspect(container)["Mounts"]
                if mount["Destination"] == "/prometheus"
            )

        write_monitoring()
        self.addCleanup(cleanup)
        compose("up", "-d")
        original = compose("ps", "--all", "--quiet", "prometheus")
        volume = prometheus_volume(original)
        node = compose("ps", "--all", "--quiet", "abci")
        variables = {
            "xian_project_name": project,
            "xian_main_compose_path": str(main),
            "xian_monitoring_compose_path": str(monitoring),
        }
        for _ in range(2):
            self.assertPlaySucceeded(
                run_play(
                    self.workdir,
                    variables=variables,
                    tasks=role_tasks("disable_monitoring"),
                )
            )
            self.assertFalse(monitoring.exists())
        compose("up", "-d", enabled=False)
        self.assertEqual(compose("ps", "--quiet", "abci", enabled=False), node)
        stopped = inspect(original)
        self.assertFalse(stopped["State"]["Running"])
        self.assertEqual(
            stopped["HostConfig"]["RestartPolicy"]["Name"], "unless-stopped"
        )

        for service in services.values():
            service["restart"] = "unless-stopped"
        write_monitoring()
        compose("up", "-d")
        active = compose("ps", "--quiet", "prometheus")
        self.assertEqual(prometheus_volume(active), volume)

    def test_prometheus_scrapes_the_node_and_node_exporter(self) -> None:
        config = self.render("prometheus.yml.j2", canonical_profile())
        self.promtool("check", "config", "--syntax-only", config.name)
        jobs = {job["job_name"]: job for job in load_yaml(config)["scrape_configs"]}
        self.assertEqual(
            jobs["xian_node"]["static_configs"], [{"targets": ["node-exporter:9100"]}]
        )
        self.assertEqual(
            jobs["xian_cometbft"]["static_configs"], [{"targets": ["abci:26660"]}]
        )

    def test_alertmanager_targets_render_the_alerting_section(self) -> None:
        config = self.render(
            "prometheus.yml.j2",
            canonical_profile(),
            xian_alertmanager_targets=["alertmanager.ops.internal:9093"],
        )

        self.promtool("check", "config", "--syntax-only", config.name)
        self.assertEqual(
            load_yaml(config)["alerting"],
            {
                "alertmanagers": [
                    {
                        "static_configs": [
                            {"targets": ["alertmanager.ops.internal:9093"]}
                        ]
                    }
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
                self.assertPlayFailed(
                    result, "xian_alertmanager_targets must be a list"
                )

    def test_no_alertmanager_by_default(self) -> None:
        config = self.render("prometheus.yml.j2", canonical_profile())

        self.assertNotIn("alerting", load_yaml(config))

    def test_node_exporter_reads_the_host_read_only_and_publishes_no_port(self) -> None:
        compose = self.render(
            "docker-compose.monitoring.yml.j2",
            canonical_profile(),
            **{
                key: value
                for key, value in load_yaml(INVENTORY).items()
                if key.startswith(
                    ("xian_prometheus_", "xian_grafana_", "xian_node_exporter_")
                )
                or key == "xian_project_name"
            },
            xian_docker_log_max_file_mb=50,
            xian_docker_log_max_files=5,
            xian_monitoring_bundle_sha256="a" * 64,
            xian_rendered_prometheus_config={"checksum": "b" * 40},
        )
        service = load_yaml(compose)["services"]["node-exporter"]

        self.assertEqual(service["image"], "prom/node-exporter:v1.12.1")
        self.assertEqual(service["command"], ["--path.rootfs=/host"])
        self.assertEqual(service["volumes"], ["/:/host:ro"])
        self.assertEqual(service["networks"], ["xian-net"])
        self.assertNotIn("ports", service)


if __name__ == "__main__":
    unittest.main()
