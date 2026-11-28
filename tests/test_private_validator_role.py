"""Private validators through the deployment role's real profile and templater."""

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    load_yaml,
    requires_ansible,
    run_play,
)
from test_private_validator_transport import policy


def private_profile():
    return canonical_profile(
        p2p={
            "seeds": [],
            "persistent_peers": [p["comet_peer"] for p in policy()["peers"]],
        },
        advanced={"cometbft": {"prometheus": False}, "metrics": {"enabled": False}},
    )


def include(task):
    return {
        "ansible.builtin.include_role": {"name": "xian_runtime", "tasks_from": task}
    }


@requires_ansible
class PrivateValidatorRoleTest(PlaybookTestCase):
    def test_private_compose_has_no_ports_or_native_networks(self):
        target = self.workdir / "compose.yaml"
        inventory = load_yaml(REPO_ROOT / "inventories/example/group_vars/all/main.yml")
        del inventory["xian_node_profile"], inventory["xian_network_manifest"]
        result = run_play(
            self.workdir,
            profile=private_profile(),
            variables={
                **inventory,
                "xian_private_validator_transport": policy(),
                "xian_private_anchor_id": "c" * 64,
            },
            tasks=[
                {
                    "ansible.builtin.include_vars": str(
                        REPO_ROOT / "roles/xian_runtime/defaults/main.yml"
                    )
                },
                {
                    "ansible.builtin.template": {
                        "src": str(
                            REPO_ROOT
                            / "roles/xian_runtime/templates/docker-compose.yml.j2"
                        ),
                        "dest": str(target),
                    }
                },
            ],
        )
        self.assertPlaySucceeded(result)
        config = load_yaml(target)
        self.assertNotIn("networks", config)
        self.assertEqual(list(config["services"]), ["abci"])
        node = config["services"]["abci"]
        self.assertEqual(node["environment"]["XIAN_PRIVATE_VALIDATOR_RPC"], "1")
        self.assertNotIn("ports", node)
        self.assertNotIn("networks", node)
        self.assertNotIn("hostname", node)
        self.assertEqual(node["network_mode"], "container:" + "c" * 64)
        self.assertEqual(node["restart"], "no")
        self.assertEqual(set(node["cap_drop"]), {"NET_RAW", "NET_ADMIN", "SYS_ADMIN"})
        self.assertEqual(node["security_opt"], ["no-new-privileges:true"])

    def test_unsafe_profiles_rejected_before_namespace_inspection(self):
        for name in ("dns_seed", "no_static_peer", "monitoring", "public_rpc"):
            with self.subTest(name=name):
                profile = private_profile()
                variables = {"xian_private_validator_transport": policy()}
                if name == "dns_seed":
                    profile["p2p"]["seeds"] = ["ab" * 20 + "@dns.example:26656"]
                elif name == "no_static_peer":
                    profile["p2p"]["persistent_peers"] = []
                elif name == "monitoring":
                    profile["advanced"]["metrics"]["enabled"] = True
                else:
                    variables["xian_public_rpc_enabled"] = True
                result = run_play(
                    self.workdir,
                    profile=profile,
                    variables=variables,
                    tasks=[include("private_transport")],
                )
                self.assertPlayFailed(
                    result, "Private validators require static enrolled peers"
                )

    def test_required_marker_rejects_missing_private_inventory(self):
        (self.workdir / "private-validator").write_text("required\n")
        result = run_play(
            self.workdir,
            profile=private_profile(),
            variables={"xian_runtime_dir": str(self.workdir)},
            tasks=[include("check_private_marker")],
        )
        self.assertPlayFailed(
            result, "requires its private WireGuard validator inventory"
        )
