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


FEE_OPTIONS = ("--tx-fee-mode", "--max-tx-chi", "--max-block-chi")
FREE_POLICY = {
    "tx_fee_mode": "free_metered",
    "max_tx_chi": 150000,
    "max_block_chi": 400000,
}
PAID_POLICY = {
    "tx_fee_mode": "paid_metered",
    "max_tx_chi": 100000,
    "max_block_chi": 300000,
}


@requires_ansible
class GenesisFeePolicyTest(PlaybookTestCase):
    def test_bundle_genesis_passes_the_manifest_fee_policy(self) -> None:
        for index, policy in enumerate((FREE_POLICY, PAID_POLICY)):
            with self.subTest(mode=policy["tx_fee_mode"]):
                workdir = self.workdir / str(index)
                workdir.mkdir()
                result, arguments = render_configure_wrapper(
                    workdir, manifest=bundle_manifest(fee_policy=policy)
                )

                self.assertPlaySucceeded(result)
                self.assertEqual(
                    option_values(arguments, "--tx-fee-mode"), [policy["tx_fee_mode"]]
                )
                self.assertEqual(
                    option_values(arguments, "--max-tx-chi"), [str(policy["max_tx_chi"])]
                )
                self.assertEqual(
                    option_values(arguments, "--max-block-chi"), [str(policy["max_block_chi"])]
                )

    def test_bundle_genesis_without_fee_policy_uses_the_paid_default(self) -> None:
        result, arguments = render_configure_wrapper(self.workdir, manifest=bundle_manifest())

        self.assertPlaySucceeded(result)
        self.assertEqual([argument for argument in arguments if argument in FEE_OPTIONS], [])

    def test_configuring_an_existing_genesis_never_passes_fee_options(self) -> None:
        result, arguments = render_configure_wrapper(self.workdir)

        self.assertPlaySucceeded(result)
        self.assertEqual([argument for argument in arguments if argument in FEE_OPTIONS], [])

    def test_profile_fee_settings_are_rejected(self) -> None:
        profile = canonical_profile(tx_fee_mode="free_metered")
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "fee_policy")

    def test_configure_wrapper_passes_no_parallel_execution_options(self) -> None:
        result, arguments = render_configure_wrapper(self.workdir)

        self.assertPlaySucceeded(result)
        self.assertEqual(
            [argument for argument in arguments if "parallel-execution" in str(argument)], []
        )

    def test_simulation_chi_cap_is_passed_only_when_the_profile_sets_one(self) -> None:
        cases = (
            ("unset", canonical_profile(), []),
            ("null", canonical_profile(simulation_max_chi=None), []),
            ("set", canonical_profile(simulation_max_chi=50000), ["50000"]),
        )
        for name, profile, expected in cases:
            with self.subTest(name=name):
                workdir = self.workdir / f"simulation-{name}"
                workdir.mkdir()
                result, arguments = render_configure_wrapper(workdir, profile=profile)
                self.assertPlaySucceeded(result)
                values = [
                    arguments[index + 1]
                    for index, argument in enumerate(arguments)
                    if argument == "--simulation-max-chi"
                ]
                self.assertEqual(values, expected)

    def test_removed_parallel_execution_settings_are_rejected(self) -> None:
        for index, profile in enumerate(
            (
                canonical_profile(parallel_execution_enabled=False),
                canonical_profile(
                    advanced={
                        "cometbft": {},
                        "statesync": {},
                        "metrics": {},
                        "pending_nonce": {},
                        "parallel_execution": {},
                    }
                ),
            )
        ):
            with self.subTest(index=index):
                workdir = self.workdir / f"parallel-{index}"
                workdir.mkdir()
                result, _ = render_configure_wrapper(workdir, profile=profile)
                self.assertPlayFailed(result, "parallel executor was removed")

    def test_unknown_profile_keys_are_rejected_by_name(self) -> None:
        profile = canonical_profile(monitoring_profile="none")
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "unknown key(s): monitoring_profile")

    def test_fee_policy_requires_a_bundle_manifest_genesis(self) -> None:
        manifest = bundle_manifest(
            genesis={"kind": "source", "source": "./genesis.json"}, fee_policy=FREE_POLICY
        )
        result, _ = render_configure_wrapper(self.workdir, manifest=manifest)

        self.assertPlayFailed(result, "only with a bundle genesis")

    def test_manifest_fee_policy_must_be_canonical(self) -> None:
        for index, fee_policy in enumerate(
            (
                FREE_POLICY | {"tx_fee_mode": "gratis"},
                # Canonical policies always carry both caps.
                {"tx_fee_mode": "paid_metered"},
                {"tx_fee_mode": "free_metered", "max_tx_chi": 10},
                FREE_POLICY | {"max_tx_chi": 0},
                FREE_POLICY | {"max_tx_chi": 10, "max_block_chi": 9},
                FREE_POLICY | {"max_tx_chi": True},
                FREE_POLICY | {"extra": 1},
                # The pre-revision-11 field names are gone.
                {"tx_fee_mode": "free_metered", "free_tx_max_chi": 1, "free_block_max_chi": 2},
            )
        ):
            with self.subTest(fee_policy=fee_policy):
                workdir = self.workdir / str(index)
                workdir.mkdir()
                result, _ = render_configure_wrapper(
                    workdir, manifest=bundle_manifest(fee_policy=fee_policy)
                )
                self.assertPlayFailed(result, "fee_policy")


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



