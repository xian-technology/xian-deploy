"""Deploy-built and `xian node init`-built bundle genesis are byte-identical.

Opt-in: set XIAN_DEPLOY_PARITY_PYTHON to an interpreter with xian-abci installed
(for example the sibling xian-cli virtualenv) and XIAN_DEPLOY_PARITY_CONFIGS to
a xian-configs checkout. The check builds real genesis files on the local disk
under a temporary HOME; it starts no node and touches no container.
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

PARITY_PYTHON = os.environ.get("XIAN_DEPLOY_PARITY_PYTHON", "")
PARITY_CONFIGS = os.environ.get("XIAN_DEPLOY_PARITY_CONFIGS", "")
MANIFEST = {
    "schema_version": 1,
    "name": "parity",
    "chain_id": "parity-1",
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
@unittest.skipUnless(PARITY_PYTHON and PARITY_CONFIGS, "genesis parity check is opt-in")
class GenesisParityTest(PlaybookTestCase):
    def _node_init_genesis(self) -> bytes:
        cli = self.workdir / "cli"
        (cli / "networks" / "parity").mkdir(parents=True)
        (cli / "networks" / "parity" / "manifest.json").write_text(json.dumps(MANIFEST))
        xian = Path(PARITY_PYTHON).with_name("xian")
        subprocess.run(
            [str(xian), "network", "join", "v1", "--base-dir", str(cli), "--network", "parity"]
            + ["--configs-dir", PARITY_CONFIGS, "--generate-validator-key"]
            + ["--home", str(cli / "home"), "--init-node"],
            check=True,
            capture_output=True,
        )
        # Deploy configures a pushed home: same layout, genesis rebuilt remotely.
        home = self.workdir / "remote" / ".cometbft"
        shutil.copytree(cli / "home" / "config", home / "config")
        (home / "config" / "genesis.json").unlink()
        return (cli / "home" / "config" / "genesis.json").read_bytes()

    def _deploy_configure(self, manifest: dict) -> subprocess.CompletedProcess:
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
            [PARITY_PYTHON, str(wrapper)],
            env={
                **os.environ,
                "HOME": str(self.workdir / "remote"),
                "XIAN_CONFIGS_DIR": PARITY_CONFIGS,
            },
            capture_output=True,
            text=True,
        )

    def _deployed_genesis(self) -> Path:
        return self.workdir / "remote" / ".cometbft" / "config" / "genesis.json"

    def test_deploy_and_node_init_build_the_same_bundle_genesis(self) -> None:
        node_init_genesis = self._node_init_genesis()

        self.assertEqual(self._deploy_configure(MANIFEST).returncode, 0)

        self.assertEqual(self._deployed_genesis().read_bytes(), node_init_genesis)

    def test_deploy_installs_only_the_pinned_genesis(self) -> None:
        pin = hashlib.sha256(self._node_init_genesis()).hexdigest()

        refused = self._deploy_configure(MANIFEST | {"genesis_sha256": "0" * 64})
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("genesis_sha256", refused.stderr)
        self.assertFalse(self._deployed_genesis().exists())

        accepted = self._deploy_configure(MANIFEST | {"genesis_sha256": pin})
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(hashlib.sha256(self._deployed_genesis().read_bytes()).hexdigest(), pin)


if __name__ == "__main__":
    unittest.main()
