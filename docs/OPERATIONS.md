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

`tests/test_prepared_genesis_integration.py` runs the real configure command
against a CLI-prepared home and checks that genesis, keys and signing state
stay byte-identical. The test uses the sibling CLI environment and starts no node.

```bash
XIAN_DEPLOY_INTEGRATION_PYTHON=../xian-cli/.venv/bin/python \
  XIAN_DEPLOY_INTEGRATION_CONFIGS=../xian-configs \
  uvx --from ansible-core python -m unittest discover -s tests -p test_prepared_genesis_integration.py
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
changes, so a profile-only change (peers, logging, block policy)
reaches the node only after `playbooks/restart.yml`.

Deploy-time configuration never restores a snapshot, even when the node profile
carries `snapshot_url`. Use `playbooks/restore-network-snapshot.yml` for that.

`playbooks/upgrade.yml` upgrades one host at a time. After each host it waits
until CometBFT RPC answers with `catching_up: false` and fails the play,
stopping the rollout, when that does not happen within
`xian_upgrade_health_timeout_seconds` (default 600, polled every
`xian_upgrade_health_poll_seconds`). Override `xian_upgrade_rpc_status_url` when
RPC is not reachable on `127.0.0.1:{{ xian_rpc_port }}` from the host.

Deploy and rolling upgrades require the installed `config/genesis.json` from
the CLI-prepared node home. Set `xian_network_manifest` to the same manifest
used by `xian node init` to verify the chain ID and any `genesis_sha256` pin
against the exact installed file bytes. Genesis validation runs before
configuration. Snapshot restore also checks the installed genesis before it
stops the node.

## Remote Health

Use the remote health playbook when you want the deployment-side equivalent of
`xian node health` and `xian doctor`:

```bash
ansible-playbook playbooks/health.yml
```

What it checks:

- expected running containers for the loaded node
  profile
- RPC reachability and current sync status
- Xian metrics
- optional dashboard / Prometheus / Grafana reachability
- BDS queue, spool, lag, and database state when BDS is enabled
- validation of the installed CometBFT configuration
- deploy-root and BDS-spool disk pressure

Use `playbooks/smoke.yml` for a lighter post-deploy sanity check. Use
`playbooks/health.yml` when you need a more complete remote diagnosis.

## Third-Party Service Images

Remote shared-network deployments require digest-pinned third-party service
images for each enabled service:

- `xian_postgres_image` when BDS/Postgres is enabled
- `xian_prometheus_image`, `xian_grafana_image`, and `xian_node_exporter_image`
  when monitoring is enabled

PostgreSQL defaults to 18.7. Its persistent directory mounts at
`/var/lib/postgresql`, with cluster data under `18/docker`. A PostgreSQL 17
directory requires a logical dump/restore into a fresh directory before this
deployment can start; retain the original directory for rollback. Follow the
[database migration procedure](../../xian-docs-web/node/configuration.md#postgresql-version-and-storage)
before running an upgrade against an existing BDS database.

Use image references such as `postgres:18.7@sha256:<digest>` or
`prom/prometheus:v3.12.0@sha256:<digest>`. Local-development and example
inventories may keep tag-only defaults. Private inventories can require the
same strict behavior outside shared-network profiles by setting
`xian_require_digest_pinned_third_party_images=true`.

## Monitoring And Alerts

When the profile enables monitoring, choose a versioned `xian-stack` release
that publishes `xian-monitoring.tar` and `xian-monitoring.tar.sha256`. Verify
the archive and checksum against their accompanying `.sigstore.json` bundles
using the [Stack release verification procedure](https://github.com/xian-technology/xian-stack/blob/main/docs/RELEASES.md).
Pin the release asset URL and the 64-character hex checksum in inventory.

```yaml
xian_monitoring_bundle_source: "https://github.com/xian-technology/xian-stack/releases/download/<tag>/xian-monitoring.tar"
xian_monitoring_bundle_sha256: "<verified SHA-256 of xian-monitoring.tar>"
```

An absolute archive path on the Ansible controller also works. For an offline
or prerelease rehearsal, run `python3 scripts/package_monitoring.py
/absolute/output-directory` from a trusted `xian-stack` checkout and use its
archive and checksum. The playbooks verify the pin before installing the
assets on the host. The node image and monitoring bundle have independent
pins, so a node can keep its existing image when compatible monitoring assets
change. To update monitoring, replace both inventory inputs and run `deploy`
or `upgrade`.

The runtime stages the selected assets on the host.

- Prometheus with the alert rules for the profile, and node-exporter for host
  disk metrics (read-only host root, no published port, scraped as job
  `xian_node`)
- the `Xian VM Runtime` Grafana dashboard
- the `Xian BDS Recovery` Grafana dashboard
- an example Alertmanager routing file at
  `{{ xian_runtime_dir }}/monitoring/alertmanager/alertmanager.example.yml`

`shared_network` profiles get these alerts in addition to the target, node
info, app block-progress, and BDS alerts (development profiles get none):

| Alert | Fires when | Severity |
| --- | --- | --- |
| `XianBlockProductionStalled` | CometBFT's committed height has not moved for 5 minutes (only rendered for `idle_interval`/`periodic` block policies; an `on_demand` chain stops while idle) | critical |
| `XianNoPeers` | 0 connected peers for 2 minutes | critical |
| `XianPeersLow` | fewer than 2 peers for 10 minutes | warning |
| `XianValidatorNotSigning` | this node's validator last signed more than 10 blocks below the committed height for 2 minutes | critical |
| `XianValidatorMissedBlocks` | this node's validator missed 5 or more commits in 10 minutes | warning |
| `XianDiskSpaceCritical` / `XianDiskSpaceLow` | a real filesystem has less than 5% (5 min) / 15% (10 min) free | critical / warning |
| `XianDiskFillingUp` | under 25% free and empty within 24 hours at the 6-hour rate | warning |

CometBFT exports the two validator series only for the node's own key, so the
validator alerts stay silent on non-validators. After a validator leaves the
set on purpose, restart the node to drop its stale last-signed series.
The Stack tests cover alert evaluation with `promtool`. Deployment tests
exercise bundle verification and load the rules for each profile. Deploying a
profile with monitoring disabled stops the monitoring containers and keeps
their data mounts for re-enabling the services. It needs no bundle pin.

### Delivering Alerts

Prometheus evaluates the rules and shows them on its Alerts page, but notifies
nobody until it knows an Alertmanager. The deployment does not run one and
ships no receiver. To deliver alerts:

1. Write your routing from `alertmanager.example.yml`: keep the routes and
   inhibit rules, replace the example webhook receivers with your own
   (`webhook_configs`, `email_configs`, `slack_configs`, `pagerduty_configs`,
   ...), and check it with `amtool check-config`.
2. Run Alertmanager where the node's Prometheus can reach it: a host or
   service of your own, or a container attached to the monitoring network
   (`<project>_xian-net`). Keep its port on loopback or behind authenticated
   access, like Prometheus and Grafana.
3. Set `xian_alertmanager_targets` in the inventory, for example
   `["alertmanager.ops.internal:9093"]`, and run `playbooks/deploy.yml`. The
   rendered Prometheus configuration then gets the `alerting` section for
   those targets; the default `[]` renders none.
4. Confirm that `http://127.0.0.1:<prometheus port>/api/v1/alertmanagers`
   lists the targets as active, then send a test alert
   (`amtool alert add XianTestAlert --alertmanager.url=http://<target>`) and
   check that your receiver gets it.