@requires_ansible
class AppMetricsTest(PlaybookTestCase):
    """The node listens on 0.0.0.0:9108 in the container; the profile sets the host side."""

    def profile(self, metrics: dict) -> dict:
        profile = canonical_profile()
        profile["advanced"]["metrics"] = metrics
        return profile

    def published(self, metrics: dict):
        report = self.workdir / "metrics.json"
        result = run_play(
            self.workdir,
            variables={},
            profile=self.profile(metrics),
            tasks=[
                {
                    "ansible.builtin.copy": {
                        "dest": str(report),
                        "content": (
                            '{"host": "{{ xian_app_metrics_bind_host }}", '
                            '"port": {{ xian_app_metrics_port }}}'
                        ),
                    }
                }
            ],
        )
        return result, report.read_text() if report.exists() else None

    def test_node_listens_on_the_fixed_container_address(self) -> None:
        result, arguments = render_configure_wrapper(
            self.workdir, profile=self.profile({"host": "127.0.0.1", "port": 39108})
        )

        self.assertPlaySucceeded(result)
        self.assertEqual(option_values(arguments, "--metrics-host"), ["0.0.0.0"])
        self.assertEqual(option_values(arguments, "--metrics-port"), ["9108"])

    def test_profile_host_and_port_are_the_published_side(self) -> None:
        result, published = self.published({"host": "10.0.0.5", "port": 39108})

        self.assertPlaySucceeded(result)
        self.assertEqual(published, '{"host": "10.0.0.5", "port": 39108}')

    def test_health_checks_probe_the_published_address(self) -> None:
        cases = [
            ({}, "http://127.0.0.1:9108/metrics"),
            ({"host": "0.0.0.0"}, "http://127.0.0.1:9108/metrics"),
            ({"host": "::"}, "http://127.0.0.1:9108/metrics"),
            ({"host": "[::]"}, "http://127.0.0.1:9108/metrics"),
            ({"host": "::1"}, "http://127.0.0.1:9108/metrics"),
            ({"host": "localhost"}, "http://127.0.0.1:9108/metrics"),
            ({"host": "10.0.0.5", "port": 39108}, "http://10.0.0.5:39108/metrics"),
            ({"host": "2001:db8::10"}, "http://[2001:db8::10]:9108/metrics"),
            ({"host": "[2001:DB8::10]"}, "http://[2001:db8::10]:9108/metrics"),
        ]
        for index, (metrics, expected) in enumerate(cases):
            with self.subTest(metrics=metrics):
                workdir = self.workdir / str(index)
                workdir.mkdir()
                report = workdir / "url.txt"
                result = run_play(
                    workdir,
                    variables={},
                    profile=self.profile(metrics),
                    tasks=[
                        {
                            "ansible.builtin.copy": {
                                "dest": str(report),
                                "content": "{{ xian_app_metrics_probe_url }}",
                            }
                        }
                    ],
                )
                self.assertPlaySucceeded(result)
                self.assertEqual(report.read_text(), expected)

    def test_metrics_are_published_locally_by_default(self) -> None:
        result, published = self.published({})

        self.assertPlaySucceeded(result)
        self.assertEqual(published, '{"host": "127.0.0.1", "port": 9108}')

if __name__ == "__main__":
    unittest.main()
