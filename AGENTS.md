# Repository Guidelines

## Scope
- `xian-deploy` owns Linux-focused deployment playbooks for released Xian node images.
- This repo should deploy released artifacts, not clone and build Xian source on remote hosts.
- Keep it aligned with the published `xian-node` and `xian-node-split` images from `xian-stack`.

## Shared Convention
- Follow the shared repo convention in `xian-meta/docs/REPO_CONVENTIONS.md`.
- Keep this repo aligned with that standard for root notes and folder-level README entrypoints.
- Follow the shared change workflow in `xian-meta/docs/CHANGE_WORKFLOW.md`.
- Before push, review `xian-docs-web` operator docs impact and run the local validation path from this repo.

## Project Layout
- `playbooks/`: operator entrypoints such as bootstrap, deploy, upgrade, restore, and smoke
- `roles/`: implementation of host bootstrap, home upload, and runtime rendering
- `inventories/`: example inventory structure and shared variables
- `docs/`: internal architecture and backlog notes

## Workflow
- Favor stable release-image deployment over mutable remote source checkouts.
- Keep prepared node-home handling separate from runtime deployment; that split is intentional.
- Treat `xian-cli` as the node-home preparation UX and this repo as the remote deployment layer.

## Validation
- Preferred validation path: `make validate`
- This repo currently validates playbook syntax and deployment structure, not a live remote host.

## Shared Agent Practices
- Keep changes clean, modular, and professional. Prefer small, cohesive modules, clear naming, explicit boundaries, and tests over quick patches.
- When code behavior, public APIs, user workflows, operator workflows, or configuration semantics change, check whether `../xian-docs-web` needs corresponding documentation updates. If this repo is `xian-docs-web`, update the relevant published docs in place. Write durable user/developer documentation, not a changelog entry.
- Follow `../xian-meta/docs/CODE_GRAPH_WORKFLOW.md` for graph freshness and source verification. Before relying on graph results, run `python3 ../xian-meta/scripts/graphify_workspace.py status --repo xian-deploy` and refresh that repo if stale.
- For codebase questions, use the local graph first when `graphify-out/graph.json` exists: run `graphify query "<question>"`; use `graphify affected "<symbol>" --depth 1` for direct dependents, larger depths for transitive impact, and `graphify path "<A>" "<B>" --directed` for call paths and `graphify explain "<concept>"` for focused concepts.
- Dirty `graphify-out/` files are expected after hooks or incremental updates and are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- Use `graphify-out/wiki/index.md` for broad navigation when it exists. Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- For any non-trivial code change, update the local graph before final verification when `graphify-out/graph.json` exists. Run `python3 ../xian-meta/scripts/graphify_workspace.py refresh --repo xian-deploy` from the repo root; use `--force` only for inspected, intentional shrinkage.
- After updating the graph, check cross-repo impact before finishing: use `graphify affected`, inspect returned source locations, and search affected sibling repos. A missing edge or truncated result does not prove there are no other consumers.
- If graphify or dependency analysis shows affected sibling repos, update those repos in the same change when the impact is real and the fix is in scope.
- Treat `graphify-out/` as a generated local artifact. Do not commit it.
