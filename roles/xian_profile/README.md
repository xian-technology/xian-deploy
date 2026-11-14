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
without a fixed `genesis_time` is rejected.

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
