# xian_profile

This role loads one canonical node profile JSON file and derives the runtime
facts consumed by the remote deploy playbooks.

Required inventory variable:

- `xian_node_profile`: path to a node profile on the Ansible control machine

The profile is the source of truth for node runtime intent: services, block
policy, pruning, logging, metrics, state sync, P2P peers, snapshots, and node
images. Inventory still owns deployment bindings such as remote paths, host
port publishing, topology, and secrets.

By default, remote runtime paths are derived from `xian_deploy_root`:
`xian_runtime_dir`, `xian_cometbft_home`, `xian_bds_data_dir`,
`xian_bds_spool_dir`, and `xian_monitoring_dir`. Private inventories should
set only `xian_deploy_root` unless a host needs a non-standard path layout.

Remote deployment requires `node_image_mode=registry` with both node image
references present in the profile.
