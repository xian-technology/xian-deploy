# xian_profile

This role loads one canonical node profile JSON file and derives the runtime
facts consumed by the remote deploy playbooks.

Required inventory variable:

- `xian_node_profile`: path to a node profile on the Ansible control machine

The profile is the source of truth for node runtime intent: services, block
policy, pruning, logging, metrics, P2P peers, snapshots, and node
images. Inventory still owns deployment bindings such as remote paths, host
port publishing and secrets.

Set `xian_network_manifest` to the manifest used by `xian node init` for a
pinned network. The runtime role checks the prepared home against the manifest's
`chain_id` and, when present, compares `genesis_sha256` with the SHA-256 of the
installed `config/genesis.json` bytes.

Node profiles omit `advanced.statesync`. For compatibility, the role accepts
a legacy object with `enabled` absent or set to `false`, and ignores its
recognized trust settings. Stop and status remain available when the legacy
object is enabled or malformed. Bootstrap through ordinary replay or a verified
full-node-store archive using `restore-network-snapshot.yml`.
Upstream source commit/URL/SHA256 provenance remains in the release manifest;
custom patch/history metadata is not required.

The transaction fee policy belongs to the genesis prepared by `xian node init`.
Node profiles that set `tx_fee_mode`, `max_tx_chi`, or `max_block_chi` are rejected.

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
