# Example Inventory Shapes

## Purpose
- This folder contains example host layouts for deploying node profiles onto
  remote hosts.

## Files
- `validator-hosts.yml`: one validator profile (generated from the `validator`
  template) on one host. Add one host entry per further validator.

## Notes
- These are only structure references.
- Keep real inventories, host vars, and secrets in a private deployment repo.
- Set `xian_node_profile` per host. The profile carries runtime intent; the
  inventory carries deploy bindings and secrets.

```mermaid
flowchart LR
  ProfileBundle["Generated node profiles"] --> InventoryShape["Example inventory shape"]
  InventoryShape --> PrivateRepo["Private deployment repo"]
  Profiles["Node profiles"] --> PrivateRepo
  PrivateRepo --> Playbooks["xian-deploy playbooks"]
  Playbooks --> Hosts["Remote hosts"]
```
