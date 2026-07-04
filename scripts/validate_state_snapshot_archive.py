#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


SNAPSHOT_METADATA_FILENAME = "metadata.json"
SNAPSHOT_STATE_FILENAME = "exported_state.json"
SNAPSHOT_FORMAT_VERSION = 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_sha256(value: str, label: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{label} must be a 64-character hex string")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a 64-character hex string") from exc
    return value.lower()


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if name in {"", "."} or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe snapshot member path: {name}")


def _load_snapshot_metadata(archive_path: Path) -> dict[str, Any]:
    if not tarfile.is_tarfile(archive_path):
        raise ValueError("snapshot archive must be a tar or tar.gz file")

    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        for member in members:
            _validate_member_name(member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsafe snapshot member type: {member.name}")

        metadata_members = [
            member
            for member in members
            if member.name == SNAPSHOT_METADATA_FILENAME and member.isfile()
        ]
        if len(metadata_members) != 1:
            raise ValueError("snapshot archive must contain one metadata.json file")

        state_members = [
            member
            for member in members
            if member.name == SNAPSHOT_STATE_FILENAME and member.isfile()
        ]
        if len(state_members) != 1:
            raise ValueError("snapshot archive must contain one exported_state.json file")

        metadata_handle = archive.extractfile(metadata_members[0])
        if metadata_handle is None:
            raise ValueError("snapshot metadata.json could not be read")
        try:
            metadata = json.loads(metadata_handle.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("snapshot metadata.json must be valid JSON") from exc
        if not isinstance(metadata, dict):
            raise ValueError("snapshot metadata.json must contain a JSON object")
        return metadata


def validate_archive(
    *,
    archive_path: Path,
    expected_sha256: str,
    expected_chain_id: str,
    expected_height: int,
    expected_app_hash: str,
) -> dict[str, Any]:
    if not archive_path.exists():
        raise FileNotFoundError(f"snapshot archive not found: {archive_path}")
    if not archive_path.is_file():
        raise ValueError(f"snapshot archive is not a regular file: {archive_path}")

    expected_sha256 = _normalize_sha256(expected_sha256, "expected sha256")
    if expected_app_hash:
        expected_app_hash = _normalize_sha256(expected_app_hash, "expected app hash")

    if not expected_chain_id:
        raise ValueError("expected chain id must be non-empty")
    if expected_height <= 0:
        raise ValueError("expected height must be a positive integer")

    actual_sha256 = _sha256_file(archive_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"snapshot archive sha256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    metadata = _load_snapshot_metadata(archive_path)
    if int(metadata.get("snapshot_format_version", 0)) != SNAPSHOT_FORMAT_VERSION:
        raise ValueError("unsupported snapshot format version")

    chain_id = metadata.get("chain_id")
    if not isinstance(chain_id, str) or chain_id == "":
        raise ValueError("snapshot chain_id metadata must be a non-empty string")
    if chain_id != expected_chain_id:
        raise ValueError(
            f"snapshot chain_id mismatch: expected {expected_chain_id}, got {chain_id}"
        )

    height = metadata.get("height")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError("snapshot height metadata must be a positive integer")
    if height != expected_height:
        raise ValueError(
            f"snapshot height mismatch: expected {expected_height}, got {height}"
        )

    app_hash = metadata.get("app_hash")
    if not isinstance(app_hash, str) or app_hash == "":
        raise ValueError("snapshot app_hash metadata must be a non-empty string")
    if expected_app_hash and app_hash.lower() != expected_app_hash:
        raise ValueError(
            f"snapshot app hash mismatch: expected {expected_app_hash}, got {app_hash}"
        )

    return {
        "archive": str(archive_path),
        "sha256": actual_sha256,
        "chain_id": chain_id,
        "height": height,
        "app_hash": app_hash,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a Xian state snapshot archive before restore",
    )
    parser.add_argument("--archive", required=True, help="local snapshot archive path")
    parser.add_argument("--sha256", required=True, help="expected archive SHA-256")
    parser.add_argument("--expected-chain-id", required=True, help="expected chain id")
    parser.add_argument(
        "--expected-height",
        required=True,
        type=int,
        help="expected snapshot height from metadata.json",
    )
    parser.add_argument(
        "--expected-app-hash",
        default="",
        help="optional expected app hash from metadata.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = validate_archive(
            archive_path=Path(args.archive).expanduser().resolve(),
            expected_sha256=args.sha256,
            expected_chain_id=args.expected_chain_id,
            expected_height=args.expected_height,
            expected_app_hash=args.expected_app_hash,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
