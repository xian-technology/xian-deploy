# Operations

This file records the concrete operator runbooks for `xian-deploy`.

For example inventory shapes, see [EXAMPLES.md](EXAMPLES.md).
For secret handling, see [SECRETS.md](SECRETS.md).

## Local Validation

Run both checks before opening a deploy change:

```bash
make lint
make validate
```

`make lint` runs the `ansible-lint` minimum profile over playbooks, roles, and
inventories. `make validate` verifies the example inventory and playbook syntax.

## Host Bootstrap Hardening

`playbooks/bootstrap.yml` runs `host_hardening` before `docker_host`.

The default hardening baseline writes `/etc/sysctl.d/90-xian-hardening.conf`
with conservative network and kernel settings. Access-affecting controls are
opt-in so a first bootstrap cannot silently lock an operator out:

- `xian_host_hardening_manage_ssh`: writes an sshd drop-in for passwordless,
  key-based access policy
- `xian_host_hardening_manage_firewall`: installs and enables UFW with explicit
  TCP allow rules
- `xian_host_hardening_manage_unattended_upgrades`: enables Debian/Ubuntu
  unattended security updates
- `xian_host_hardening_manage_fail2ban`: installs and starts fail2ban

Before enabling SSH or firewall management, confirm operator key access, the SSH
port, and the public Xian ports that should be reachable. By default, the UFW
allow list includes SSH and the configured P2P port; add RPC, dashboard,
Prometheus, or Grafana ports only when those services are intentionally public.
Docker also manages iptables for published container ports, so verify the
effective exposure from outside the host after enabling UFW.

## Remote Health

Use the remote health playbook when you want the deployment-side equivalent of
`xian node health` and `xian doctor`:

```bash
ansible-playbook playbooks/health.yml
```

What it checks:

- expected running containers for `xian_deploy_topology` and the loaded node
  profile
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

1. Open the `Xian VM Runtime` dashboard and identify the affected instance and
   runtime health fields.
2. Inspect node logs and the local `xian-perf.json` snapshot for the same block
   height.
3. Capture the block height, app hash, and affected node identity before
   restarting or redeploying anything.

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
- `xian_state_snapshot_sha256`
- `xian_state_snapshot_expected_chain_id`
- `xian_state_snapshot_expected_height`

Optional additional pin:

- `xian_state_snapshot_expected_app_hash`

The restore playbook validates the local archive checksum and snapshot metadata
before uploading it or stopping the remote runtime. For shared-network
operations, source the checksum and metadata from a signed operator snapshot
manifest or another release-approved publication path. This is not the same as
a full prepared node-home archive.

### 3. Protocol State Sync

Use this when you want the remote node to bootstrap from trusted peers that
serve Xian application snapshots through CometBFT state sync.

```bash
ansible-playbook playbooks/bootstrap-state-sync.yml
```

Required profile settings:

- `advanced.statesync.enabled=true`
- at least two `advanced.statesync.rpc_servers`
- `advanced.statesync.trust_height`
- `advanced.statesync.trust_hash`
- `advanced.statesync.trust_period`

This path reuses the normal remote deploy role, but it validates the state-sync
profile settings first and prints a focused summary afterward.
