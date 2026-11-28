"""Read-only verification of an operator-provisioned WireGuard namespace.

Only the verified immutable Docker container ID leaves the host check.
WireGuard key output must never be logged or interpolated into command lines.
"""

import base64
import ipaddress
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit


def require(condition, message):
    if not condition:
        raise ValueError(message)


def secret_bytes(value):
    try:
        raw = base64.b64decode(value, validate=True)
    except (TypeError, ValueError):
        raise ValueError("invalid WireGuard key") from None
    require(len(raw) == 32 and any(raw), "missing or invalid WireGuard key")
    require(base64.b64encode(raw).decode() == value, "noncanonical WireGuard key")
    return raw


def comet_endpoint(value):
    identity, sep, endpoint = value.partition("@")
    require(sep and re.fullmatch(r"[a-f0-9]{40}", identity), "invalid CometBFT peer ID")
    parsed = urlsplit("//" + endpoint)
    require(
        not (parsed.path or parsed.query or parsed.fragment or parsed.username),
        "invalid peer endpoint",
    )
    address = ipaddress.ip_address(parsed.hostname)
    require(
        not (
            address.is_loopback
            or address.is_multicast
            or address.is_unspecified
            or address.is_link_local
            or "%" in str(address)
        ),
        "invalid WireGuard peer address",
    )
    require(parsed.port is not None and parsed.port > 0, "missing CometBFT peer port")
    return identity, address


def inventory_peers(policy):
    require(
        isinstance(policy, dict) and set(policy) == {"anchor", "interface", "peers"},
        "private transport requires anchor, interface and peers",
    )
    require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", policy["anchor"]),
        "invalid anchor name",
    )
    require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", policy["interface"]),
        "invalid WireGuard interface",
    )
    peers = policy["peers"]
    require(isinstance(peers, list) and peers, "empty WireGuard peer inventory")
    routes, identities = {}, set()
    for peer in peers:
        require(
            isinstance(peer, dict)
            and set(peer) == {"wireguard_public_key", "comet_peer"},
            "invalid peer record",
        )
        public = peer["wireguard_public_key"]
        secret_bytes(public)
        identity, address = comet_endpoint(peer["comet_peer"])
        route = f"{address}/{address.max_prefixlen}"
        require(
            public not in routes
            and route not in routes.values()
            and identity not in identities,
            "duplicate WireGuard peer, route or CometBFT ID",
        )
        routes[public] = route
        identities.add(identity)
    return routes


def check_peers(policy, allowed, psks):
    expected = inventory_peers(policy)
    require(
        allowed == expected and set(psks) == set(expected),
        "WireGuard peers or allowed IPs disagree with inventory",
    )
    keys = {secret_bytes(psk) for psk in psks.values()}
    require(
        len(keys) == len(expected), "each WireGuard peer needs a distinct preshared key"
    )


def check_comet(config, policy):
    inventory_peers(policy)
    allowed = {p["comet_peer"] for p in policy["peers"]}
    p2p = config["p2p"]
    require(
        set(p2p["persistent_peers"].split(",")) == allowed,
        "CometBFT peer set disagrees with private inventory",
    )
    require(
        p2p.get("pex") is False
        and p2p.get("seed_mode") is False
        and p2p.get("seeds") == "",
        "private CometBFT configuration permits peer discovery",
    )
    require(
        not p2p.get("external_address") and not p2p.get("libp2p", {}).get("enabled"),
        "unexpected P2P transport",
    )
    require(
        not config.get("priv_validator_laddr")
        and not config.get("statesync", {}).get("enable"),
        "unsupported remote signer or state sync connection",
    )
    require(
        not config.get("instrumentation", {}).get("prometheus"),
        "unexpected Prometheus listener",
    )
    require(
        config.get("proxy_app", "unix:///tmp/abci.sock") == "unix:///tmp/abci.sock",
        "private ABCI connection must use the local UNIX socket",
    )
    rpc = config["rpc"]
    require(
        not (rpc.get("unsafe") or rpc.get("grpc_laddr") or rpc.get("pprof_laddr")),
        "unexpected RPC listener or unsafe dialing method",
    )
    require(
        config["rpc"]["laddr"] == "tcp://127.0.0.1:26657",
        "private RPC must bind the namespace loopback",
    )


