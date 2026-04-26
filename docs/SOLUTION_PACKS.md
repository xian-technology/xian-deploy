# Solution Packs

This file mirrors the validated remote starter flows for the Xian solution
packs into `xian-deploy`.

Use it together with:

- the packaged `xian-cli solution-pack starter ... --flow remote` output
- the reusable runtime presets under `presets/templates/`
- the example host layouts under `inventories/example/solution-packs/`

## Credits Ledger

Remote posture:

- template class: `embedded-backend`
- inventory shape: `inventories/example/solution-packs/embedded-backend-hosts.yml`
- runtime preset: `presets/templates/embedded-backend.yml`

Recommended sequence:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml \
  -e @presets/templates/embedded-backend.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml \
  -e @presets/templates/embedded-backend.yml
```

Use the same remote posture for the Workflow Backend pack.

## DEX

Remote posture:

- template class: `consortium-3`
- inventory shape: `inventories/example/solution-packs/consortium-3-hosts.yml`
- validator preset: `presets/templates/consortium-validator.yml`
- service-node preset: `presets/templates/consortium-service-node.yml`

Recommended sequence:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml
```

After the network is healthy, deploy the pinned DEX bundle from the
`xian-stack` checkout with `scripts/backend.py localnet-dex-bootstrap`, pointed
at the service RPC and an explicit bootstrap wallet. Keep validators minimal;
use the service node for indexed reads, DEX web inspection, and automation.

## Registry / Approval

Remote posture:

- template class: `consortium-3`
- inventory shape: `inventories/example/solution-packs/consortium-3-hosts.yml`
- validator preset: `presets/templates/consortium-validator.yml`
- service-node preset: `presets/templates/consortium-service-node.yml`

Recommended host-variable split:

- validator hosts:
  `consortium-validator.yml`
- service-node host:
  `consortium-service-node.yml`

Recommended sequence:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml
```

The service node should carry the BDS and monitoring posture. Validators should
stay minimal.

## Stable Protocol

Remote posture:

- template class: `consortium-3`
- inventory shape: `inventories/example/solution-packs/consortium-3-hosts.yml`
- validator preset: `presets/templates/consortium-validator.yml`
- service-node preset: `presets/templates/consortium-service-node.yml`

Recommended host-variable split:

- validator hosts:
  `consortium-validator.yml`
- service-node host:
  `consortium-service-node.yml`

Recommended sequence:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml
```

After the network is healthy, run the canonical protocol bootstrap from the
`xian-stable-protocol` checkout against the deployed RPC. Keep the service node
responsible for BDS-backed inspection, monitoring, and any risk-dashboard or
automation surfaces. Validators should stay focused on consensus work.

## Workflow Backend

Remote posture:

- template class: `embedded-backend`
- inventory shape: `inventories/example/solution-packs/embedded-backend-hosts.yml`
- runtime preset: `presets/templates/embedded-backend.yml`

Recommended sequence:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml \
  -e @presets/templates/embedded-backend.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml \
  -e @presets/templates/embedded-backend.yml
```

Use the same remote posture as Credits Ledger, then point the
`xian-py/examples/workflow_backend` processor, projector, and API flows at the
deployed node.
