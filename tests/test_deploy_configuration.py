"""Deploy-time node configuration rendered with Ansible's real templater."""

from __future__ import annotations

import unittest

from ansible_harness import (
    PlaybookTestCase,
    canonical_profile,
    option_values,
    render_configure_wrapper,
    requires_ansible,
    run_play,
)

GENESIS_TIME = "2026-06-21T00:00:00.000000Z"


def bundle_manifest(**overrides) -> dict:
    manifest = {
        "schema_version": 1,
        "name": "local-dev",
        "chain_id": "local-dev-1",
        "genesis": {"kind": "bundle", "bundle": "mainnet", "genesis_time": GENESIS_TIME},
        "runtime_features": {"zk": True},
    }
    manifest.update(overrides)
    return manifest


@requires_ansible
class SnapshotArgumentsTest(PlaybookTestCase):
    def test_deploy_configuration_never_restores_a_snapshot(self) -> None:
        profile = canonical_profile(
            snapshot_url="https://snapshots.example/manifest.json",
            snapshot_signing_keys=["c" * 64],
        )
        result, arguments = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlaySucceeded(result)
        self.assertEqual(
            [argument for argument in arguments if argument.startswith("--snapshot")], []
        )


@requires_ansible
class BundleGenesisTest(PlaybookTestCase):
    def test_bundle_genesis_uses_the_manifest_chain_time_and_runtime_features(self) -> None:
        result, arguments = render_configure_wrapper(self.workdir, manifest=bundle_manifest())

        self.assertPlaySucceeded(result)
        self.assertEqual(option_values(arguments, "--genesis-bundle"), ["mainnet"])
        self.assertEqual(option_values(arguments, "--chain-id"), ["local-dev-1"])
        self.assertEqual(option_values(arguments, "--genesis-time"), [GENESIS_TIME])
        self.assertIn("--runtime-feature-zk", arguments)
        self.assertNotIn("--no-runtime-feature-zk", arguments)

    def test_disabled_runtime_features_are_passed_explicitly(self) -> None:
        result, arguments = render_configure_wrapper(
            self.workdir, manifest=bundle_manifest(runtime_features={"zk": False})
        )

        self.assertPlaySucceeded(result)
        self.assertIn("--no-runtime-feature-zk", arguments)

    def test_profile_bundle_genesis_overrides_the_manifest_like_node_init(self) -> None:
        profile = canonical_profile(
            genesis={"kind": "bundle", "bundle": "testnet", "genesis_time": "2026-03-30T00:00:00Z"}
        )
        result, arguments = render_configure_wrapper(
            self.workdir, profile=profile, manifest=bundle_manifest()
        )

        self.assertPlaySucceeded(result)
        self.assertEqual(option_values(arguments, "--genesis-bundle"), ["testnet"])
        self.assertEqual(option_values(arguments, "--genesis-time"), ["2026-03-30T00:00:00Z"])

    def test_bundle_genesis_without_fixed_time_is_rejected(self) -> None:
        manifest = bundle_manifest(genesis={"kind": "bundle", "bundle": "mainnet"})
        result, _ = render_configure_wrapper(self.workdir, manifest=manifest)

        self.assertPlayFailed(result, "genesis_time")

    def test_profile_bundle_genesis_requires_the_network_manifest(self) -> None:
        profile = canonical_profile(
            genesis={"kind": "bundle", "bundle": "mainnet", "genesis_time": GENESIS_TIME}
        )
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "xian_network_manifest")

    def test_inventory_chain_id_must_match_the_manifest(self) -> None:
        result, _ = render_configure_wrapper(
            self.workdir, manifest=bundle_manifest(), variables={"xian_chain_id": "other-1"}
        )

        self.assertPlayFailed(result, "xian_chain_id")

    def test_manifest_source_genesis_keeps_the_pushed_home_genesis(self) -> None:
        manifest = bundle_manifest(genesis={"kind": "source", "source": "./genesis.json"})
        result, arguments = render_configure_wrapper(self.workdir, manifest=manifest)

        self.assertPlaySucceeded(result)
        self.assertEqual(
            [argument for argument in arguments if argument.startswith("--genesis")], []
        )
        self.assertNotIn("--chain-id", arguments)


@requires_ansible
class PublicRpcTest(PlaybookTestCase):
    def rpc_bind(self, **variables):
        report = self.workdir / "rpc.txt"
        result = run_play(
            self.workdir,
            variables=variables,
            tasks=[
                {
                    "ansible.builtin.copy": {
                        "dest": str(report),
                        "content": "{{ xian_rpc_bind_host }}",
                    }
                }
            ],
        )
        return result, report.read_text() if report.exists() else None

    def test_rpc_is_published_on_loopback_by_default(self) -> None:
        result, bind_host = self.rpc_bind()

        self.assertPlaySucceeded(result)
        self.assertEqual(bind_host, "127.0.0.1")

    def test_public_rpc_bind_requires_explicit_opt_in(self) -> None:
        for host in ("0.0.0.0", "::", "203.0.113.10"):
            with self.subTest(host=host):
                result, _ = self.rpc_bind(xian_rpc_bind_host=host)
                self.assertPlayFailed(result, "xian_public_rpc_enabled")

    def test_public_rpc_bind_is_allowed_after_opt_in(self) -> None:
        result, bind_host = self.rpc_bind(
            xian_rpc_bind_host="0.0.0.0", xian_public_rpc_enabled=True
        )

        self.assertPlaySucceeded(result)
        self.assertEqual(bind_host, "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
