# Operations

This file records the concrete operator runbooks for `xian-deploy`.

For example inventory shapes, see [EXAMPLES.md](EXAMPLES.md).
For secret handling, see [SECRETS.md](SECRETS.md).

The remote configuration container overrides the node image's entrypoint with
Python. It only writes configuration; it must not start the integrated image's
supervisor or validator services. The Compose runtime starts after configuration
succeeds.

## Local Validation

Run both checks before opening a deploy change:

```bash
make lint
make validate
```

`make lint` runs the `ansible-lint` minimum profile over playbooks, roles, and
inventories. `make validate` verifies the example inventory and playbook syntax
and runs the role checks in `tests/` with ansible-core on localhost: rendered
configure arguments, genesis and RPC exposure validation, the upgrade health
gate against a local fake RPC, and the network snapshot restore script.

`tests/test_genesis_parity.py` additionally proves that deploy and
`xian node init` build byte-identical bundle genesis. It is opt-in because it
needs xian-abci; it starts no node:

```bash
cd tests && XIAN_DEPLOY_PARITY_PYTHON=../../xian-cli/.venv/bin/python \
  XIAN_DEPLOY_PARITY_CONFIGS=../../xian-configs \
  uvx --from ansible-core python -m unittest test_genesis_parity
```

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
Docker manages iptables for published container ports and bypasses UFW rules:
a port published on `0.0.0.0` is reachable even if UFW does not allow it. The
bind host is therefore the effective exposure control. CometBFT RPC binds to
`127.0.0.1` by default; publishing it on any other address requires
`xian_public_rpc_enabled: true`, and the profile role fails otherwise. Verify
the effective exposure from outside the host after enabling UFW.

## Configuration Changes and Upgrades

`deploy.yml` rewrites the node configuration and runs `docker compose up -d`.
Compose recreates containers only when the image or Compose definition
changes, so a profile-only change (peers, state sync, logging, block policy)
reaches the node only after `playbooks/restart.yml`.

Deploy-time configuration never restores a snapshot, even when the node profile
carries `snapshot_url`. Use `playbooks/restore-network-snapshot.yml` for that.

`playbooks/upgrade.yml` upgrades one host at a time. After each host it waits
until CometBFT RPC answers with `catching_up: false` and fails the play,
stopping the rollout, when that does not happen within
`xian_upgrade_health_timeout_seconds` (default 600, polled every
`xian_upgrade_health_poll_seconds`). Override `xian_upgrade_rpc_status_url` when
RPC is not reachable on `127.0.0.1:{{ xian_rpc_port }}` from the host.

When deploy builds a bundle genesis (the node profile genesis is a bundle, or
the profile has none and the network manifest's genesis is a bundle), set
`xian_network_manifest` to the manifest used by `xian node init`. Deploy takes
`chain_id`, `genesis_time`, `runtime_features` and `fee_policy` from it, with the same
profile-over-manifest precedence as `xian node init`, and rejects a bundle
genesis without a fixed `genesis_time`. A manifest `source` genesis is not
copied; the pushed node home already contains it.

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

## Third-Party Service Images

Remote shared-network deployments require digest-pinned third-party service
images for each enabled service:

- `xian_postgres_image` when BDS/Postgres is enabled
- `xian_prometheus_image` and `xian_grafana_image` when monitoring is enabled

Use image references such as `postgres:17.10@sha256:<digest>` or
`prom/prometheus:v3.12.0@sha256:<digest>`. Local-development and example
inventories may keep tag-only defaults. Private inventories can require the
same strict behavior outside shared-network profiles by setting
`xian_require_digest_pinned_third_party_images=true`.

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

Prometheus and Grafana bind to loopback by default. If a private inventory binds
either service to a non-loopback address, set both
`xian_public_monitoring_enabled=true` and
`xian_monitoring_public_auth_confirmed=true` after placing the published ports
behind authenticated TLS reverse-proxy access or equivalent host/network
controls. Prometheus lifecycle/admin endpoints are not enabled by the deploy
compose template.

Bind hosts may be IPv4 or IPv6 literals. Prefer unbracketed IPv6 values such as
`::1` or `2001:db8::10` in inventory; the Compose templates render long-form
port publications with `host_ip`, so IPv6 colons are not parsed as port
separators.

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

### 3. Network Snapshot From the Node Profile

Use this when the node profile carries `snapshot_url` and trusted
`snapshot_signing_keys`:

```bash
ansible-playbook playbooks/restore-network-snapshot.yml
```

The playbook validates the profile inputs, stops the runtime, restores the
signed snapshot inside the node image, and starts the runtime again, one host
at a time. The expected chain id is `xian_snapshot_expected_chain_id`, or the
network manifest chain id when that is empty.

### 4. Protocol State Sync

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

## Log Retention

Rendered Compose services use Docker's `local` logging driver in blocking mode.
Inventory bindings `xian_docker_log_max_file_mb` (default 50) and
`xian_docker_log_max_files` (default 5) must be positive integers. All node, BDS,
dashboard and monitoring containers receive the policy. Recreate containers
through deployment to adopt changed logging settings. This limits retained
stdout/stderr by size and file count; Docker does not provide a seven-day age
limit with this driver. Never truncate Docker-managed log files manually.

The node profile independently controls application-file retention:
`app_log_retention_days` defaults to 7, `app_log_max_file_mb` to 50 and
`app_log_max_total_mb` to 250. The deployment wrapper forwards these settings to
`xian-configure-node`. These application files can expire earlier under size
pressure. This repo installs Docker Compose services, not native Xian systemd
units, and does not change global host journald retention.
