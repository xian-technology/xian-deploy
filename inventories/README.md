# Inventories

## Purpose
- This folder contains example inventory structure for `xian-deploy`.

## Notes
- Keep real inventories and secrets out of the public repo.
- Use this folder as the shape reference for private deployment repos.
- The `example/solutions/` subfolder shows the recommended host layouts for
  the validated remote starter flows.

```mermaid
flowchart LR
  Example["Example inventory structure"] --> PrivateInventory["Private inventory repo"]
  PrivateInventory --> GroupVars["Group vars and host vars"]
  PrivateInventory --> Secrets["Operator secrets"]
  PrivateInventory --> Playbooks["xian-deploy playbooks"]
```
