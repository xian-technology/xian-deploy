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
class PreparedHomeArgumentsTest(PlaybookTestCase):
    def test_deploy_ignores_genesis_preparation_inputs(self) -> None:
        bundle = {"kind": "bundle", "bundle": "mainnet", "genesis_time": GENESIS_TIME}
        source = {"kind": "source", "source": "./genesis.json"}
        cases = (
            ("bundle-manifest", {}, bundle),
            ("source-profile", {"genesis": source}, bundle),
            ("bundle-profile", {"genesis": bundle}, source),
        )
        for name, overrides, manifest_genesis in cases:
            with self.subTest(name=name):
                workdir = self.workdir / name
                workdir.mkdir()
                result, arguments = render_configure_wrapper(
                    workdir,
                    profile=canonical_profile(**overrides),
                    manifest=bundle_manifest(
                        genesis=manifest_genesis,
                        genesis_sha256="ab" * 32,
                        fee_policy={
                            "tx_fee_mode": "free_metered",
                            "max_tx_chi": 150000,
                            "max_block_chi": 400000,
                        },
                    ),
                )

                self.assertPlaySucceeded(result)
                self.assertFalse(any(argument.startswith("--genesis") for argument in arguments))
                self.assertTrue(
                    {
                        "--chain-id",
                        "--runtime-feature-zk",
                        "--no-runtime-feature-zk",
                        "--tx-fee-mode",
                        "--max-tx-chi",
                        "--max-block-chi",
                    }.isdisjoint(arguments)
                )

    def test_inventory_chain_id_must_match_the_manifest(self) -> None:
        result, _ = render_configure_wrapper(
            self.workdir, manifest=bundle_manifest(), variables={"xian_chain_id": "other-1"}
        )

        self.assertPlayFailed(result, "xian_chain_id")


@requires_ansible
class NodeConfigurationTest(PlaybookTestCase):
    def test_profile_fee_settings_are_rejected(self) -> None:
        profile = canonical_profile(tx_fee_mode="free_metered")
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "fee_policy")

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

    def test_profile_external_address_is_passed_to_configure(self) -> None:
        def advanced(cometbft: dict) -> dict:
            return {"cometbft": cometbft, "metrics": {}, "pending_nonce": {}}

        cases = (
            ("unset", canonical_profile(), [""]),
            (
                "set",
                canonical_profile(advanced=advanced({"external_address": "203.0.113.10:26656"})),
                ["203.0.113.10:26656"],
            ),
        )
        for name, profile, expected in cases:
            with self.subTest(name=name):
                workdir = self.workdir / f"external-address-{name}"
                workdir.mkdir()
                result, arguments = render_configure_wrapper(workdir, profile=profile)
                self.assertPlaySucceeded(result)
                self.assertEqual(option_values(arguments, "--p2p-external-address"), expected)

    def test_unknown_advanced_profile_keys_are_rejected(self) -> None:
        profile = canonical_profile(
            advanced={"cometbft": {}, "metrics": {}, "pending_nonce": {}, "typo": {}}
        )
        result, _ = render_configure_wrapper(self.workdir, profile=profile)
        self.assertPlayFailed(result, "Fix unknown")

    def test_unknown_profile_keys_are_rejected_by_name(self) -> None:
        profile = canonical_profile(monitoring_profile="none")
        result, _ = render_configure_wrapper(self.workdir, profile=profile)

        self.assertPlayFailed(result, "unknown key(s): monitoring_profile")


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
