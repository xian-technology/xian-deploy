# Repository Guidelines

## Scope
- `xian-deploy` owns Linux-focused deployment playbooks for released Xian node images.
- This repo should deploy released artifacts, not clone and build Xian source on remote hosts.
- Keep it aligned with the published `xian-node` and `xian-node-split` images from `xian-stack`.

## Project Layout
- `playbooks/`: operator entrypoints such as bootstrap, deploy, upgrade, restore, and smoke
- `roles/`: implementation of host bootstrap, home upload, and runtime rendering
- `inventories/`: example inventory structure and shared variables
- `docs/`: internal architecture and backlog notes

## Workflow
- Favor stable release-image deployment over mutable remote source checkouts.
- Keep prepared node-home handling separate from runtime deployment; that split is intentional.
- Treat `xian-cli` as the node-home preparation UX and this repo as the remote deployment layer.

