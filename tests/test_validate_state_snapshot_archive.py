from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_state_snapshot_archive.py"
APP_HASH = "a" * 64


def write_snapshot(
    directory: Path,
    *,
    chain_id: str = "xian-test-1",
    height: int = 42,
    app_hash: str = APP_HASH,
    member_name: str = "metadata.json",
) -> Path:
    metadata = {
        "snapshot_format_version": 1,
        "chain_id": chain_id,
        "height": height,
        "app_hash": app_hash,
    }
    state = {
        "number": height,
        "hash": app_hash,
        "state": {},
    }
    metadata_path = directory / "metadata.json"
    state_path = directory / "exported_state.json"
    archive_path = directory / "snapshot.tar.gz"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(metadata_path, arcname=member_name)
        archive.add(state_path, arcname="exported_state.json")
    return archive_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ValidateStateSnapshotArchiveTest(unittest.TestCase):
    def run_validator(self, archive: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--archive", str(archive), *extra_args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_accepts_matching_archive_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_snapshot(Path(tmp))
            result = self.run_validator(
                archive,
                "--sha256",
                sha256_file(archive),
                "--expected-chain-id",
                "xian-test-1",
                "--expected-height",
                "42",
                "--expected-app-hash",
                APP_HASH,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["chain_id"], "xian-test-1")
        self.assertEqual(payload["height"], 42)
        self.assertEqual(payload["app_hash"], APP_HASH)

    def test_rejects_sha256_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_snapshot(Path(tmp))
            result = self.run_validator(
                archive,
                "--sha256",
                "0" * 64,
                "--expected-chain-id",
                "xian-test-1",
                "--expected-height",
                "42",
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha256 mismatch", result.stderr)

    def test_rejects_chain_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_snapshot(Path(tmp), chain_id="wrong-chain")
            result = self.run_validator(
                archive,
                "--sha256",
                sha256_file(archive),
                "--expected-chain-id",
                "xian-test-1",
                "--expected-height",
                "42",
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("chain_id mismatch", result.stderr)

    def test_rejects_height_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_snapshot(Path(tmp), height=40)
            result = self.run_validator(
                archive,
                "--sha256",
                sha256_file(archive),
                "--expected-chain-id",
                "xian-test-1",
                "--expected-height",
                "42",
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("height mismatch", result.stderr)

    def test_rejects_unsafe_member_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = write_snapshot(Path(tmp), member_name="../metadata.json")
            result = self.run_validator(
                archive,
                "--sha256",
                sha256_file(archive),
                "--expected-chain-id",
                "xian-test-1",
                "--expected-height",
                "42",
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe snapshot member path", result.stderr)


if __name__ == "__main__":
    unittest.main()
