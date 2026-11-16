#!/usr/bin/env python3
"""Hermetic Docker command fixture; the real guard supplies all mount logic."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys


def record_command(args):
    guards = [
        {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
        for path in Path(os.environ["TMPDIR"]).glob("xian-node-store-check-stopped-*")
        if path.is_file()
    ]
    with Path(os.environ["GUARD_DOCKER_LOG"]).open("a") as handle:
        handle.write(json.dumps({"args": args, "guards": guards}) + "\n")


def emit_asset():
    proof = os.environ.get("GUARD_FAKE_PROOF")
    if proof is None:
        sys.stdout.buffer.write(Path(os.environ["GUARD_SOURCE_ASSET"]).read_bytes())
    else:
        sys.stdout.write("import sys\nsys.stdout.write(" + repr(proof + "\n") + ")\n")


def main():
    args = sys.argv[1:]
    record_command(args)
    if args[0] == os.environ.get("GUARD_DOCKER_FAILURE"):
        print("fake Docker query failed", file=sys.stderr)
        return 7
    if args[0] == "run":
        emit_asset()
    elif args[0] == "ps":
        print("other-project-1" if os.environ["GUARD_CONTAINER_ROWS"] != "[]" else "")
    elif args[0] == "inspect":
        print(os.environ["GUARD_CONTAINER_ROWS"])
    elif args[0] != "compose":
        return 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
