# Template Presets

## Purpose
- This folder contains reusable remote deployment presets that mirror the canonical Xian template classes.

## Presets
- `embedded-backend.yml`: service-node posture for application-oriented remote deployments
- `consortium-validator.yml`: validator posture for shared-state consortium deployments
- `consortium-service-node.yml`: service-node posture for consortium deployments with BDS and monitoring

## Usage

Apply one of these presets with:

```bash
ansible-playbook playbooks/deploy.yml -e @presets/templates/embedded-backend.yml
```

Use the solution runbook in `docs/SOLUTIONS.md` to see which preset matches
each reference-app flow.

```mermaid
flowchart LR
  Embedded["embedded-backend"] --> ServiceNode["Single service-node deployment"]
  Validator["consortium-validator"] --> ValidatorHost["Validator host"]
  ConsortiumService["consortium-service-node"] --> IndexedHost["Service node with BDS and monitoring"]
  SolutionRunbook["docs/SOLUTIONS.md"] --> Embedded
  SolutionRunbook --> Validator
  SolutionRunbook --> ConsortiumService
```
