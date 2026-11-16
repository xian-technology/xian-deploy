"""Run the selected image's exact stopped-home asset on the Docker host."""

from __future__ import annotations

import hashlib
import json
import os
from unittest.mock import patch

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    load_yaml,
    requires_ansible,
    run_play,
)

ASSET = REPO_ROOT.parent / "xian-stack/scripts/node_store_runtime_guard.py"
IMAGE = "registry.example/xian-node@sha256:" + "a" * 64
ASSET_IN_IMAGE = "/usr/local/bin/xian-node-store-check-stopped"


@requires_ansible
class SnapshotHomeGuardTest(PlaybookTestCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(
            ASSET.is_file(), "current sibling xian-stack guard source is required"
        )
        self.source = self.workdir / "guard-source.py"
        self.source.write_bytes(ASSET.read_bytes())
        self.source_sha256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.guard_tmp = self.workdir / "guard-tmp"
        self.guard_tmp.mkdir()
        self.calls = self.workdir / "docker.jsonl"
        executable_dir = self.workdir / "bin"
        executable_dir.mkdir()
        docker = executable_dir / "docker"
        docker.write_bytes((REPO_ROOT / "tests/fake_guard_docker.py").read_bytes())
        docker.chmod(0o755)
        self.env = {
            "PATH": str(executable_dir) + os.pathsep + os.environ["PATH"],
            "TMPDIR": str(self.guard_tmp),
            "GUARD_DOCKER_LOG": str(self.calls),
            "GUARD_SOURCE_ASSET": str(self.source),
        }

    def restore_prefix(self, home, *, rows=None, failure=None, proof=None):
        play = load_yaml(REPO_ROOT / "playbooks/restore-network-snapshot.yml")[0]
        before_restore = [
            task
            for task in play["tasks"]
            if task["name"]
            in {"Stop runtime before restore", "Verify stopped home before restore"}
        ]
        marker = self.workdir / "restore-started"
        marker.unlink(missing_ok=True)
        self.calls.unlink(missing_ok=True)
        environment = {
            **self.env,
            "GUARD_CONTAINER_ROWS": json.dumps(rows or []),
            "GUARD_DOCKER_FAILURE": failure or "",
        }
        if proof is not None:
            environment["GUARD_FAKE_PROOF"] = proof
        with patch.dict(os.environ, environment):
            result = run_play(
                self.workdir,
                variables={
                    "xian_cometbft_home": str(home),
                    "xian_deploy_root": str(self.workdir / "deploy"),
                    "xian_project_name": "managed-project",
                    "xian_restore_image": IMAGE,
                },
                tasks=[
                    *before_restore,
                    {
                        "ansible.builtin.file": {
                            "path": str(marker),
                            "state": "touch",
                            "mode": "0600",
                        }
                    },
                ],
            )
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        return result, marker, calls

    def assert_clean(self):
        self.assertEqual(
            list(self.guard_tmp.glob("xian-node-store-check-stopped-*")), []
        )

    def test_known_empty_daemon_uses_exact_asset_privately_and_cleans_it(self):
        home = self.workdir / "recipient"
        home.mkdir()
        alias = self.workdir / "recipient-alias"
        alias.symlink_to(home, target_is_directory=True)
        result, marker, calls = self.restore_prefix(alias)
        self.assertPlaySucceeded(result)
        self.assertTrue(marker.exists())
        fetches = [call["args"] for call in calls if call["args"][0] == "run"]
        self.assertEqual(
            fetches,
            [
                [
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--entrypoint",
                    "cat",
                    IMAGE,
                    ASSET_IN_IMAGE,
                ]
            ],
        )
        queries = [call for call in calls if call["args"][0] == "ps"]
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0]["args"], ["ps", "--quiet"])
        self.assertEqual(
            queries[0]["guards"], [{"sha256": self.source_sha256, "mode": 0o700}]
        )
        self.assert_clean()

    def test_nonexistent_fresh_home_is_allowed_without_creating_it(self):
        home = self.workdir / "future" / "recipient"
        result, marker, _ = self.restore_prefix(home)
        self.assertPlaySucceeded(result)
        self.assertTrue(marker.exists())
        self.assertFalse(home.exists())
        self.assert_clean()

    def test_host_guard_does_not_import_modules_from_the_temporary_directory(self):
        injected = self.workdir / "untrusted-module-ran"
        (self.guard_tmp / "json.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(injected)!r}).touch()\n"
            "raise RuntimeError('imported untrusted temporary json module')\n"
        )
        result, marker, _ = self.restore_prefix(self.workdir / "recipient")
        self.assertPlaySucceeded(result)
        self.assertTrue(marker.exists())
        self.assertFalse(injected.exists())
        self.assert_clean()

    def test_other_compose_project_writable_parent_prevents_restore(self):
        home = self.workdir / "future" / "recipient"
        rows = [
            {
                "Config": {"Labels": {"com.docker.compose.project": "unrelated"}},
                "Mounts": [{"Source": str(self.workdir), "RW": True}],
            }
        ]
        result, marker, calls = self.restore_prefix(home, rows=rows)
        self.assertPlayFailed(result, "writable mount")
        self.assertFalse(marker.exists())
        self.assertEqual(calls[0]["args"][-1], "down")
        self.assertTrue(
            any(call["args"] == ["inspect", "other-project-1"] for call in calls)
        )
        self.assert_clean()

    def test_readonly_overlap_does_not_hide_a_stopped_home(self):
        home = self.workdir / "recipient"
        rows = [{"Mounts": [{"Source": str(self.workdir), "RW": False}]}]
        result, marker, _ = self.restore_prefix(home, rows=rows)
        self.assertPlaySucceeded(result)
        self.assertTrue(marker.exists())
        self.assert_clean()

    def test_docker_query_failure_refuses_restore_and_removes_temporary_script(self):
        for failure in ("ps", "inspect", "run"):
            with self.subTest(failure=failure):
                result, marker, _ = self.restore_prefix(
                    self.workdir / "recipient", rows=[{"Mounts": []}], failure=failure
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(marker.exists())
                self.assert_clean()

    def test_nonpositive_or_wrong_home_proof_refuses_restore_and_cleans_up(self):
        home = self.workdir / "recipient"
        for proof in (
            "not-json",
            json.dumps({"runtime_stopped": 1, "home": str(home.resolve())}),
            json.dumps({"runtime_stopped": True, "home": "/wrong-home"}),
        ):
            with self.subTest(proof=proof):
                result, marker, _ = self.restore_prefix(home, proof=proof)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(marker.exists())
                self.assert_clean()
