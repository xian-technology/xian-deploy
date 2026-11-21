"""push-home places a prepared node home; it never resets a validator's signing state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ansible_harness import REPO_ROOT, PlaybookTestCase, requires_ansible, run_play

STATE_FILE = Path("data/priv_validator_state.json")
GENESIS_FILE = Path("config/genesis.json")
GENESIS = b'{"chain_id":"local-dev-1","abci_genesis":{"genesis":[]}}\n'
MANIFEST = {"chain_id": "local-dev-1", "genesis_sha256": hashlib.sha256(GENESIS).hexdigest()}
FAKE_DOCKER = REPO_ROOT / "tests/fake_node_home_docker.py"


def has_gnu_tar() -> bool:
    """Ansible's unarchive needs GNU tar (Linux CI has it; macOS ships bsdtar)."""
    if shutil.which("gtar"):
        return True
    version = subprocess.run(["tar", "--version"], capture_output=True, text=True, check=False)
    return "GNU tar" in version.stdout


requires_gnu_tar = unittest.skipUnless(has_gnu_tar(), "unarchive needs GNU tar")


def signing_state(height: str) -> str:
    return json.dumps({"height": height, "round": 0, "step": 0})


def write_home(home: Path, *, height: str, marker: str) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "config" / "marker.txt").write_text(marker, encoding="utf-8")
    (home / "config" / "config.toml").write_text(
        'genesis_file = "config/genesis.json"\n'
        'priv_validator_state_file = "data/priv_validator_state.json"\n',
        encoding="utf-8",
    )
    (home / GENESIS_FILE).write_bytes(GENESIS)
    (home / STATE_FILE).write_text(signing_state(height), encoding="utf-8")


