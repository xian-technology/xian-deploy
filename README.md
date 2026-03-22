# xian-deploy

`xian-deploy` is the Linux-focused deployment layer for Xian nodes.

It is intentionally separate from:

- `xian-cli`, which prepares and joins node homes
- `xian-stack`, which defines the runtime architecture and release images

This repo does not clone source code onto remote machines and does not build Xian remotely. It deploys released container images and a prepared CometBFT home archive.

## Scope

The first supported deployment flow is:

1. prepare a node home archive locally
2. bootstrap a remote Linux host with Docker
3. upload the prepared node home
4. configure that home in place with `xian-configure-node`
5. run the released node image in either:
   - `integrated` topology
   - `fidelity` topology

Optional services:

- Xian dashboard
- BDS with PostgreSQL
- Prometheus + Grafana

This first cut intentionally does not deploy PostGraphile. The primary read surfaces remain raw ABCI queries and optional BDS-backed ABCI queries.

## Assumptions

- one Xian node stack per host
- Debian or Ubuntu host
- public GHCR images are used
- the node home archive contains the contents of `.cometbft` at the archive root

Example archive layout:

```text
config/
data/
xian/
```

Do not archive the parent `.cometbft` directory itself unless you also change the extraction target.

## Inventory Model

The example inventory lives in [inventories/example/hosts.yml](inventories/example/hosts.yml) and [inventories/example/group_vars/all/main.yml](inventories/example/group_vars/all/main.yml).

The most important variables are:

- `xian_release_tag`
- `xian_topology`
- `xian_node_home_archive`
- `xian_state_snapshot_archive`
- `xian_moniker`
- `xian_seed_node_address` or `xian_seed_node`
- `xian_copy_genesis`
- `xian_genesis_source`
- `xian_enable_dashboard`
- `xian_enable_bds`
- `xian_enable_monitoring`

## Workflow

Bootstrap the host:

```bash
ansible-playbook playbooks/bootstrap.yml
```

Upload the prepared node home:

```bash
ansible-playbook playbooks/push-home.yml
```

Deploy or update the runtime:

```bash
ansible-playbook playbooks/deploy.yml
```

Roll out an updated release across multiple hosts serially:

```bash
ansible-playbook playbooks/upgrade.yml
```

Inspect status:

```bash
ansible-playbook playbooks/status.yml
```

Run a basic smoke check against the deployed node:

```bash
ansible-playbook playbooks/smoke.yml
```

Restart services:

```bash
ansible-playbook playbooks/restart.yml
```

Stop the stack:

```bash
ansible-playbook playbooks/stop.yml
```

Restore an exported Xian state snapshot and redeploy:

```bash
ansible-playbook playbooks/restore-state-snapshot.yml
```

## Node Home Preparation

`xian-deploy` expects a prepared home archive. The intended split is:

- use `xian-cli` and `xian-abci` tooling locally to create or join a network
- archive the resulting `.cometbft` home contents
- deploy that archive with this repo

`xian-deploy` still runs `xian-configure-node` remotely so runtime settings like tracer mode, parallel execution, BDS, metrics, pruning, block policy, and state sync stay aligned with the deployment inventory.

If the uploaded home already contains validator key material, `xian-deploy` preserves it by default.

## Topologies

### Integrated

One released `xian-node` container per host. The container runs the integrated node image with `s6-overlay`.

### Fidelity

Two released `xian-node-split` containers per host:

- `abci-app`
- `cometbft`

This is closer to a split-process production layout.

## Monitoring

If `xian_enable_monitoring` is true, `xian-deploy` also runs:

- Prometheus
- Grafana

The node dashboard is separate and optional.

## Notes

- pin `xian_release_tag` to a real release instead of using `latest`
- keep real inventories and secrets private
- store validator keys and passwords outside the public example inventory
- when restoring state snapshots, set `xian_state_snapshot_archive` to the exported `xian-state-snapshot` tarball path
