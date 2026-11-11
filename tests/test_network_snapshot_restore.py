"""Profile snapshot restore is an explicit stop -> restore -> start playbook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    canonical_profile,
    load_yaml,
    requires_ansible,
    run_play,
)

PLAYBOOK = REPO_ROOT / "playbooks/restore-network-snapshot.yml"
TEMPLATE = REPO_ROOT / "roles/xian_runtime/templates/restore-network-snapshot.py.j2"
SNAPSHOT_URL = "https://snapshots.example/manifest.json"


def task_names(tasks: list[dict]) -> list[str]:
    return [task["name"] for task in tasks]


@requires_ansible
class RestorePlaybookOrderTest(unittest.TestCase):
    def test_restore_stops_the_runtime_before_restoring_and_starts_it_after(self) -> None:
        play = load_yaml(PLAYBOOK)[0]
        tasks = play["tasks"]
        stop, restore, start = (
            task_names(tasks).index(name)
            for name in (
                "Stop runtime before restore",
                "Restore network snapshot into node home",
                "Start runtime after restore",
            )
        )

        self.assertLess(stop, restore)
        self.assertLess(restore, start)
        self.assertEqual(tasks[stop]["vars"], {"xian_runtime_action": "stop"})
        self.assertEqual(tasks[start]["vars"], {"xian_runtime_action": "deploy"})
        self.assertEqual(play["serial"], 1)


@requires_ansible
class RestoreScriptTest(PlaybookTestCase):
    def render(self, profile: dict, **variables):
        script = self.workdir / "restore.py"
        result = run_play(
            self.workdir,
            profile=profile,
            variables=variables,
            tasks=[
                {
                    "ansible.builtin.include_role": {
                        "name": "xian_profile",
                        "tasks_from": "network_snapshot",
                    }
                },
                {"ansible.builtin.template": {"src": str(TEMPLATE), "dest": str(script)}},
            ],
        )
        return result, script

    def restore_call(self, script) -> dict:
        package = self.workdir / "fake" / "xian"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "node_admin.py").write_text(
            "import json\n\n"
            "def apply_snapshot_archive(url, home, **options):\n"
            "    print(json.dumps({'url': url, 'home': str(home), **options}))\n"
            "    return 'snapshot.tar.gz'\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, str(script)],
            env={**os.environ, "PYTHONPATH": str(self.workdir / "fake")},
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout.splitlines()[0])

    def test_restore_uses_the_profile_snapshot_and_trusted_keys(self) -> None:
        profile = canonical_profile(snapshot_url=SNAPSHOT_URL, snapshot_signing_keys=["c" * 64])
        result, script = self.render(profile, xian_chain_id="local-dev-1")

        self.assertPlaySucceeded(result)
        self.assertEqual(
            self.restore_call(script),
            {
                "url": SNAPSHOT_URL,
                "home": "/root/.cometbft",
                "trusted_manifest_public_keys": ["c" * 64],
                "expected_chain_id": "local-dev-1",
            },
        )

    def test_restore_requires_a_profile_snapshot_url(self) -> None:
        result, _ = self.render(canonical_profile(snapshot_signing_keys=["c" * 64]))

        self.assertPlayFailed(result, "snapshot_url")

    def test_restore_requires_trusted_signing_keys(self) -> None:
        result, _ = self.render(canonical_profile(snapshot_url=SNAPSHOT_URL))

        self.assertPlayFailed(result, "snapshot_signing_keys")


if __name__ == "__main__":
    unittest.main()
