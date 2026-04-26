# Operations

This file records the concrete operator runbooks for `xian-deploy`.

For the validated remote reference-app paths, see [SOLUTIONS.md](SOLUTIONS.md).

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

## Monitoring And Alerts

When monitoring is enabled, the runtime now stages:

- the `Xian VM Runtime` Grafana dashboard
- the `Xian BDS Recovery` Grafana dashboard
- an example Alertmanager routing file at
  `{{ xian_runtime_dir }}/monitoring/alertmanager/alertmanager.example.yml`

The Alertmanager file is an example only. It is not started or wired
automatically. Use it as the starting point when you want:

- VM mismatch alerts routed to a high-priority receiver
- BDS recovery alerts routed to an operator or storage/on-call receiver
- infrastructure-critical alerts separated from warning-grade operational noise

## VM Mismatch Alert Response

Treat `XianVmShadowMismatchDetected` as a rollout-integrity alert.

Recommended response:

1. Open the `Xian VM Runtime` dashboard and identify the affected instance,
   stage, contract, and mismatch fields.
2. Inspect the latest mismatch context from Prometheus
   (`xian_vm_shadow_last_mismatch_info`) and the local mismatch log at
   `storage/logs/xian-vm-shadow-mismatches.jsonl`.
3. If the node is in `xian_vm_v1` native-authority mode during rollout, move it
   back to Python authority or pause the rollout until the mismatch is
   explained.
4. Capture the tx hash, block height, contract/function, and mismatch fields
   before restarting or redeploying anything.

Do not ignore repeated mismatches. A mismatch means the two engines disagreed on
an authoritative state transition shape.

## BDS Recovery Alert Response

Use the `Xian BDS Recovery` dashboard when `XianBdsLagHigh`,
`XianBdsMetricsRefreshFailed`, `XianBdsRecoveryStalled`, or
`XianBdsAlertsPresent` fires.

Recommended response:

1. Confirm whether `indexed_height` is still moving toward `current_block_height`.
2. Check `catching_up`, `worker_running`, `catchup_running`, `refresh_success`,
   `db_ok`, spool pressure, and free disk space.
3. If BDS is progressing and lag is shrinking, keep the node in observation.
4. If catch-up is stalled or the database is degraded, export what you can and
   restore from a known-good BDS snapshot or rebuild the BDS service cleanly.
5. Re-run `ansible-playbook playbooks/health.yml` after recovery to confirm lag,
   spool, and alert state are back to normal.

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
