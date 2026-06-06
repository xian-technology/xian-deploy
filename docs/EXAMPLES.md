# Examples

This file maps the current profile-driven deploy architecture onto
`xian-deploy`.

`xian-deploy` does not define runtime presets. Each host points at the node
profile it should run with `xian_node_profile`; inventory only supplies deploy
bindings such as host paths, published ports, database credentials, resource
limits, and `xian_deploy_topology`.

## Inventory Shapes

Use the layouts under `inventories/example/examples/` as starting points:

- `single-node-indexed-hosts.yml`: one generated `single-node-indexed` profile
  deployed to one host.
- `consortium-5-hosts.yml`: five generated `consortium-5` validator profiles
  deployed to five hosts.

Keep real inventories, host vars, and secrets in a private deployment repo.

## Deploy Sequence

Generate the network and node profiles with `xian-cli`, copy the profile paths
into your inventory, then run:

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml
```

After the network is healthy, run product repo or example application
bootstraps against the deployed RPC/BDS endpoints. Product contracts and
application examples are post-start concerns; they are not deploy presets.
