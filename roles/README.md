# Roles

## Purpose
- This folder contains the implementation details behind the deployment playbooks.

## Contents
- `host_hardening/`: host sysctl baseline and opt-in SSH/firewall hardening
- `docker_host/`: Docker bootstrap
- `xian_profile/`: node profile loading and runtime fact derivation
- `xian_node_home/`: prepared home upload and extraction
- `xian_runtime/`: runtime rendering, remote configuration, and Compose operations

```mermaid
flowchart LR
  Playbooks["Playbooks"] --> Hardening["host_hardening"]
  Playbooks --> DockerHost["docker_host"]
  Playbooks --> Profile["xian_profile"]
  Playbooks --> NodeHome["xian_node_home"]
  Playbooks --> Runtime["xian_runtime"]
  Hardening --> Host["Prepared Linux host"]
  DockerHost --> Host["Prepared Linux host"]
  Profile --> Runtime
  NodeHome --> Home["Installed node home"]
  Runtime --> Compose["Rendered Compose runtime"]
  Home --> Compose
  Host --> Compose
```
