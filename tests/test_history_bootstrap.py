"""Use Ansible's real role/template boundary for state-sync artifact intent."""

from __future__ import annotations

import unittest
from copy import deepcopy

from ansible_harness import (
    PlaybookTestCase,
    canonical_profile,
    requires_ansible,
    run_play,
)


def history_release() -> dict:
    return {
        "schema_version": 1,
        "build": {
            "cometbft_version": "0.40.0",
            "cometbft_source_commit": "d" * 40,
            "cometbft_source_url": "https://codeload.github.com/cometbft/cometbft/tar.gz/"
            + "d" * 40,
            "cometbft_source_sha256": "e" * 64,
            "cometbft_patch_path": "docker/cometbft-patches/0001-verified-evidence-history.patch",
            "cometbft_patch_sha256": "f" * 64,
            "cometbft_history_revision": "1",
        },
    }


def sync_profile(*, release=None, enabled=True):
    profile = canonical_profile()
    if release is not None:
        profile["node_release_manifest"] = release
    profile["advanced"]["statesync"] = {
        "enabled": enabled,
        "rpc_servers": ["http://one:26657", "http://two:26657"],
        "trust_height": 42,
        "trust_hash": "ab" * 32,
        "trust_period": "168h0m0s",
    }
    return profile


@requires_ansible
class HistoryArtifactTest(PlaybookTestCase):
    def test_missing_history_identity_refuses_state_sync_before_deployment(self):
        result = run_play(self.workdir, profile=sync_profile(), variables={}, tasks=[])
        self.assertPlayFailed(result, "history")

    def test_supported_identity_is_consumed_as_intended_metadata(self):
        release = history_release()
        result = run_play(
            self.workdir,
            profile=sync_profile(release=release),
            variables={},
            tasks=[
                {
                    "ansible.builtin.assert": {
                        "that": [
                            "xian_statesync_history_build.cometbft_history_revision == '1'",
                            "xian_statesync_history_build.cometbft_patch_sha256 == '"
                            + "f" * 64
                            + "'",
                        ]
                    }
                },
            ],
        )
        self.assertPlaySucceeded(result)

    def test_network_release_metadata_is_used_when_profile_has_no_override(self):
        result = run_play(
            self.workdir,
            profile=sync_profile(),
            manifest={"node_release_manifest": history_release()},
            variables={},
            tasks=[
                {
                    "ansible.builtin.assert": {
                        "that": [
                            "xian_statesync_history_build.cometbft_history_revision == '1'"
                        ]
                    }
                },
            ],
        )
        self.assertPlaySucceeded(result)

    def test_profile_override_does_not_fall_back_to_other_network_artifact(self):
        wrong = history_release()
        wrong["build"]["cometbft_history_revision"] = "2"
        result = run_play(
            self.workdir,
            profile=sync_profile(release=wrong),
            manifest={"node_release_manifest": history_release()},
            variables={},
            tasks=[],
        )
        self.assertPlayFailed(result, "history")

    def test_ordinary_legacy_replay_needs_no_history_build_metadata(self):
        result = run_play(
            self.workdir, profile=sync_profile(enabled=False), variables={}, tasks=[]
        )
        self.assertPlaySucceeded(result)

    def test_malformed_history_metadata_is_rejected(self):
        mutations = [
            ("schema_version", True),
            ("build", []),
            ("cometbft_version", "0.39.3"),
            ("cometbft_history_revision", 1),
            ("cometbft_history_revision", "2"),
            ("cometbft_source_commit", "D" * 40),
            ("cometbft_source_url", "https://example.invalid/source.tar.gz"),
            ("cometbft_source_sha256", "E" * 64),
            ("cometbft_patch_sha256", "F" * 64),
            ("cometbft_patch_path", "docker/cometbft-patches/../bad.patch"),
            ("cometbft_patch_path", "/tmp/bad.patch"),
            ("cometbft_patch_sha256", "f" * 64 + "\n"),
        ]
        for i, (field, value) in enumerate(mutations):
            with self.subTest(field=field, value=value):
                directory = self.workdir / str(i)
                directory.mkdir()
                release = deepcopy(history_release())
                if field in ["schema_version", "build"]:
                    release[field] = value
                else:
                    release["build"][field] = value
                result = run_play(
                    directory,
                    profile=sync_profile(release=release),
                    variables={},
                    tasks=[],
                )
                self.assertPlayFailed(result, "history")


if __name__ == "__main__":
    unittest.main()
