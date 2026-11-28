"""Opt-in kernel test: uvx --from ansible-core python tests/check_private_wireguard.py --image IMAGE.

IMAGE needs Linux iproute2, wg, python (3.11+) and sleep.

Creates and removes two isolated underlays and WireGuard peers. No host network,
host PID namespace, Docker socket mounts, published ports, or persistent keys.
"""

import argparse
import base64
import json
import secrets
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "roles/xian_runtime/files")
)
from ansible_harness import REPO_ROOT, canonical_profile, load_yaml, run_play
from private_validator_transport import check_anchor, check_service, check_snapshot_url

# The status endpoint is a fixture. WireGuard, routing, Docker namespace
# attachment and the private RPC and restore playbook commands run for real.
RESPONSE_SERVER = dedent("""
    import socketserver, sys
    class Response(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096)
            payload = sys.argv[3].encode()
            self.request.sendall(
                b"HTTP/1.0 200 OK\\r\\nContent-Length: " + str(len(payload)).encode()
                + b"\\r\\n\\r\\n" + payload
            )
    socketserver.TCPServer.allow_reuse_address = True
    socketserver.TCPServer((sys.argv[1], int(sys.argv[2])), Response).serve_forever()
""")


def docker(*args, data=None):
    proc = subprocess.run(
        ["docker", *args], check=False, input=data, capture_output=True, timeout=30
    )
    if proc.returncode:
        # Stdin can contain a secret. Neither input nor container streams are logged.
        raise RuntimeError(
            f"disposable Docker gate failed ({args[0]}, exit {proc.returncode})"
        )
    return proc.stdout.decode().strip()


def check_comet_finality(anchors, addresses, image):
    """Two freshly generated equal-power ML-DSA validators must both sign."""
    peers, voters, nodes = [], [], []
    with ExitStack() as cleanup:
        for anchor in anchors:
            node = docker(
                "run",
                "-d",
                "--network",
                "container:" + anchor,
                "--cap-drop",
                "NET_ADMIN",
                "--cap-drop",
                "SYS_ADMIN",
                "--cap-drop",
                "NET_RAW",
                "--security-opt",
                "no-new-privileges:true",
                "--tmpfs",
                "/gate",
                "--entrypoint",
                "sleep",
                image,
                "300",
            )
            cleanup.callback(docker, "rm", "-f", node)
            nodes.append(node)
            docker("exec", node, "cometbft", "init", "--home", "/gate")
            peers.append(
                docker("exec", node, "cometbft", "show-node-id", "--home", "/gate")
            )
            key_json = subprocess.run(
                ["xian-validator-key"],
                input=secrets.token_bytes(32),
                capture_output=True,
                check=True,
            ).stdout
            key = json.loads(key_json)
            voters.append(
                {
                    "address": key["address"],
                    "pub_key": key["pub_key"],
                    "power": "1",
                    "name": "",
                }
            )
            docker(
                "exec",
                "-i",
                node,
                "sh",
                "-c",
                "cat >/gate/config/priv_validator_key.json",
                data=key_json,
            )
        genesis = json.loads(
            docker("exec", nodes[0], "cat", "/gate/config/genesis.json")
        )
        genesis["chain_id"] = "wg-disposable"
        genesis["validators"] = voters
        genesis["consensus_params"]["validator"]["pub_key_types"] = ["ml_dsa_65"]
        for i, node in enumerate(nodes):
            other = 1 - i
            docker(
                "exec",
                "-i",
                node,
                "sh",
                "-c",
                "cat >/gate/config/genesis.json",
                data=json.dumps(genesis).encode(),
            )
            docker(
                "exec",
                "-d",
                node,
                "cometbft",
                "node",
                "--home",
                "/gate",
                "--proxy_app",
                "kvstore",
                "--p2p.pex=false",
                "--p2p.persistent_peers",
                peers[other] + "@" + addresses[other] + ":26656",
                "--p2p.laddr",
                "tcp://" + addresses[i] + ":26656",
                "--rpc.laddr",
                "tcp://127.0.0.1:26657",
            )
        read_commit = dedent("""
            import base64, json, time
            from urllib.request import urlopen
            for attempt in range(65):
                try:
                    with urlopen('http://127.0.0.1:26657/commit?height=1',timeout=1) as response:
                        signed = json.load(response)['result']['signed_header']['commit']
                    signatures = signed['signatures']
                    assert len(signatures) == 2 and all(
                        s['block_id_flag'] == 2 and len(base64.b64decode(s['signature'])) == 3309 for s in signatures
                    )
                    print(signed['block_id']['hash'])
                    break
                except (OSError, KeyError):
                    time.sleep(.3)
            else:
                raise RuntimeError('missing two-validator commit')
        """)
        hashes = [docker("exec", node, "python", "-Ic", read_commit) for node in nodes]
        if not hashes[0] or hashes[0] != hashes[1]:
            raise AssertionError("private validators disagree on the committed block")
        print(
            "Both private CometBFT peers finalized the same block with two ML-DSA-65 precommits"
        )