@requires_ansible
class PushHomeTest(PlaybookTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepared = self.workdir / "prepared"
        write_home(self.prepared, height="0", marker="prepared")
        self.archive = self.workdir / "home.tar.gz"
        self.create_archive()
        self.home = self.workdir / "remote" / ".cometbft"
        (self.workdir / "bin").mkdir()
        self.docker = self.workdir / "bin/docker"

    def create_archive(self) -> None:
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(self.prepared, arcname=".")

    def push_home(self, *, replace: bool, manifest=None, compose_script="raise SystemExit(8)"):
        self.docker.write_text(f"#!{sys.executable}\n" + FAKE_DOCKER.read_text() + "\n" + compose_script)
        self.docker.chmod(0o700)
        with patch.dict(os.environ, {"PATH": f"{self.docker.parent}{os.pathsep}{os.environ['PATH']}"}):
            return run_play(
                self.workdir,
                variables={
                    "xian_deploy_root": str(self.workdir / "remote"),
                    "xian_node_home_archive": str(self.archive),
                    "xian_node_home_replace": replace,
                    "xian_project_name": "test-node",
                },
                extra_vars={"xian_cometbft_home": str(self.home)},
                manifest=manifest,
                tasks=[{"ansible.builtin.import_role": {"name": "xian_node_home"}}],
            )

    @requires_gnu_tar
    def test_fresh_host_receives_the_prepared_home(self) -> None:
        self.assertPlaySucceeded(self.push_home(replace=True, manifest=MANIFEST))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "prepared")

    @requires_gnu_tar
    def test_home_without_signing_progress_may_be_replaced(self) -> None:
        write_home(self.home, height="0", marker="old")
        self.assertPlaySucceeded(self.push_home(replace=True))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "prepared")

    @requires_gnu_tar
    def test_prepared_home_can_overlay_unsigned_data(self) -> None:
        write_home(self.home, height="0", marker="old")
        extra = self.home / "config/custom.txt"
        extra.write_text("retain")

        self.assertPlaySucceeded(self.push_home(replace=False))

        self.assertEqual((self.home / "config/marker.txt").read_text(), "prepared")
        self.assertEqual(extra.read_text(), "retain")

    @requires_gnu_tar
    def test_invalid_incoming_genesis_preserves_the_home_before_stopping(self) -> None:
        write_home(self.home, height="0", marker="retain")
        runtime = self.workdir / "remote/runtime"
        runtime.mkdir(parents=True)
        (runtime / "docker-compose.yml").write_text("services: {}\n")
        stopped = runtime / "stopped"
        compose_script = (
            "from pathlib import Path\n"
            f"Path({str(stopped)!r}).touch()\nraise SystemExit(7)\n"
        )
        incoming_genesis = self.prepared / GENESIS_FILE
        for payload, message in (
            (None, "config/genesis.json"),
            (b" " + GENESIS, "genesis_sha256"),
        ):
            with self.subTest(payload=payload):
                if payload is None:
                    incoming_genesis.unlink()
                else:
                    incoming_genesis.write_bytes(payload)
                self.create_archive()

                result = self.push_home(replace=True, manifest=MANIFEST, compose_script=compose_script)

                self.assertPlayFailed(result, message)
                self.assertFalse(stopped.exists())
                self.assertEqual((self.home / GENESIS_FILE).read_bytes(), GENESIS)
                self.assertEqual((self.home / STATE_FILE).read_text(), signing_state("0"))
                self.assertEqual((self.home / "config/marker.txt").read_text(), "retain")

    def test_signing_state_is_never_replaced(self) -> None:
        for replace in (True, False):
            with self.subTest(replace=replace):
                write_home(self.home, height="42", marker="live")
                result = self.push_home(replace=replace)
                self.assertPlayFailed(result, "has signed up to height 42")
                self.assertEqual((self.home / STATE_FILE).read_text(), signing_state("42"))
                self.assertEqual((self.home / "config" / "marker.txt").read_text(), "live")

    def test_invalid_signing_height_never_allows_home_replacement(self) -> None:
        for height in ("not-a-height", "0.5", False):
            with self.subTest(height=height):
                write_home(self.home, height=height, marker="unverified")
                result = self.push_home(replace=True)
                self.assertPlayFailed(result, "cannot verify validator signing state")
                self.assertEqual((self.home / "config" / "marker.txt").read_text(), "unverified")

    def test_existing_home_without_signing_state_is_not_replaced(self) -> None:
        write_home(self.home, height="42", marker="unverified")
        (self.home / STATE_FILE).unlink()

        result = self.push_home(replace=True)

        self.assertPlayFailed(result, "cannot verify validator signing state")
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "unverified")

    def test_custom_or_unreadable_signing_configuration_preserves_the_home(self) -> None:
        configurations = (
            'priv_validator_state_file = "data/custom-state.json"\n',
            'priv_validator_state_file = "/root/.cometbft/custom-state.json"\n',
            'priv_validator_laddr = "tcp://signer:1234"\n',
            'priv_validator_state_file = "unterminated\n',
            None,
        )
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                write_home(self.home, height="0", marker="live-custom")
                custom_state = self.home / "data" / "custom-state.json"
                custom_state.write_text(signing_state("42"), encoding="utf-8")
                config_file = self.home / "config" / "config.toml"
                if configuration is None:
                    config_file.unlink()
                else:
                    config_file.write_text(configuration, encoding="utf-8")

                result = self.push_home(replace=True)

                self.assertPlayFailed(result, "cannot verify validator signing configuration")
                self.assertEqual(custom_state.read_text(), signing_state("42"))
                self.assertEqual((self.home / "config" / "marker.txt").read_text(), "live-custom")

    @requires_gnu_tar
    def test_runtime_is_stopped_and_signing_progress_rechecked_before_replacement(self) -> None:
        write_home(self.home, height="0", marker="live")
        runtime = self.workdir / "remote" / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "docker-compose.yml").write_text("services: {}\n")
        stopped = runtime / "stopped"
        compose_script = (
            "from pathlib import Path\n"
            f"Path({str(stopped)!r}).touch()\n"
            f"Path({str(self.home / STATE_FILE)!r}).write_text({signing_state('42')!r})\n"
        )
        result = self.push_home(replace=True, compose_script=compose_script)

        self.assertPlayFailed(result, "has signed up to height 42")
        self.assertTrue(stopped.exists())
        self.assertEqual((self.home / STATE_FILE).read_text(), signing_state("42"))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "live")


if __name__ == "__main__":
    unittest.main()