def command(*argv):
    # Suppress stderr as well as stdout on failure. Secret data passes through
    # pipes only; even a broken tool cannot echo a key into an Ansible log.
    result = subprocess.run(argv, check=False, capture_output=True, timeout=15)
    require(result.returncode == 0, "Docker or namespace inspection failed")
    return result.stdout.decode()


def container(selector):
    (result,) = json.loads(
        command("docker", "inspect", "--type", "container", selector)
    )
    return result


# Linux can instantiate these immutable fallback tunnel devices in every netns.
# None can carry node traffic while down, unaddressed, unrouted and without NET_ADMIN.
FALLBACK_TUNNELS = {
    "tunl0": "ipip",
    "gre0": "gre",
    "gretap0": "gretap",
    "erspan0": "erspan",
    "ip_vti0": "vti",
    "ip6_vti0": "vti6",
    "sit0": "sit",
    "ip6tnl0": "ip6tnl",
    "ip6gre0": "ip6gre",
}


def check_links(iface, interfaces, address_list, routes):
    links = {item["ifname"]: item for item in interfaces}
    require(
        links.get("lo", {}).get("link_type") == "loopback"
        and links.get(iface, {}).get("linkinfo", {}).get("info_kind") == "wireguard",
        "loopback and an actual WireGuard device required",
    )
    active = {"lo", iface}
    require(
        all("UP" in links[name]["flags"] for name in active),
        "namespace links must be up",
    )
    for name in set(links) - active:
        link = links[name]
        require(
            name in FALLBACK_TUNNELS
            and link.get("linkinfo", {}).get("info_kind") == FALLBACK_TUNNELS[name]
            and "UP" not in link["flags"]
            and link.get("operstate") == "DOWN",
            "namespace contains an unapproved or enabled fallback interface",
        )
    require(
        all(
            not link.get("addr_info")
            for link in address_list
            if link["ifname"] not in active
        ),
        "fallback interface has a configured address",
    )
    for route in routes:
        require(
            route.get("dst") not in ("default", "0.0.0.0/0", "::/0"),
            "namespace has a default route",
        )
        require(
            route.get("dev") in active,
            "namespace route leaves the permitted interfaces",
        )
        require(not route.get("nexthops"), "multipath routes are unsupported")


def check_anchor(policy):
    inventory_peers(policy)
    anchor = container(policy["anchor"])
    handle = anchor["Id"]
    require(re.fullmatch("[0-9a-f]{64}", handle), "invalid immutable anchor ID")
    require(
        anchor["State"]["Running"] and anchor["HostConfig"]["NetworkMode"] == "none",
        "anchor must be running with Docker network mode none",
    )
    require(
        not anchor["HostConfig"].get("PortBindings")
        and not anchor["HostConfig"].get("PublishAllPorts"),
        "anchor must have no published ports",
    )

    def inspect(*args):
        return command("docker", "exec", handle, *args)

    iface = policy["interface"]
    routes = []
    for version in ("-4", "-6"):
        routes.extend(
            json.loads(inspect("ip", "-j", version, "route", "show", "table", "all"))
        )
    check_links(
        iface,
        json.loads(inspect("ip", "-j", "-d", "link", "show")),
        json.loads(inspect("ip", "-j", "addr", "show")),
        routes,
    )

    def peer_fields(field):
        return dict(
            line.split("\t", 1)
            for line in inspect("wg", "show", iface, field).splitlines()
        )

    secret_bytes(inspect("wg", "show", iface, "public-key").strip())
    check_peers(policy, peer_fields("allowed-ips"), peer_fields("preshared-keys"))
    for route in inventory_peers(policy).values():
        address = ipaddress.ip_interface(route).ip
        probe = json.loads(
            inspect("ip", "-j", f"-{address.version}", "route", "get", str(address))
        )
        require(
            probe and all(r.get("dev") == iface for r in probe),
            "unreachable WireGuard peer",
        )
    return handle


