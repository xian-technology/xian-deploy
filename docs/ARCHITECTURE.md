# Architecture

`xian-deploy` is the remote deployment layer for released Xian node images.

Main areas:

- `playbooks/`: operator-facing actions
- `roles/docker_host/`: Docker bootstrap on target hosts
- `roles/xian_profile/`: canonical node-profile loading and deploy fact derivation
- `roles/xian_node_home/`: prepared node-home upload and extraction
- `roles/xian_runtime/`: runtime rendering, remote node configuration, and Compose operations
- `docs/OPERATIONS.md`: concrete remote runbooks for health and recovery
- `docs/EXAMPLES.md`: example inventory shapes for generated node profiles

Boundary:

- node profiles are the source of truth for runtime intent
- inventory owns host bindings: paths, ports, secrets, resource limits, and `xian_deploy_topology`
- deploy playbooks must not re-declare service posture that is already present in a node profile
- stack-local services such as IntentKit, DEX automation, and shielded relayer
  must be disabled until `xian-deploy` has explicit support for them

Dependency direction:

- consumes released images from `xian-stack`
- consumes CLI/config behavior from `xian-abci`
- is intended to complement `xian-cli`, not replace it
