"""Validation at the private inventory and live WireGuard boundaries."""

import base64
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "roles/xian_runtime/files")
)
import private_validator_transport as transport


def key(n):
    return base64.b64encode(bytes([n]) * 32).decode()


def policy():
    return {
        "anchor": "validator-net",
        "interface": "wg0",
        "peers": [
            {
                "wireguard_public_key": key(1),
                "comet_peer": "ab" * 20 + "@10.9.0.2:26656",
            },
            {
                "wireguard_public_key": key(2),
                "comet_peer": "bc" * 20 + "@[fd10::3]:26656",
            },
        ],
    }


class PrivateTransportTest(unittest.TestCase):
    def test_wireguard_peer_routes_and_nonempty_unique_pairwise_secrets(self):
        allowed = {key(1): "10.9.0.2/32", key(2): "fd10::3/128"}
        psk = {key(1): key(3), key(2): key(4)}
        transport.check_peers(policy(), allowed, psk)
        for routes, secrets in [
            ({**allowed, key(1): "0.0.0.0/0"}, psk),
            ({**allowed, key(1): "10.9.0.5/32"}, psk),
            ({**allowed, key(1): "10.9.0.2/32,10.9.0.8/32"}, psk),
            ({**allowed, key(10): "10.9.0.10/32"}, psk),
            (allowed, {**psk, key(2): key(3)}),
            (allowed, {**psk, key(1): key(0)}),
            (allowed, {**psk, key(1): "(none)"}),
            (allowed, {}),
        ]:
            with self.assertRaises(ValueError):
                transport.check_peers(policy(), routes, secrets)

    def test_only_literal_and_unique_comet_endpoints_are_accepted(self):
        for bad in (
            "localhost:26656",
            "0.0.0.0:26656",
            "127.0.0.1:26656",
            "10.9.0.2:invalid",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p = policy()
                p["peers"][0]["comet_peer"] = "ab" * 20 + "@" + bad
                transport.inventory_peers(p)
        p = policy()
        p["peers"][1] = copy.copy(p["peers"][0])
        with self.assertRaises(ValueError):
            transport.inventory_peers(p)

    def test_installed_node_rejects_discovery_or_inconsistent_bindings(self):
        config = {
            "p2p": {
                "persistent_peers": ",".join(
                    p["comet_peer"] for p in policy()["peers"]
                ),
                "pex": False,
                "seed_mode": False,
                "seeds": "",
                "external_address": "",
                "libp2p": {"enabled": False},
            },
            "rpc": {"laddr": "tcp://127.0.0.1:26657"},
        }
        transport.check_comet(config, policy())
        for field, value in [
            ("pex", True),
            ("seeds", "foreign@host:26656"),
            ("seed_mode", True),
            ("persistent_peers", ""),
            ("libp2p", {"enabled": True}),
            ("external_address", "public.example:26656"),
        ]:
            bad = copy.deepcopy(config)
            bad["p2p"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                transport.check_comet(bad, policy())

    def test_kernel_fallbacks_must_be_dormant_for_both_ip_families(self):
        links = [
            {"ifname": "lo", "link_type": "loopback", "flags": ["UP"]},
            {"ifname": "wg0", "linkinfo": {"info_kind": "wireguard"}, "flags": ["UP"]},
            {
                "ifname": "ip6tnl0",
                "linkinfo": {"info_kind": "ip6tnl"},
                "flags": [],
                "operstate": "DOWN",
            },
        ]
        addresses = [{"ifname": "ip6tnl0", "addr_info": []}]
        routes = [{"dev": "wg0", "dst": "fd42::1"}]
        transport.check_links("wg0", links, addresses, routes)
        for changed_links, changed_addresses, changed_routes in [
            ([*links[:2], {**links[2], "flags": ["UP"]}], addresses, routes),
            ([*links[:2], {**links[2], "ifname": "arbitrary0"}], addresses, routes),
            (
                [*links[:2], {**links[2], "linkinfo": {"info_kind": "dummy"}}],
                addresses,
                routes,
            ),
            (
                links,
                [{"ifname": "ip6tnl0", "addr_info": [{"local": "fd42::8"}]}],
                routes,
            ),
            (links, addresses, [{"dev": "ip6tnl0", "dst": "fd42::8"}]),
            (links, addresses, [{"dev": "wg0", "dst": "::/0"}]),
            (links, addresses, [{"dev": "wg0", "dst": "default"}]),
            (links, addresses, [{**routes[0], "nexthops": [{"dev": "wg0"}]}]),
        ]:
            with (
                self.subTest(
                    interfaces=changed_links,
                    addresses=changed_addresses,
                    routes=changed_routes,
                ),
                self.assertRaises(ValueError),
            ):
                transport.check_links(
                    "wg0", changed_links, changed_addresses, changed_routes
                )

    def test_comet_has_no_remote_signer_alternate_rpc_or_statesync(self):
        base = {
            "p2p": {
                "persistent_peers": ",".join(
                    p["comet_peer"] for p in policy()["peers"]
                ),
                "pex": False,
                "seed_mode": False,
                "seeds": "",
            },
            "rpc": {"laddr": "tcp://127.0.0.1:26657"},
        }
        for field, value in (
            ("priv_validator_laddr", "tcp://0.0.0.0:1234"),
            ("statesync", {"enable": True}),
            ("rpc", {**base["rpc"], "grpc_laddr": "tcp://0.0.0.0:9090"}),
            ("rpc", {**base["rpc"], "unsafe": True}),
            ("rpc", {**base["rpc"], "pprof_laddr": "0.0.0.0:6060"}),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                transport.check_comet({**base, field: value}, policy())

    def test_restore_requires_an_enrolled_publisher_endpoint(self):
        transport.check_snapshot_url(policy(), "https://[fd10::3]:8443/manifest")
        transport.check_snapshot_url(policy(), "http://10.9.0.2/manifest")
        for bad in (
            "file:///tmp/manifest",
            "http://localhost/manifest",
            "https://10.9.0.6/manifest",
            "https://10.9.0.2@example.org/manifest",
            "http://127.0.0.1/manifest",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                transport.check_snapshot_url(policy(), bad)

    def test_installed_container_rejects_port_publication_and_extra_privileges(self):
        anchor = "a" * 64
        config = {
            "NetworkMode": "container:" + anchor,
            "PortBindings": {},
            "PublishAllPorts": False,
            "CapDrop": ["CAP_NET_ADMIN", "CAP_SYS_ADMIN", "CAP_NET_RAW"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"],
            "RestartPolicy": {"Name": "no"},
        }
        node = {
            "Id": "b" * 64,
            "State": {"Running": False},
            "HostConfig": config,
            "Config": {"Env": ["XIAN_PRIVATE_VALIDATOR_RPC=1"]},
        }
        with (
            mock.patch.object(transport, "command", return_value=node["Id"]),
            mock.patch.object(transport, "container", return_value=node),
        ):
            transport.check_service(anchor, "test-project")
            with self.assertRaises(ValueError):
                transport.check_service(anchor, "test-project", require_running=True)
            with (
                mock.patch.dict(
                    node,
                    Mounts=[{"Type": "bind", "Destination": "/var/run/docker.sock"}],
                ),
                self.assertRaises(ValueError),
            ):
                transport.check_service(anchor, "test-project")
            for override in (
                {"NetworkMode": "bridge"},
                {"CapAdd": ["NET_ADMIN"]},
                {"CapDrop": ["SYS_ADMIN"]},
                {"PortBindings": {"26657/tcp": [{"HostPort": "26657"}]}},
                {"PublishAllPorts": True},
                {"Privileged": True},
                {"PidMode": "host"},
                {"IpcMode": "host"},
                {"Devices": [{"PathOnHost": "/dev/example"}]},
                {"RestartPolicy": {"Name": "always"}},
                {"SecurityOpt": []},
            ):
                with (
                    self.subTest(override=override),
                    mock.patch.dict(node, HostConfig={**config, **override}),
                    self.assertRaises(ValueError),
                ):
                    transport.check_service(anchor, "test-project")
            with (
                mock.patch.dict(
                    node,
                    Mounts=[{"Type": "bind", "Destination": "/var/run/docker.sock"}],
                ),
                self.assertRaises(ValueError),
            ):
                transport.check_service(anchor, "test-project")
            with (
                mock.patch.dict(node, Config={"Env": []}),
                self.assertRaises(ValueError),
            ):
                transport.check_service(anchor, "test-project")
