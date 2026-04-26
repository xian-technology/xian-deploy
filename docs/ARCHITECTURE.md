# Architecture

`xian-deploy` is the remote deployment layer for released Xian node images.

Main areas:

- `playbooks/`: operator-facing actions
- `roles/docker_host/`: Docker bootstrap on target hosts
- `roles/xian_node_home/`: prepared node-home upload and extraction
- `roles/xian_runtime/`: runtime rendering, remote node configuration, and Compose operations
- `presets/`: reusable remote deployment postures aligned with the Xian template classes
- `docs/OPERATIONS.md`: concrete remote runbooks for health and recovery
- `docs/SOLUTIONS.md`: remote starter-flow mapping for the validated reference apps

Dependency direction:

- consumes released images from `xian-stack`
- consumes CLI/config behavior from `xian-abci`
- is intended to complement `xian-cli`, not replace it
