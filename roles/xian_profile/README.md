# xian_profile

This role loads one canonical node profile JSON file and derives the runtime
facts consumed by the remote deploy playbooks.

Required inventory variable:

- `xian_node_profile`: path to a node profile on the Ansible control machine

The profile is the source of truth for node runtime intent: services, block
policy, pruning, logging, metrics, state sync, P2P peers, snapshots, and node
images. Inventory still owns deployment bindings such as remote paths, host
port publishing, topology, and secrets.

Optional `xian_network_manifest` points at the network manifest used by
`xian node init`. It is required when deploy builds a bundle genesis and then
supplies `chain_id`, `genesis_time`, `runtime_features`, and `fee_policy`, using the same
profile-over-manifest genesis precedence as `xian node init`. A bundle genesis
without a fixed `genesis_time` is rejected. A manifest `genesis_sha256` is
passed to configure, which refuses a home genesis that does not match it.

For enabled protocol state sync, the role consumes `node_release_manifest`
from the profile, falling back to the network manifest only when the profile
has no override. It requires integer release schema 1 and a history-aware
`build`: CometBFT `0.40.0`, a 40-character lowercase `cometbft_source_commit`,
the matching official commit-specific `cometbft_source_url`, a lowercase
64-character `cometbft_source_sha256`, a repository-relative
`docker/cometbft-patches/*.patch` path, a lowercase 64-character
`cometbft_patch_sha256`, and string `cometbft_history_revision: "1"`.
The validated intended build is available as `xian_statesync_history_build`.
These values are configuration diagnostics, not attestation of the deployed
image; the application's private capability and historical bootstrap guards
enforce safety. Ordinary replay does not require history-build metadata.

The transaction fee policy is genesis state. Node profiles that set
`tx_fee_mode`, `max_tx_chi`, or `max_block_chi` are rejected; deploy
passes the manifest `fee_policy` only when it builds a bundle genesis and never
writes fee settings into `xian.toml`.

CometBFT RPC binds to `127.0.0.1` unless `xian_public_rpc_enabled` is true.

The profile's `advanced.metrics.host` and `advanced.metrics.port` choose where
the node's app metrics are published on the host (`xian_app_metrics_bind_host`,
`xian_app_metrics_port`; default `127.0.0.1:9108`), the same meaning as in
`xian-cli` and `xian-stack`. Inside the container the node always listens on
`0.0.0.0:9108`, which is also the in-network Prometheus target.

BDS deployments must provide `xian_bds_password` from a private inventory,
vault, or secret manager; it is the only source of the BDS password (see
[docs/SECRETS.md](../../docs/SECRETS.md)). Empty values and weak example
passwords are rejected before runtime files are rendered. Profiles carry no
BDS password, and unknown profile keys (for example `services.bds.password`)
fail by name.

By default, remote runtime paths are derived from `xian_deploy_root`:
`xian_runtime_dir`, `xian_cometbft_home`, `xian_bds_data_dir`,
`xian_bds_spool_dir`, and `xian_monitoring_dir`. Private inventories should
set only `xian_deploy_root` unless a host needs a non-standard path layout.

Remote deployment requires `node_image_mode=registry` with both node image
references present in the profile.
