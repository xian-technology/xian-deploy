"""Use Ansible's real operator entrypoints for unsupported bootstrap policies."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    load_yaml,
    requires_ansible,
    run_play,
)


@requires_ansible
class BootstrapPolicyTest(PlaybookTestCase):
    def entrypoint(self, name, *, variables=None, environment=None):
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
                **(environment or {}),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def test_stop_entrypoint_can_stop_an_unsupported_existing_profile(self):
        profile = canonical_profile()
        profile["advanced"]["statesync"] = {"enabled": True}
        profile_path = self.workdir / "profile.json"
        profile_path.write_text(json.dumps(profile))
        executable_dir = self.workdir / "bin"
        executable_dir.mkdir()
        calls = self.workdir / "docker-calls.jsonl"
        docker = executable_dir / "docker"
        docker.write_text(
            f"#!{sys.executable}\nimport json,sys\n"
            f"with open({str(calls)!r}, 'a') as handle:\n"
            "    handle.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        )
        docker.chmod(0o755)
        result = self.entrypoint(
            "stop.yml",
            variables={
                "xian_node_profile": str(profile_path),
                "xian_project_name": "test-snapshot-stop",
                "xian_deploy_root": str(self.workdir / "deploy"),
            },
            environment={"PATH": str(executable_dir) + os.pathsep + os.environ["PATH"]},
        )
        self.assertPlaySucceeded(result)
        commands = [json.loads(line) for line in calls.read_text().splitlines()]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], "compose")
        self.assertEqual(commands[0][-1], "down")

    def health_tasks(self, *names):
        return [
            task
            for task in load_yaml(REPO_ROOT / "playbooks/health.yml")[0]["tasks"]
            if task["name"] in names
        ]

    def rendered_health(self, config):
        home = self.workdir / "node"
        (home / "config").mkdir(parents=True)
        (home / "config/config.toml").write_text(config)
        return run_play(
            self.workdir,
            variables={"xian_cometbft_home": str(home)},
            tasks=self.health_tasks(
                "Read rendered state-sync readiness",
                "Require disabled rendered state sync",
            ),
        )

    def test_health_refuses_enabled_rendered_state_sync_despite_disabled_profile(self):
        result = self.rendered_health("[statesync]\nenable = true\n")
        self.assertPlayFailed(result, "P2P application state sync is disabled")
        self.assertIn("full-node-store", result.stdout)

    def test_health_accepts_disabled_rendered_state_sync(self):
        result = self.rendered_health("[statesync]\nenable = false\n")
        self.assertPlaySucceeded(result)

    def test_health_refuses_unreadable_rendered_config(self):
        result = self.rendered_health("malformed = [\n")
        self.assertPlayFailed(result, "cannot read rendered CometBFT configuration")

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
        self.assertPlayFailed(result, "P2P application state sync is disabled")
        self.assertIn("replay", result.stdout)
        self.assertIn("full-node-store", result.stdout)

    def test_ordinary_replay_requires_no_history_patch_metadata(self):
        result = run_play(
            self.workdir, profile=canonical_profile(), variables={}, tasks=[]
        )
        self.assertPlaySucceeded(result)

    def test_obsolete_bootstrap_playbooks_refuse_before_connecting_or_deploying(self):
        for name in ("bootstrap-state-sync.yml", "restore-state-snapshot.yml"):
            with self.subTest(playbook=name):
                completed = self.entrypoint(name)
                self.assertPlayFailed(completed, "full-node-store")
                self.assertNotIn("Gathering Facts", completed.stdout)
                self.assertNotIn("docker run", completed.stdout)


if __name__ == "__main__":
    import unittest

    unittest.main()