The example routing sends critical alerts, BDS recovery alerts, and warnings
to separate receivers, and inhibits the CometBFT-derived alerts while the
CometBFT target is down, `XianPeersLow` under `XianNoPeers`, and the low or
filling disk alerts under `XianDiskSpaceCritical`.

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
The upload playbook validates the staged home's genesis and any manifest pin
before stopping a managed runtime or changing its home.
It is for a host whose node home has not signed yet. A prepared archive
carries a fresh `data/priv_validator_state.json`, so `push-home.yml` refuses a
home whose signing state is above height 0 (with either
`xian_node_home_replace` value) instead of letting the validator sign those
heights again. An existing home with missing, unreadable, or malformed signing
state is also refused: an unknown signing height is not a fresh validator.
The role verifies `config/config.toml` before trusting that state file. Missing
or invalid configuration, custom signing-state paths, and external signers
are refused because a default height-zero file does not prove their signing
history is empty. Preserve those homes and use a recovery workflow instead.
Recover such a node with path 3, which keeps its keys and signing state.
If a managed runtime exists, the role stops it and rechecks signing state
before replacing the home, so signing progress made during shutdown cannot be
erased. Processes started outside the managed Compose runtime must be stopped
before this workflow.

### 2. Offline Application State Snapshots

`xian-state-snapshot` export/import operates on application data only. It does
not contain CometBFT's complete consensus, block and evidence stores and cannot
bootstrap a node. Use these APIs for offline analysis and service workflows.
`scripts/validate_state_snapshot_archive.py` checks this offline format only;
it does not verify a bootable full-node store.

### 3. Verified Full-Node-Store Snapshot From the Node Profile

Use this when the node profile carries `snapshot_url` and trusted
`snapshot_signing_keys`:

```bash
ansible-playbook playbooks/restore-network-snapshot.yml
```

The playbook validates profile inputs, stops the runtime, invokes the canonical
`xian-abci` full-store verifier inside the node image, and starts the runtime
only after restore succeeds, one host at a time. The expected chain id is
`xian_snapshot_expected_chain_id`, or the network manifest chain id when empty.

The signed full-store manifest identifies `snapshot_kind: "full_node_store"`
and binds chain/genesis, height, application root, block hash, archive checksum
and compressed/unpacked sizes. Complete `data/` and `xian/` stores and their
native CometBFT checkpoint/history must pass verification before publication.
This playbook selects the signed-manifest flow and requires a complete
full-node-store archive. The lower-level restore
API on classical homes also supports an independently trusted archive checksum, subject to the
same full-store, native-checkpoint, genesis, application-root, history and
resource checks. A self-declared checksum or an unpinned unsigned archive is
not a trust anchor; this playbook adds no checksum-only option.

For a post-quantum publisher, authenticate and install its complete
`ml-dsa-65:<public-key-hex>` pin in the network manifest's
`snapshot_signing_keys`. Profiles inherit that list and may select a subset.
The node image must support v3 ML-DSA-65 full-store manifests. A PQ pin,
ML-DSA-65 consensus genesis or account registry requires a signed v3 manifest,
including for local archives and recovery plans with an independent checksum.

Recipient configuration, node/validator keys and signing state remain local.
Trusting the configured snapshot signer or an independently authenticated
archive checksum is an explicit trust boundary; this workflow does not
independently replay all blocks from genesis.

### 4. CometBFT Configuration

Xian uses unmodified upstream CometBFT. Keep `[statesync].enable` set to `false`
in `config.toml`. Deploy, restart, snapshot restore and health validate the
installed configuration. Bootstrap through ordinary replay from genesis or use
the verified full-store workflow above.

Existing profiles can omit `advanced.statesync` or include a legacy object
with `enabled` absent or set to `false`. If the object is enabled or malformed,
use `stop.yml` and `status.yml` to operate on the existing runtime while you
correct the profile.

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
