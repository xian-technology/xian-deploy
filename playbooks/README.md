# Playbooks

## Purpose
- This folder contains the operator entrypoints for `xian-deploy`.

## Contents
- `bootstrap.yml`: prepare the host
- `push-home.yml`: upload a prepared node home
- `deploy.yml`: deploy or update the runtime
- `health.yml`: detailed remote runtime, BDS, state-sync, and disk checks
- `upgrade.yml`: serial rollout
- `bootstrap-state-sync.yml`: deploy with validated state-sync settings
- `restore-state-snapshot.yml`: restore an exported state snapshot
- `smoke.yml`: basic post-deploy health check
