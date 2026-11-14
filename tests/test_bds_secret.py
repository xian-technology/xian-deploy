"""BDS settings live in xian.toml; the password only in one owner-only secret file."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    option_values,
    render_configure_wrapper,
    requires_ansible,
    run_play,
)

PASSWORD = "a-strong-test-password"
SECRET_PATH = "/run/secrets/xian_bds_password"


def bds_profile() -> dict:
    return canonical_profile(
        services={"bds": {"enabled": True}, "dashboard": {}, "monitoring": {}}
    )


@requires_ansible
class BdsSecretTest(PlaybookTestCase):
    def render_compose(self, topology: str) -> dict:
        import yaml  # ansible-core depends on PyYAML

        compose = self.workdir / f"compose-{topology}.yml"
        inventory = yaml.safe_load(
            (REPO_ROOT / "inventories/example/group_vars/all/main.yml").read_text(encoding="utf-8")
        )
        inventory.pop("xian_node_profile")
        result = run_play(
            self.workdir,
            profile=bds_profile(),
            variables={
                **inventory,
                "xian_bds_password": PASSWORD,
                "xian_deploy_topology": topology,
            },
            tasks=[
                {
                    "ansible.builtin.include_vars": str(
                        REPO_ROOT / "roles/xian_runtime/defaults/main.yml"
                    )
                },
                {"ansible.builtin.set_fact": {"xian_effective_bds_rpc_url": ""}},
                {
                    "ansible.builtin.template": {
                        "src": str(REPO_ROOT / "roles/xian_runtime/templates/docker-compose.yml.j2"),
                        "dest": str(compose),
                        "mode": "0600",
                    }
                },
            ],
        )
        self.assertPlaySucceeded(result)
        return yaml.safe_load(compose.read_text(encoding="utf-8"))

    def test_node_and_postgres_read_the_same_secret_file(self) -> None:
        for topology, node_service in (("integrated", "abci"), ("fidelity", "abci-app")):
            with self.subTest(topology=topology):
                services = self.render_compose(topology)["services"]

                self.assertEqual(services[node_service]["secrets"], ["xian_bds_password"])
                self.assertNotIn("env_file", services[node_service])
                self.assertEqual(services["postgres"]["secrets"], ["xian_bds_password"])
                self.assertEqual(
                    services["postgres"]["environment"]["POSTGRES_PASSWORD_FILE"], SECRET_PATH
                )
                rendered = json.dumps(services)
                self.assertNotIn(PASSWORD, rendered)
                self.assertNotIn("XIAN_BDS_", rendered)

    def test_configure_wrapper_never_handles_the_password(self) -> None:
        result, arguments = render_configure_wrapper(
            self.workdir,
            profile=bds_profile(),
            variables={
                "xian_bds_password": PASSWORD,
                "xian_bds_dsn": "postgresql://indexer@db.internal/xian?sslmode=require",
            },
        )

        self.assertPlaySucceeded(result)
        self.assertNotIn(PASSWORD, arguments)
        self.assertFalse([value for value in arguments if value.startswith("--bds-password")])
        self.assertEqual(
            option_values(arguments, "--bds-dsn"),
            ["postgresql://indexer@db.internal/xian?sslmode=require"],
        )


    def test_profile_bds_password_is_rejected_by_name(self) -> None:
        profile = canonical_profile(
            services={"bds": {"enabled": False, "password": ""}, "dashboard": {}, "monitoring": {}}
        )
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "unknown key(s): services.bds.password")


if __name__ == "__main__":
    unittest.main()
