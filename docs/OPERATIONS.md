# Operations

This file records the concrete operator runbooks for `xian-deploy`.

For the validated remote reference-app paths, see [SOLUTION_PACKS.md](SOLUTION_PACKS.md).

## Remote Health

Use the remote health playbook when you want the deployment-side equivalent of
`xian node health` and `xian doctor`:

```bash
ansible-playbook playbooks/health.yml
```

What it checks:

- expected running containers for the selected topology
- RPC reachability and current sync status
- Xian metrics
- optional dashboard / Prometheus / Grafana reachability
- BDS queue, spool, lag, and database state when BDS is enabled
- rendered state-sync readiness from the remote `config.toml`
- deploy-root and BDS-spool disk pressure

Use `playbooks/smoke.yml` for a lighter post-deploy sanity check. Use
`playbooks/health.yml` when you need a more complete remote diagnosis.

## Recovery Paths

There are three distinct recovery/bootstrap paths:

### 1. Prepared Node-Home Archive

Use this when you already have a full prepared `.cometbft` home.

```bash
ansible-playbook playbooks/push-home.yml
ansible-playbook playbooks/deploy.yml
```

This is the closest remote equivalent to a local `xian-cli` node-home restore.

### 2. Application State Snapshot Import

Use this when you have an exported `xian-state-snapshot` archive and want to
restore the application state into an existing remote home.

```bash
ansible-playbook playbooks/restore-state-snapshot.yml
```

Required variable:

- `xian_state_snapshot_archive`

This is not the same as a full prepared node-home archive.

### 3. Protocol State Sync

Use this when you want the remote node to bootstrap from trusted peers that
serve Xian application snapshots through CometBFT state sync.

```bash
ansible-playbook playbooks/bootstrap-state-sync.yml
```

Required variables:

- `xian_statesync_enable=true`
- at least two `xian_statesync_rpc_servers`
- `xian_statesync_trust_height`
- `xian_statesync_trust_hash`
- `xian_statesync_trust_period`

This path reuses the normal remote deploy role, but it validates the state-sync
inputs first and prints a focused summary afterward.
