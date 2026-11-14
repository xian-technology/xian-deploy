"""Run repository roles on localhost with Ansible's real templater.

These checks need ansible-core. `make validate` runs them through
`uvx --from ansible-core`; plain `python3 -m unittest` skips them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    import ansible  # noqa: F401
except ImportError:  # pragma: no cover - depends on the interpreter
    HAS_ANSIBLE = False
else:
    HAS_ANSIBLE = True

requires_ansible = unittest.skipUnless(HAS_ANSIBLE, "ansible-core is not importable")


def load_yaml(path: Path):
    import yaml  # ansible-core depends on PyYAML

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def canonical_profile(**overrides) -> dict:
    profile = {
        "schema_version": 1,
        "name": "validator-1",
        "network": "local-dev",
        "moniker": "validator-1",
        "node_image_mode": "registry",
        "node_integrated_image": "registry.example/xian-node@sha256:" + "a" * 64,
        "node_split_image": "registry.example/xian-node-split@sha256:" + "b" * 64,
        "p2p": {"seeds": [], "persistent_peers": []},
        "block_policy_mode": "on_demand",
        "operator_profile": "local_development",
        "services": {"bds": {"enabled": False}, "dashboard": {}, "monitoring": {}},
        "advanced": {
            "cometbft": {},
            "statesync": {},
            "metrics": {},
            "pending_nonce": {},
        },
    }
    profile.update(overrides)
    return profile


def run_play(
    workdir: Path,
    *,
    variables: dict,
    tasks: list[dict],
    profile: dict | None = None,
    manifest: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    """Load the node profile role, then run ``tasks`` on localhost."""

    profile_path = workdir / "profile.json"
    profile_path.write_text(json.dumps(profile or canonical_profile()), encoding="utf-8")
    play_vars = {"xian_node_profile": str(profile_path), **variables}
    if manifest is not None:
        manifest_path = workdir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        play_vars["xian_network_manifest"] = str(manifest_path)
    play = [
        {
            "name": "Exercise deployment roles locally",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": play_vars,
            "tasks": [
                {"ansible.builtin.import_role": {"name": "xian_profile"}},
                *tasks,
            ],
        }
    ]
    playbook = workdir / "play.yml"  # JSON is valid YAML
    playbook.write_text(json.dumps(play, indent=2), encoding="utf-8")
    environment = {
        **os.environ,
        "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(REPO_ROOT / "roles"),
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "ANSIBLE_NOCOLOR": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", str(playbook)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def render_configure_wrapper(workdir: Path, **kwargs) -> tuple[subprocess.CompletedProcess, list]:
    """Render the configure-node wrapper and return the argv it passes to configure."""

    wrapper = workdir / "configure-node.py"
    kwargs["variables"] = {"xian_effective_bds_rpc_url": "", **kwargs.get("variables", {})}
    result = run_play(
        workdir,
        tasks=[
            {
                "ansible.builtin.template": {
                    "src": str(
                        REPO_ROOT / "roles/xian_runtime/templates/configure-node-wrapper.py.j2"
                    ),
                    "dest": str(wrapper),
                    "mode": "0600",
                }
            }
        ],
        **kwargs,
    )
    if result.returncode != 0:
        return result, []
    package = workdir / "fake" / "xian" / "cli"
    package.mkdir(parents=True)
    for directory in (package.parent, package):
        (directory / "__init__.py").write_text("", encoding="utf-8")
    (package / "configure_node.py").write_text(
        "import json\n\ndef main(args):\n    print(json.dumps(args))\n    return 0\n",
        encoding="utf-8",
    )
    captured = subprocess.run(
        [sys.executable, str(wrapper)],
        env={**os.environ, "PYTHONPATH": str(workdir / "fake")},
        capture_output=True,
        text=True,
        check=True,
    )
    return result, json.loads(captured.stdout)


def option_values(arguments: list[str], option: str) -> list[str]:
    return [arguments[index + 1] for index, value in enumerate(arguments) if value == option]


class PlaybookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="xian-deploy-test-")
        self.addCleanup(directory.cleanup)
        self.workdir = Path(directory.name)

    def assertPlayFailed(self, result, message: str) -> None:  # noqa: N802
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stdout)

    def assertPlaySucceeded(self, result) -> None:  # noqa: N802
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
