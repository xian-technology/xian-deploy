# xian_runtime

This role owns the remote Xian node runtime deployment on a target host.

It is responsible for:

- materializing the chosen topology on the host
- applying the inventory-driven runtime configuration
- starting and updating the released containers

It is not responsible for:

- creating node-home archives
- generating validator keys
- defining runtime image contents

See the repo root [README.md](../../README.md) for the full deployment flow and
[docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for repo boundaries.
