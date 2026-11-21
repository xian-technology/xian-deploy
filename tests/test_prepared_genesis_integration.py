"""Configure a real CLI-prepared node home without modifying genesis or keys.

Opt-in: set XIAN_DEPLOY_INTEGRATION_PYTHON to the sibling xian-cli virtualenv
interpreter and XIAN_DEPLOY_INTEGRATION_CONFIGS to a xian-configs checkout.
The check prepares a home under a temporary directory and starts no node.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from ansible_harness import REPO_ROOT, PlaybookTestCase, requires_ansible, run_play

INTEGRATION_PYTHON = os.environ.get("XIAN_DEPLOY_INTEGRATION_PYTHON", "")
INTEGRATION_CONFIGS = os.environ.get("XIAN_DEPLOY_INTEGRATION_CONFIGS", "")
MANIFEST = {
    "schema_version": 1,
    "name": "deploy-test",
    "chain_id": "deploy-test-1",
    "genesis": {
        "kind": "bundle",
        "bundle": "mainnet",
        "genesis_time": "2026-06-21T00:00:00.000000Z",
    },
    "runtime_features": {"zk": True},
    "fee_policy": {
        "tx_fee_mode": "free_metered",
        "max_tx_chi": 150000,
        "max_block_chi": 400000,
    },
    "node_image_mode": "local_build",
    "p2p": {"seeds": [], "persistent_peers": []},
    "block_policy_mode": "on_demand",
    "block_policy_interval": "0s",
    "snapshot_signing_keys": [],
}


@requires_ansible
@unittest.skipUnless(
    INTEGRATION_PYTHON and INTEGRATION_CONFIGS, "prepared-genesis integration is opt-in"
)
class PreparedGenesisIntegrationTest(PlaybookTestCase):
    def prepare_node_home(self) -> Path:
        cli = self.workdir / "cli"
        network = cli / "networks" / MANIFEST["name"]
        network.mkdir(parents=True)
        (network / "manifest.json").write_text(json.dumps(MANIFEST))
        xian = Path(INTEGRATION_PYTHON).with_name("xian")
        completed = subprocess.run(
            [str(xian), "network", "join", "v1", "--base-dir", str(cli), "--network", MANIFEST["name"]]
            + ["--configs-dir", INTEGRATION_CONFIGS, "--generate-validator-key"]
            + ["--home", str(cli / "home"), "--init-node"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        home = self.workdir / "remote" / ".cometbft"
        shutil.copytree(cli / "home", home)
        return home

    def deploy_configure(self, home: Path, manifest: dict) -> subprocess.CompletedProcess:
        wrapper = self.workdir / "wrapper.py"
        result = run_play(
            self.workdir,
            manifest=manifest,
            variables={"xian_effective_bds_rpc_url": ""},
            tasks=[
                {
                    "ansible.builtin.template": {
                        "src": str(
                            REPO_ROOT / "roles/xian_runtime/templates/configure-node-wrapper.py.j2"
                        ),
                        "dest": str(wrapper),
                    }
                }
            ],
        )
        self.assertPlaySucceeded(result)
        return subprocess.run(
            [INTEGRATION_PYTHON, str(wrapper)],
            env={**os.environ, "HOME": str(home.parent)},
            capture_output=True,
            text=True,
        )

    def test_configuring_a_prepared_node_preserves_its_genesis_and_keys(self) -> None:
        home = self.prepare_node_home()
        protected = [
            home / "config/genesis.json",
            home / "config/node_key.json",
            home / "config/priv_validator_key.json",
            home / "data/priv_validator_state.json",
        ]
        original = {path: path.read_bytes() for path in protected}
        pin = hashlib.sha256(original[protected[0]]).hexdigest()
        validation = subprocess.run(
            [
                INTEGRATION_PYTHON,
                str(REPO_ROOT / "roles/xian_runtime/files/validate_node_home.py"),
                str(home),
                "genesis",
                MANIFEST["chain_id"],
                pin,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(validation.returncode, 0, validation.stderr)
        for _ in range(2):
            configured = self.deploy_configure(home, MANIFEST | {"genesis_sha256": pin})
            self.assertEqual(configured.returncode, 0, configured.stderr)
            self.assertEqual({path: path.read_bytes() for path in protected}, original)


if __name__ == "__main__":
    unittest.main()
