"""Check the deploy preflight against local files through Ansible's real role."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ansible_harness import REPO_ROOT, PlaybookTestCase, requires_ansible, run_play

GENESIS = b'{"chain_id":"local-dev-1","abci_genesis":{"genesis":[]}}\n'
PIN = hashlib.sha256(GENESIS).hexdigest()
VALIDATOR = REPO_ROOT / "roles/xian_runtime/files/validate_node_home.py"
FAKE_DOCKER = REPO_ROOT / "tests/fake_node_home_docker.py"
spec = importlib.util.spec_from_file_location("validate_node_home", VALIDATOR)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class GenesisHomeTestCase(PlaybookTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.workdir / "node home"
        self.config = self.home / "config"
        self.config.mkdir(parents=True)
        self.genesis = self.config / "genesis.json"
        self.genesis.write_bytes(GENESIS)
        self.comet_config = self.config / "config.toml"
        self.comet_config.write_text('genesis_file = "config/genesis.json"\n')


class PreparedGenesisFileTest(GenesisHomeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.policy = SimpleNamespace(validate_comet_state_sync_disabled=Mock())

    def verify(self, chain_id="", pin="", *, mode="genesis") -> None:
        with patch.dict(sys.modules, {"xian.state_sync_policy": self.policy}):
            validator.main(self.home, mode, chain_id, pin)

    def test_home_can_be_verified_without_a_manifest(self) -> None:
        self.verify()

    def test_configuration_only_verifies_policy_on_an_existing_runtime(self) -> None:
        self.genesis.unlink()

        self.verify("local-dev-1", PIN, mode="config")

        self.policy.validate_comet_state_sync_disabled.assert_called_once_with(
            {"genesis_file": "config/genesis.json"}
        )

    def test_unknown_validation_mode_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown prepared node home validation mode"):
            self.verify(mode="unexpected")

    def test_missing_genesis_file_setting_is_rejected(self) -> None:
        self.comet_config.write_text('moniker = "validator-1"\n')

        with self.assertRaisesRegex(ValueError, "genesis_file"):
            self.verify()

    def test_malformed_cometbft_configuration_fails(self) -> None:
        self.comet_config.write_text("genesis_file = [\n")

        with self.assertRaisesRegex(ValueError, "cannot read rendered CometBFT configuration"):
            self.verify()

    def test_equivalent_cometbft_path_resolves_to_the_prepared_file(self) -> None:
        self.comet_config.write_text(f"genesis_file = {json.dumps(str(self.genesis))}\n")

        self.verify("local-dev-1", PIN)

    def test_cometbft_must_use_the_same_genesis_as_abci(self) -> None:
        (self.config / "other.json").write_bytes(GENESIS)
        self.comet_config.write_text('genesis_file = "config/other.json"\n')

        with self.assertRaisesRegex(ValueError, "genesis_file"):
            self.verify("local-dev-1", PIN)

    def test_genesis_file_cannot_escape_the_prepared_home(self) -> None:
        outside = self.workdir / "genesis.json"
        self.genesis.rename(outside)
        self.genesis.symlink_to(outside)

        with self.assertRaisesRegex(ValueError, "file inside the node home"):
            self.verify()

    def test_invalid_genesis_is_rejected_even_without_a_pin(self) -> None:
        for data, message in (
            (b'{"chain_id":', "valid Xian genesis JSON"),
            (b'{"chain_id":NaN}', "valid Xian genesis JSON"),
            (b"[]", "Xian genesis object"),
            (b'{"chain_id":11}', "nonempty chain_id"),
            (b'{"chain_id":" "}', "nonempty chain_id"),
            (b'{"chain_id":"local-dev-1"}', "abci_genesis.genesis"),
            (b'{"chain_id":"local-dev-1","abci_genesis":{"genesis":{}}}', "abci_genesis.genesis"),
        ):
            with self.subTest(data=data):
                self.genesis.write_bytes(data)
                with self.assertRaisesRegex(ValueError, message):
                    self.verify()

    def test_genesis_chain_id_must_match_the_network(self) -> None:
        with self.assertRaisesRegex(ValueError, "chain_id"):
            self.verify("other-1")

    def test_reformatted_bytes_do_not_match_the_pin(self) -> None:
        self.genesis.write_bytes(json.dumps(json.loads(GENESIS), indent=2).encode())

        with self.assertRaisesRegex(ValueError, "genesis_sha256"):
            self.verify(pin=PIN)


@requires_ansible
class PreparedGenesisTest(GenesisHomeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.signing_state = self.home / "priv_validator_state.json"
        self.signing_state.write_text('{"height":"71","round":0,"step":3}\n')

        executable_dir = self.workdir / "bin"
        executable_dir.mkdir()
        docker = executable_dir / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            + FAKE_DOCKER.read_text()
            + "\nraise SystemExit(8)\n"
        )
        docker.chmod(0o755)
        self.docker_path = str(executable_dir) + os.pathsep + os.environ["PATH"]

    def verify(self, *, deploy=False, **manifest):
        role = {"name": "xian_runtime"}
        if not deploy:
            role["tasks_from"] = "check_node_home"
        with patch.dict(os.environ, {"PATH": self.docker_path}):
            return run_play(
                self.workdir,
                variables={
                    "xian_cometbft_home": str(self.home),
                    "xian_deploy_root": str(self.workdir / "deploy"),
                },
                manifest={"chain_id": "local-dev-1", **manifest},
                tasks=[{"ansible.builtin.include_role": role}],
            )

    def test_prepared_home_is_accepted_with_or_without_a_pin(self) -> None:
        self.assertPlaySucceeded(self.verify())
        self.assertPlaySucceeded(self.verify(genesis_sha256=PIN.upper()))
        self.assertEqual(self.genesis.read_bytes(), GENESIS)
        self.assertEqual(self.signing_state.read_text(), '{"height":"71","round":0,"step":3}\n')

    def test_reformatted_bytes_do_not_match_the_pin(self) -> None:
        reformatted = json.dumps(json.loads(GENESIS), indent=2).encode()
        self.genesis.write_bytes(reformatted)

        self.assertPlayFailed(self.verify(genesis_sha256=PIN), "genesis_sha256")
        self.assertEqual(self.genesis.read_bytes(), reformatted)

    def test_missing_genesis_fails_without_recreating_it(self) -> None:
        self.genesis.unlink()

        self.assertPlayFailed(self.verify(deploy=True), "config/genesis.json must be a file")
        self.assertFalse(self.genesis.exists())
        self.assertFalse((self.workdir / "deploy").exists())

    def test_bad_manifest_pin_is_rejected(self) -> None:
        self.assertPlayFailed(self.verify(genesis_sha256=""), "64 hexadecimal characters")