def run(image, comet_image=None):
    run_id = "xian-wg-" + uuid4().hex[:12]
    underlay_net = run_id + "-underlay"
    local = ["10.244.201.1", "10.244.201.2"]
    anchors, underlying, public, remote = [], [], [], []
    with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
        docker("network", "create", "--internal", underlay_net)
        cleanup.callback(docker, "network", "rm", underlay_net)

        def start(name, network, *extra):
            cid = docker(
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                *extra,
                image,
                "sleep",
                "900",
            )
            cleanup.callback(docker, "rm", "-f", cid)
            return cid

        for index in range(2):
            under = start(f"{run_id}-under-{index}", underlay_net)
            anchor = start(f"{run_id}-anchor-{index}", "none", "--cap-add", "NET_ADMIN")
            underlying.append(under)
            anchors.append(anchor)
            remote.append(
                json.loads(docker("inspect", under))[0]["NetworkSettings"]["Networks"][
                    underlay_net
                ]["IPAddress"]
            )
            # Create the UDP socket in this disposable underlay, move only the
            # WG link to PID 1 of the anchor's *private* PID namespace.
            docker(
                "run",
                "--rm",
                "--network",
                "container:" + under,
                "--pid",
                "container:" + anchor,
                "--cap-add",
                "NET_ADMIN",
                "--cap-add",
                "SYS_ADMIN",
                image,
                "sh",
                "-ec",
                "ip link add wg0 type wireguard; ip link set wg0 netns 1",
            )
            private = docker("exec", anchor, "wg", "genkey")
            docker(
                "exec",
                "-i",
                anchor,
                "wg",
                "set",
                "wg0",
                "private-key",
                "/dev/stdin",
                "listen-port",
                "51820",
                data=private.encode() + b"\n",
            )
            public.append(docker("exec", anchor, "wg", "show", "wg0", "public-key"))
            docker(
                "exec", anchor, "ip", "addr", "add", local[index] + "/32", "dev", "wg0"
            )
            docker("exec", anchor, "ip", "link", "set", "wg0", "up")
        psk = base64.b64encode(secrets.token_bytes(32)) + b"\n"
        for i, anchor in enumerate(anchors):
            other = 1 - i
            docker(
                "exec",
                "-i",
                anchor,
                "wg",
                "set",
                "wg0",
                "peer",
                public[other],
                "preshared-key",
                "/dev/stdin",
                "allowed-ips",
                local[other] + "/32",
                "endpoint",
                remote[other] + ":51820",
                data=psk,
            )
            docker(
                "exec", anchor, "ip", "route", "add", local[other] + "/32", "dev", "wg0"
            )

        policy = {
            "anchor": run_id + "-anchor-0",
            "interface": "wg0",
            "peers": [
                {
                    "wireguard_public_key": public[1],
                    "comet_peer": "11" * 20 + "@" + local[1] + ":26656",
                }
            ],
        }
        assert check_anchor(policy) == anchors[0]
        if comet_image:
            check_comet_finality(anchors, local, comet_image)
        # TCP data crosses an authenticated tunnel with no other possible path.
        docker(
            "exec",
            "-d",
            anchors[1],
            "python3",
            "-c",
            RESPONSE_SERVER,
            local[1],
            "8443",
            "signed manifest fixture",
        )
        docker(
            "exec",
            anchors[0],
            "python3",
            "-c",
            "import http.client,time\nfor i in range(30):\n try:\n  c=http.client.HTTPConnection('10.244.201.2',8443,timeout=3);c.request('GET','/');assert c.getresponse().status==200;break\n except OSError:time.sleep(.3)\nelse:raise RuntimeError('tunnel failed')",
        )
        assert (
            int(
                docker(
                    "exec", anchors[0], "wg", "show", "wg0", "latest-handshakes"
                ).split()[1]
            )
            > 0
        )
        compose = Path(tmp) / "compose.json"
        compose.write_text(
            json.dumps(
                {
                    "services": {
                        "abci": {
                            "image": image,
                            "network_mode": "container:" + anchors[0],
                            "environment": {"XIAN_PRIVATE_VALIDATOR_RPC": "1"},
                            "cap_drop": ["NET_RAW", "NET_ADMIN", "SYS_ADMIN"],
                            "security_opt": ["no-new-privileges:true"],
                            "command": ["sleep", "900"],
                        }
                    }
                }
            )
        )
        docker("compose", "-p", run_id, "-f", str(compose), "up", "-d")
        cleanup.callback(docker, "compose", "-p", run_id, "-f", str(compose), "down")
        check_service(anchors[0], run_id)

        # Invoke the role's real health gate against a namespace-only RPC.
        status = {
            "result": {"sync_info": {"catching_up": False, "latest_block_height": "7"}}
        }
        docker(
            "exec",
            "-d",
            anchors[0],
            "python3",
            "-c",
            RESPONSE_SERVER,
            "127.0.0.1",
            "26657",
            json.dumps(status),
        )
        profile = canonical_profile(
            p2p={"seeds": [], "persistent_peers": [policy["peers"][0]["comet_peer"]]},
            advanced={"cometbft": {"prometheus": False}, "metrics": {"enabled": False}},
        )
        variables = {
            "xian_private_validator_transport": policy,
            "xian_runtime_dir": tmp,
            "xian_project_name": run_id,
            "xian_upgrade_health_timeout_seconds": 5,
            "xian_upgrade_health_poll_seconds": 1,
        }
        (Path(tmp) / "docker-compose.yml").write_bytes(compose.read_bytes())
        result = run_play(
            Path(tmp),
            profile=profile,
            variables=variables,
            tasks=[
                {
                    "ansible.builtin.include_role": {
                        "name": "xian_runtime",
                        "tasks_from": "wait_for_rpc_sync",
                    }
                },
                {
                    "ansible.builtin.assert": {
                        "that": "xian_private_rpc_status.json.result.sync_info.latest_block_height == '7'"
                    }
                },
            ],
        )
        if result.returncode:
            raise AssertionError(result.stdout)
        # Exercise the deployed restore task's Docker invocation with a fixture
        # downloader so the signed-snapshot tests own the archive validation.
        snapshot_url = "http://" + local[1] + ":8443/manifest"
        check_snapshot_url(policy, snapshot_url)
        restore_script = Path(tmp) / "fetch.py"
        restore_script.write_text(
            "from urllib.request import urlopen\n"
            + "assert urlopen("
            + repr(snapshot_url)
            + ", timeout=5).read() == b'signed manifest fixture'\n"
        )
        restore_task = next(
            t
            for t in load_yaml(REPO_ROOT / "playbooks/restore-network-snapshot.yml")[0][
                "tasks"
            ]
            if t["name"] == "Restore network snapshot into node home"
        )
        result = run_play(
            Path(tmp),
            profile={**profile, "snapshot_url": snapshot_url},
            variables={
                **variables,
                "xian_runtime_action": "restore",
                "xian_restore_image": image,
                "xian_cometbft_home": tmp,
                "xian_network_snapshot_script_path": str(restore_script),
            },
            tasks=[
                {
                    "ansible.builtin.include_role": {
                        "name": "xian_runtime",
                        "tasks_from": "private_transport",
                    }
                },
                restore_task,
            ],
        )
        if result.returncode:
            raise AssertionError(result.stdout)

        def rejected(check):
            try:
                check()
            except ValueError:
                return
            raise AssertionError("accepted unsafe private topology")

        rejected(lambda: check_service(anchors[1], run_id))
        docker("exec", anchors[0], "ip", "link", "add", "stray0", "type", "dummy")
        rejected(lambda: check_anchor(policy))
        docker("exec", anchors[0], "ip", "link", "del", "stray0")
        docker(
            "exec",
            anchors[0],
            "wg",
            "set",
            "wg0",
            "peer",
            public[1],
            "allowed-ips",
            "0.0.0.0/0",
        )
        rejected(lambda: check_anchor(policy))
        docker(
            "exec",
            anchors[0],
            "wg",
            "set",
            "wg0",
            "peer",
            public[1],
            "allowed-ips",
            local[1] + "/32",
            "preshared-key",
            "/dev/null",
        )
        rejected(lambda: check_anchor(policy))
    print(
        "WireGuard handshake, TCP, immutable Docker attachment and negative topology checks passed"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--comet-image",
        help="pinned Xian CometBFT image with python; requires xian-validator-key on host PATH",
    )
    args = parser.parse_args()
    run(args.image, args.comet_image)
