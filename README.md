# xian-deploy

`xian-deploy` is the Linux-focused deployment layer for Xian nodes. It deploys
released container images and prepared node-home archives instead of cloning or
building source code on remote machines.

## Scope

This repo owns:

- remote host bootstrap and runtime deployment playbooks
- inventory-driven configuration for released Xian node images
- optional enablement of dashboard, BDS, and monitoring services

This repo does not own:

- node-home creation and network-join UX
- runtime image definitions
- deterministic node behavior

## Key Directories

- `playbooks/`: bootstrap, deploy, upgrade, smoke, and restore entrypoints
- `roles/`: reusable deployment roles and runtime tasks
- `inventories/`: example inventory and group variable layout
- `docs/`: repo-local notes and future enhancements

## Validation

```bash
make validate
```

## Related Docs

- [AGENTS.md](AGENTS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/BACKLOG.md](docs/BACKLOG.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/README.md](docs/README.md)

## Workflow

The supported flow is:

1. prepare a node home archive locally
2. bootstrap a remote Linux host with Docker
3. upload the prepared node home
4. configure that home in place with `xian-configure-node`
5. run the released node image in either `integrated` or `fidelity` topology

Common entrypoints:

```bash
ansible-playbook playbooks/bootstrap.yml
ansible-playbook playbooks/push-home.yml
ansible-playbook playbooks/deploy.yml
ansible-playbook playbooks/upgrade.yml
ansible-playbook playbooks/status.yml
ansible-playbook playbooks/health.yml
ansible-playbook playbooks/smoke.yml
ansible-playbook playbooks/bootstrap-state-sync.yml
ansible-playbook playbooks/restart.yml
ansible-playbook playbooks/stop.yml
ansible-playbook playbooks/restore-state-snapshot.yml
```

Optional services include the Xian dashboard, BDS with PostgreSQL, and
Prometheus + Grafana.

## Recovery Runbooks

Use these recovery/bootstrap paths intentionally:

- prepared node-home archive:
  `playbooks/push-home.yml` then `playbooks/deploy.yml`
- application state snapshot import:
  `playbooks/restore-state-snapshot.yml`
- protocol state sync:
  `playbooks/bootstrap-state-sync.yml`

For a fuller remote diagnosis than the basic smoke check, use:

```bash
ansible-playbook playbooks/health.yml
```
