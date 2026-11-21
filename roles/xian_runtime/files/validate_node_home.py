"""Validate the remote node home's installed configuration and genesis."""

import hashlib
import json
import sys
import tomllib
from pathlib import Path


def prepared_file(home: Path, name: str) -> Path:
    path = (home / name).resolve()
    if not path.is_relative_to(home) or not path.is_file():
        raise ValueError(f"{name} must be a file inside the node home")
    return path


def read_cometbft_config(home: Path) -> dict:
    path = prepared_file(home, "config/config.toml")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read rendered CometBFT configuration {path}: {exc}") from exc


def reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def genesis_chain_id(data: bytes) -> str:
    try:
        genesis = json.loads(data.decode("utf-8"), parse_constant=reject_nonfinite_json)
    except ValueError as exc:
        raise ValueError("config/genesis.json is not valid Xian genesis JSON") from exc
    if not isinstance(genesis, dict):
        raise ValueError("config/genesis.json must contain a Xian genesis object")
    chain_id = genesis.get("chain_id")
    if not isinstance(chain_id, str) or not chain_id.strip():
        raise ValueError("config/genesis.json must have a nonempty chain_id")
    state = genesis.get("abci_genesis")
    if not isinstance(state, dict) or not isinstance(state.get("genesis"), list):
        raise ValueError("config/genesis.json must contain abci_genesis.genesis state")
    return chain_id


def validate_genesis(home: Path, config: dict, expected_chain_id: str, expected_pin: str) -> None:
    genesis_path = prepared_file(home, "config/genesis.json")
    configured_genesis = config.get("genesis_file")
    if (
        not isinstance(configured_genesis, str)
        or (home / configured_genesis).resolve() != genesis_path
    ):
        raise ValueError("CometBFT genesis_file must resolve to config/genesis.json used by Xian")

    data = genesis_path.read_bytes()
    chain_id = genesis_chain_id(data)
    if expected_chain_id and chain_id != expected_chain_id:
        raise ValueError(f"genesis chain_id {chain_id!r} must match {expected_chain_id!r}")
    if expected_pin and hashlib.sha256(data).hexdigest() != expected_pin:
        raise ValueError(
            "config/genesis.json bytes do not match the network manifest genesis_sha256"
        )


def main(home: Path, mode: str, chain_id: str, pin: str) -> None:
    from xian.state_sync_policy import validate_comet_state_sync_disabled

    home = home.resolve()
    config = read_cometbft_config(home)
    validate_comet_state_sync_disabled(config)
    if mode == "genesis":
        validate_genesis(home, config, chain_id, pin)
    elif mode != "config":
        raise ValueError(f"Unknown prepared node home validation mode: {mode}")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]), *sys.argv[2:])
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Cannot validate the prepared node home: {exc}") from exc
