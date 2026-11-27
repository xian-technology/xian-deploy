# xian_runtime

This role owns the remote Xian node runtime deployment on a target host.

It is responsible for:

- materializing the node's Compose stack on the host
- applying the runtime facts derived from the canonical node profile
- starting and updating the released containers
- verifying and installing the pinned Stack monitoring bundle for enabled
  profiles, then applying target bindings and alert policy
- exposing the same node-local runtime settings that `xian-configure-node`
  writes, including logging, simulation, BDS, metrics, and state
  sync controls
- defaulting the BDS catch-up RPC URL to the node-local RPC when
  `xian_bds_rpc_url` is left empty
- rendering the BDS password and validator-key material into `0600` files
  under `xian_runtime_secret_dir` and keeping those values out of rendered
  Compose files, `xian.toml` and host command-line arguments; the BDS password
  file is mounted as the Compose secret `/run/secrets/xian_bds_password` for
  both Postgres and the node

It is not responsible for:

- loading or validating the node profile; run `xian_profile` first
- creating node-home archives
- generating validator keys
- defining runtime image contents

Before full-store restore, the `check_stopped_home` taskfile checks the host's
Docker daemon for writable mounts of the home, its parents, or its subpaths,
including containers from other Compose projects. A failed Docker query blocks
restore. The selected image supplies the shared standalone guard; the role
runs its exact bytes with isolated host Python 3 from a private temporary file
and always removes that file. The host needs Docker-daemon access for this check.

See the repo root [README.md](../../README.md) for the full deployment flow and
[docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for repo boundaries.
