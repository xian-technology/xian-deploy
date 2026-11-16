"""push-home places a prepared node home; it never resets a validator's signing state."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ansible_harness import PlaybookTestCase, requires_ansible, run_play

STATE_FILE = Path("data/priv_validator_state.json")


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
        'priv_validator_state_file = "data/priv_validator_state.json"\n', encoding="utf-8"
    )
    (home / STATE_FILE).write_text(signing_state(height), encoding="utf-8")


@requires_ansible
class PushHomeTest(PlaybookTestCase):
    def setUp(self) -> None:
        super().setUp()
        prepared = self.workdir / "prepared"
        write_home(prepared, height="0", marker="prepared")
        self.archive = self.workdir / "home.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(prepared, arcname=".")
        self.home = self.workdir / "remote" / ".cometbft"

    def push_home(self, *, replace: bool):
        return run_play(
            self.workdir,
            variables={
                "xian_deploy_root": str(self.workdir / "remote"),
                "xian_cometbft_home": str(self.home),
                "xian_node_home_archive": str(self.archive),
                "xian_node_home_replace": replace,
                "xian_project_name": "test-node",
            },
            tasks=[{"ansible.builtin.import_role": {"name": "xian_node_home"}}],
        )

    @requires_gnu_tar
    def test_fresh_host_receives_the_prepared_home(self) -> None:
        self.assertPlaySucceeded(self.push_home(replace=True))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "prepared")

    @requires_gnu_tar
    def test_home_without_signing_progress_may_be_replaced(self) -> None:
        write_home(self.home, height="0", marker="old")
        self.assertPlaySucceeded(self.push_home(replace=True))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "prepared")

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

    def test_runtime_is_stopped_and_signing_progress_rechecked_before_replacement(self) -> None:
        write_home(self.home, height="0", marker="live")
        runtime = self.workdir / "remote" / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "docker-compose.yml").write_text("services: {}\n")
        stopped = runtime / "stopped"
        fake_bin = self.workdir / "bin"
        fake_bin.mkdir()
        docker = fake_bin / "docker"
        docker.write_text(
            f"#!{sys.executable}\nfrom pathlib import Path\n"
            f"Path({str(stopped)!r}).touch()\n"
            f"Path({str(self.home / STATE_FILE)!r}).write_text({signing_state('42')!r})\n"
        )
        docker.chmod(0o700)

        with patch.dict(os.environ, {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}):
            result = self.push_home(replace=True)

        self.assertPlayFailed(result, "has signed up to height 42")
        self.assertTrue(stopped.exists())
        self.assertEqual((self.home / STATE_FILE).read_text(), signing_state("42"))
        self.assertEqual((self.home / "config" / "marker.txt").read_text(), "live")


if __name__ == "__main__":
    unittest.main()