def check_project(project):
    services = command(
        "docker",
        "ps",
        "--all",
        "--filter",
        "label=com.docker.compose.project=" + project,
        "--format",
        '{{.Label "com.docker.compose.service"}}',
    ).splitlines()
    require(
        all(service == "abci" for service in services),
        "remove companion services before enrolling a private validator",
    )


def check_service(anchor_id, project, require_running=False):
    listing = command(
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        "label=com.docker.compose.project=" + project,
        "--filter",
        "label=com.docker.compose.service=abci",
    )
    require(
        len(listing.splitlines()) == 1, "deploy the private validator before restart"
    )
    node = container(listing.strip())
    require(
        "XIAN_PRIVATE_VALIDATOR_RPC=1" in node["Config"].get("Env", []),
        "installed supervisor must restrict RPC to loopback",
    )
    config = node["HostConfig"]
    require(
        config["NetworkMode"] == "container:" + anchor_id,
        "installed node does not share the verified anchor; redeploy",
    )
    require(
        not config.get("PortBindings") and not config.get("PublishAllPorts"),
        "installed node publishes ports",
    )
    require(
        not config.get("Privileged") and not config.get("CapAdd"),
        "unexpected node capabilities",
    )
    require(
        not config.get("PidMode")
        and config.get("IpcMode") in (None, "", "private")
        and not config.get("Devices"),
        "unexpected host namespace or device access",
    )
    require(
        all(
            mount.get("Type") == "bind"
            and mount.get("Destination") == "/root/.cometbft"
            for mount in node.get("Mounts", [])
        ),
        "unexpected private validator mount",
    )
    dropped = {cap.removeprefix("CAP_") for cap in (config.get("CapDrop") or [])}
    require(
        {"NET_ADMIN", "SYS_ADMIN", "NET_RAW"}.issubset(dropped),
        "node capability restrictions missing",
    )
    require(
        any(
            option in {"no-new-privileges:true", "no-new-privileges"}
            for option in (config.get("SecurityOpt") or [])
        ),
        "node can gain extra privileges",
    )
    require(
        config.get("RestartPolicy", {}).get("Name") in ("no", ""),
        "restart must verify the private namespace",
    )
    require(
        not require_running or node["State"]["Running"],
        "private validator service is stopped",
    )
    if node["State"]["Running"]:

        def namespace(handle):
            return command(
                "docker", "exec", handle, "readlink", "/proc/self/ns/net"
            ).strip()

        require(
            namespace(node["Id"]) == namespace(anchor_id),
            "node is attached to a stale network namespace; redeploy",
        )


def check_snapshot_url(policy, source):
    url = urlsplit(source)
    require(
        url.scheme in {"https", "http"}
        and url.username is None
        and url.password is None,
        "invalid private snapshot URL",
    )
    hosts = {route.split("/")[0] for route in inventory_peers(policy).values()}
    require(
        str(ipaddress.ip_address(url.hostname)) in hosts,
        "snapshot publisher must be a literal enrolled peer IP",
    )


def main(args):
    mode, public_inventory, *extra = args
    policy = json.loads(public_inventory)
    if mode == "comet":
        import tomllib

        # The supervisor passes its own --rpc.laddr to CometBFT. Older
        # images lack this helper and cannot be used for private validators.
        require(
            command("/usr/local/bin/xian-comet-rpc-address").strip()
            == "tcp://127.0.0.1:26657",
            "installed supervisor does not support private RPC",
        )
        with open(extra[0], "rb") as stream:
            check_comet(tomllib.load(stream), policy)
        return
    require(
        mode in ("anchor", "installed", "running", "snapshot"),
        "unknown verification mode",
    )
    check_project(extra[0])
    if mode == "snapshot":
        check_snapshot_url(policy, extra[1])
    handle = check_anchor(policy)
    if mode in ("installed", "running"):
        check_service(handle, extra[0], require_running=mode == "running")
    print(handle)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        sys.exit(
            "private validator transport verification failed; check namespace, bindings and peer inventory"
        )
