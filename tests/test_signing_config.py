"""The deployment guard must verify the configuration before trusting a default file."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "signing_config", ROOT / "roles/xian_node_home/filter_plugins/signing_config.py"
)
signing_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signing_config)


class SigningConfigurationTest(unittest.TestCase):
    def test_local_default_and_cometbft_defaults_are_verifiable(self):
        for config in (
            "",
            'priv_validator_state_file = "data/priv_validator_state.json"\n',
            'priv_validator_laddr = ""\n',
            '[other]\npriv_validator_state_file = "ignored"\n',
        ):
            with self.subTest(config=config):
                self.assertIs(signing_config.uses_default_local_signing_state(config), True)

    def test_custom_paths_and_remote_signers_are_not_verifiable(self):
        for config in (
            'priv_validator_state_file = "data/other.json"\n',
            'priv_validator_state_file = "/root/.cometbft/data/priv_validator_state.json"\n',
            'priv_validator_state_file = ""\n',
            "priv_validator_state_file = false\n",
            'priv_validator_laddr = "tcp://signer:1234"\n',
            "priv_validator_laddr = false\n",
        ):
            with self.subTest(config=config):
                self.assertIs(signing_config.uses_default_local_signing_state(config), False)

    def test_invalid_toml_is_reported_as_unverifiable(self):
        with self.assertRaisesRegex(ValueError, "cannot verify validator signing configuration"):
            signing_config.uses_default_local_signing_state('priv_validator_state_file = "bad\n')

    def test_filter_registration_uses_the_same_guard(self):
        self.assertIs(
            signing_config.FilterModule().filters()["uses_default_local_signing_state"],
            signing_config.uses_default_local_signing_state,
        )


if __name__ == "__main__":
    unittest.main()
