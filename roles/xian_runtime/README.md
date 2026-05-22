# xian_runtime

This role owns the remote Xian node runtime deployment on a target host.

It is responsible for:

- materializing the chosen topology on the host
- applying the inventory-driven runtime configuration
- starting and updating the released containers
- exposing the same node-local runtime settings that `xian-configure-node`
  writes, including logging, simulation, pending nonce, BDS, metrics, state
  sync, and speculative parallel execution controls
- deriving the BDS catch-up RPC URL from the selected topology when
  `xian_bds_rpc_url` is left empty

It is not responsible for:

- creating node-home archives
- generating validator keys
- defining runtime image contents

See the repo root [README.md](../../README.md) for the full deployment flow and
[docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for repo boundaries.
