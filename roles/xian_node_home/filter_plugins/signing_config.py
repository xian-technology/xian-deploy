"""Identify the local signing state that push-home can verify on the host."""

import tomllib

DEFAULT_SIGNING_STATE = "data/priv_validator_state.json"


def uses_default_local_signing_state(config_text: str) -> bool:
    try:
        config = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(
            "cannot verify validator signing configuration: invalid config.toml"
        ) from exc
    return (
        config.get("priv_validator_state_file", DEFAULT_SIGNING_STATE) == DEFAULT_SIGNING_STATE
        and config.get("priv_validator_laddr", "") == ""
    )


class FilterModule:
    def filters(self):
        return {"uses_default_local_signing_state": uses_default_local_signing_state}
