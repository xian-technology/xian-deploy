"""The rolling-upgrade health gate against a local fake CometBFT RPC."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ansible_harness import (
    REPO_ROOT,
    PlaybookTestCase,
    load_yaml,
    requires_ansible,
    run_play,
)


def rpc_server(responses: list[dict | None]) -> ThreadingHTTPServer:
    """Serve ``responses`` in order (``None`` means HTTP 503), repeating the last."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = responses.pop(0) if len(responses) > 1 else responses[0]
            if payload is None:
                self.send_response(503)
                self.end_headers()
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def status(catching_up: bool) -> dict:
    return {"result": {"sync_info": {"catching_up": catching_up, "latest_block_height": "9"}}}


@requires_ansible
class UpgradeHealthGateTest(PlaybookTestCase):
    def gate(self, responses: list[dict | None], *, url: str | None = None):
        server = rpc_server(responses)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        return run_play(
            self.workdir,
            variables={
                "xian_upgrade_rpc_status_url": url or f"http://127.0.0.1:{port}/status",
                "xian_upgrade_health_timeout_seconds": 3,
                "xian_upgrade_health_poll_seconds": 1,
            },
            tasks=[
                {
                    "ansible.builtin.include_role": {
                        "name": "xian_runtime",
                        "tasks_from": "wait_for_rpc_sync",
                    }
                }
            ],
        )

    def test_gate_passes_once_the_node_has_caught_up(self) -> None:
        self.assertPlaySucceeded(self.gate([None, status(True), status(False)]))

    def test_gate_fails_while_the_node_keeps_catching_up(self) -> None:
        result = self.gate([status(True)])

        self.assertPlayFailed(result, "Wait for node RPC to answer and finish catching up")
        self.assertIn("FAILED - RETRYING", result.stdout)

    def test_gate_fails_when_rpc_never_answers(self) -> None:
        result = self.gate([None], url="http://127.0.0.1:9/status")

        self.assertPlayFailed(result, "Wait for node RPC to answer and finish catching up")


@requires_ansible
class UpgradePlaybookTest(unittest.TestCase):
    def test_upgrade_gates_each_host_and_stops_on_the_first_failure(self) -> None:
        play = load_yaml(REPO_ROOT / "playbooks/upgrade.yml")[0]

        self.assertEqual(play["serial"], 1)
        self.assertEqual(play["max_fail_percentage"], 0)
        self.assertEqual(
            [task["ansible.builtin.include_role"] for task in play["post_tasks"]],
            [{"name": "xian_runtime", "tasks_from": "wait_for_rpc_sync"}],
        )


if __name__ == "__main__":
    unittest.main()
