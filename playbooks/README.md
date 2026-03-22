# Playbooks

## Purpose
- This folder contains the operator entrypoints for `xian-deploy`.

## Contents
- `bootstrap.yml`: prepare the host
- `push-home.yml`: upload a prepared node home
- `deploy.yml`: deploy or update the runtime
- `upgrade.yml`: serial rollout
- `restore-state-snapshot.yml`: restore an exported state snapshot
- `smoke.yml`: basic post-deploy health check

