# Roles

## Purpose
- This folder contains the implementation details behind the deployment playbooks.

## Contents
- `docker_host/`: Docker bootstrap
- `xian_node_home/`: prepared home upload and extraction
- `xian_runtime/`: runtime rendering, remote configuration, and Compose operations

```mermaid
flowchart LR
  Playbooks["Playbooks"] --> DockerHost["docker_host"]
  Playbooks --> NodeHome["xian_node_home"]
  Playbooks --> Runtime["xian_runtime"]
  DockerHost --> Host["Prepared Linux host"]
  NodeHome --> Home["Installed node home"]
  Runtime --> Compose["Rendered Compose runtime"]
  Home --> Compose
  Host --> Compose
```
