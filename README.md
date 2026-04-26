# xian-deploy

`xian-deploy` is the remote deployment layer for Xian nodes on Linux hosts. It
deploys released node images and prepared node-home archives instead of
building source code on the target machine.

## Quick Start

```bash
ansible-playbook playbooks/bootstrap.yml
ansible-playbook playbooks/push-home.yml
ansible-playbook playbooks/deploy.yml
ansible-playbook playbooks/health.yml
```

That flow assumes:

- a prepared node home already exists
- inventory and group vars are set for the target hosts
- the target uses released Xian images rather than local source builds

## Principles

- Deploy released artifacts, not source checkouts.
- Keep host setup explicit and inventory-driven.
- Treat dashboard, BDS, and monitoring as optional layers on top of the core
  node runtime.
- Keep remote flows composable: bootstrap, deploy, upgrade, health, and
  recovery should remain separate entrypoints.

## Key Directories

- `playbooks/`: bootstrap, deploy, upgrade, smoke, and restore entrypoints
- `roles/`: reusable deployment roles and runtime tasks
- `inventories/`: example inventory and group variable layout
- `presets/`: reusable runtime posture presets for remote starter flows
- `docs/`: repo-local architecture, operations, and solution notes

## Validation

```bash
make validate
```

## Related Docs

- [AGENTS.md](AGENTS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/BACKLOG.md](docs/BACKLOG.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/SOLUTIONS.md](docs/SOLUTIONS.md)
- [docs/README.md](docs/README.md)

## Common Playbooks

Use these playbooks directly when operating remote hosts:

- `playbooks/bootstrap.yml`: prepare hosts for Docker-based Xian runtime
- `playbooks/push-home.yml`: upload a prepared node-home archive
- `playbooks/deploy.yml`: start or reconfigure the released node runtime
- `playbooks/upgrade.yml`: roll forward to a newer released image
- `playbooks/health.yml`: run remote health checks
- `playbooks/bootstrap-state-sync.yml`: join by protocol state sync
- `playbooks/restore-state-snapshot.yml`: restore an application-state snapshot

For validated reference-app flows, pair those playbooks with the starter
presets under `presets/templates/` as described in `docs/SOLUTIONS.md`.
