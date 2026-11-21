"""Use Ansible's real operator entrypoints for unsupported bootstrap policies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import patch

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    load_yaml,
    render_configure_wrapper,
    requires_ansible,
    run_play,
)


@requires_ansible
class BootstrapPolicyTest(PlaybookTestCase):
    def entrypoint(self, name, *, variables=None):
        inventory = self.workdir / "inventory.json"
        inventory.write_text(
            json.dumps(
                {
                    "xian_nodes": {
                        "hosts": {"localhost": {"ansible_connection": "local"}}
                    }
                }
            )
        )
        extra_vars = self.workdir / "entrypoint-vars.json"
        extra_vars.write_text(
            json.dumps({"ansible_become": False, **(variables or {})})
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "ansible.cli.playbook",
                "-i",
                str(inventory),
                str(REPO_ROOT / "playbooks" / name),
                "-e",
                "@" + str(extra_vars),
            ],
            cwd=REPO_ROOT,
            env={
                **os.environ,
                "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible.cfg"),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def test_stop_and_status_entrypoints_remain_available_for_unusable_profiles(self):
        profile = canonical_profile()
        profile_path = self.workdir / "profile.json"
        with self.fake_docker() as calls:
            for command, legacy, compose_action in (
                ("stop", {"enabled": True}, "down"),
                ("status", [], "ps"),
            ):
                with self.subTest(command=command):
                    profile["advanced"]["statesync"] = legacy
                    profile_path.write_text(json.dumps(profile))
                    result = self.entrypoint(
                        f"{command}.yml",
                        variables={
                            "xian_node_profile": str(profile_path),
                            "xian_project_name": "test-snapshot-stop",
                            "xian_deploy_root": str(self.workdir / "deploy"),
                        },
                    )
                    self.assertPlaySucceeded(result)
                    invocation = json.loads(calls.read_text().splitlines()[-1])
                    self.assertEqual(invocation[0], "compose")
                    self.assertEqual(invocation[-1], compose_action)

    @contextmanager
    def fake_docker(self):
        executable_dir = self.workdir / "bin"
        executable_dir.mkdir(exist_ok=True)
        calls = self.workdir / "docker-calls.jsonl"
        docker = executable_dir / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            "import json, sys, types\n"
            "args = sys.argv[1:]\n"
            f"with open({str(calls)!r}, 'a') as handle:\n"
            "    handle.write(json.dumps(args) + '\\n')\n"
            "if args[0] != 'run':\n"
            "    sys.exit(0)\n"
            "assert args[:7] == ['run', '--rm', '--network', 'none', '--entrypoint', 'python', '--mount']\n"
            "mount = args[7].split(',')\n"
            "assert mount == ['type=bind', mount[1], 'target=/root/.cometbft', 'readonly']\n"
            "assert args[9] == '-Ic' and args[11] == '/root/.cometbft'\n"
            "assert args[12] == 'config'\n"
            "def validate(config):\n"
            "    statesync = config.get('statesync', {})\n"
            "    if not isinstance(statesync, dict):\n"
            "        raise ValueError('Comet statesync configuration must be an object')\n"
            "    enabled = statesync.get('enable', False)\n"
            "    if type(enabled) is not bool:\n"
            "        raise ValueError('Comet statesync.enable must be a boolean')\n"
            "    if enabled:\n"
            "        raise ValueError('P2P application state sync is unsupported; use a verified full-node-store snapshot')\n"
            "policy = types.ModuleType('xian.state_sync_policy')\n"
            "policy.validate_comet_state_sync_disabled = validate\n"
            "sys.modules[policy.__name__] = policy\n"
            "sys.argv = ['-c', mount[1].removeprefix('source='), *args[12:]]\n"
            "exec(args[10], {'__name__': '__main__'})\n"
        )
        docker.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(executable_dir) + os.pathsep + os.environ["PATH"]}):
            yield calls

    def health_tasks(self, *names):
        return [
            task
            for task in load_yaml(REPO_ROOT / "playbooks/health.yml")[0]["tasks"]
            if task["name"] in names
        ]

    def rendered_health(self, config):
        home = self.workdir / "node"
        (home / "config").mkdir(parents=True, exist_ok=True)
        (home / "config/config.toml").write_text(config)
        with self.fake_docker():
            return run_play(
                self.workdir,
                variables={"xian_cometbft_home": str(home)},
                tasks=self.health_tasks("Validate installed CometBFT configuration"),
            )

    def test_health_refuses_enabled_rendered_state_sync_despite_disabled_profile(self):
        result = self.rendered_health("[statesync]\nenable = true\n")
        self.assertPlayFailed(result, "P2P application state sync is unsupported")
        self.assertIn("full-node-store", result.stdout)

    def test_health_accepts_disabled_rendered_state_sync(self):
        result = self.rendered_health("[statesync]\nenable = false\n")
        self.assertPlaySucceeded(result)

    def test_health_refuses_unreadable_rendered_config(self):
        result = self.rendered_health("malformed = [\n")
        self.assertPlayFailed(result, "cannot read rendered CometBFT configuration")

    def test_health_refuses_nonboolean_rendered_state_sync_setting(self):
        result = self.rendered_health("[statesync]\nenable = 0\n")
        self.assertPlayFailed(result, "Comet statesync.enable must be a boolean")

    def test_restart_refuses_unsafe_config_before_calling_compose(self):
        home = self.workdir / "node"
        (home / "config").mkdir(parents=True)
        (home / "config/config.toml").write_text("[statesync]\nenable = true\n")
        profile_path = self.workdir / "profile.json"
        profile_path.write_text(json.dumps(canonical_profile()))

        with self.fake_docker() as calls:
            result = self.entrypoint(
                "restart.yml",
                variables={
                    "xian_node_profile": str(profile_path),
                    "xian_cometbft_home": str(home),
                    "xian_deploy_root": str(self.workdir / "deploy"),
                },
            )

        self.assertPlayFailed(result, "P2P application state sync is unsupported")
        self.assertEqual([json.loads(line)[0] for line in calls.read_text().splitlines()], ["run"])

    def test_remote_disk_probe_executes_python_with_line_boundaries(self):
        result = run_play(
            self.workdir,
            variables={
                "xian_deploy_root": str(self.workdir),
                "xian_bds_disk_free_warn_bytes": 0,
            },
            tasks=[
                *self.health_tasks("Read remote disk health summary"),
                {
                    "ansible.builtin.assert": {
                        "that": [
                            "(xian_health_disk.stdout | from_json).paths.deploy_root.exists",
                            "(xian_health_disk.stdout | from_json).alerts == []",
                        ]
                    }
                },
            ],
        )
        self.assertPlaySucceeded(result)

    def test_enabled_state_sync_is_refused_before_runtime_tasks(self):
        profile = canonical_profile()
        profile["advanced"]["statesync"] = {
            "enabled": True,
            "rpc_servers": ["http://one:26657", "http://two:26657"],
            "trust_height": 42,
            "trust_hash": "ab" * 32,
            "trust_period": "168h0m0s",
        }
        result = run_play(self.workdir, profile=profile, variables={}, tasks=[])
        self.assertPlayFailed(result, "P2P application state sync is unsupported")
        self.assertIn("replay", result.stdout)
        self.assertIn("full-node-store", result.stdout)

    def test_ordinary_replay_requires_no_history_patch_metadata(self):
        result = run_play(
            self.workdir, profile=canonical_profile(), variables={}, tasks=[]
        )
        self.assertPlaySucceeded(result)

    def test_legacy_disabled_state_sync_has_no_configure_flags(self):
        profile = canonical_profile()
        profile["advanced"]["statesync"] = {"enabled": False, "trust_height": 42}
        result, arguments = render_configure_wrapper(self.workdir, profile=profile)
        self.assertPlaySucceeded(result)
        self.assertFalse(any("statesync" in arg for arg in arguments))

    def test_invalid_legacy_state_sync_is_refused_before_runtime_tasks(self):
        for legacy in (None, [], {"enabled": 0}, {"enabled": "false"}, {"enable": True}):
            with self.subTest(legacy=legacy):
                profile = canonical_profile()
                profile["advanced"]["statesync"] = legacy
                result = run_play(self.workdir, profile=profile, variables={}, tasks=[])
                self.assertPlayFailed(result, "Remove advanced.statesync")


if __name__ == "__main__":
    import unittest

    unittest.main()
