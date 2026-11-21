# Examples

This file maps the current profile-driven deploy architecture onto
`xian-deploy`.

`xian-deploy` does not define runtime presets. Each host points at the node
profile it should run with `xian_node_profile`; inventory only supplies deploy
bindings such as host paths, published ports, database credentials, resource
and limits.

## Inventory Shapes

Use the layouts under `inventories/example/examples/` as starting points:

- `validator-hosts.yml`: one profile generated from the `validator` template
  deployed to one host; add one host entry per further validator.

Keep real inventories, host vars, and secrets in a private deployment repo.

## Deploy Sequence

Generate the network and node profiles with `xian-cli`. Run `xian node init`
for each profile and archive the resulting home contents, including
`config/genesis.json`. Set `xian_node_profile` and `xian_node_home_archive` to
those files in inventory. Set `xian_network_manifest` to the preparation
manifest so deploy can verify the chain ID and any `genesis_sha256` pin.

Run the playbooks in sequence.

```bash
ansible-playbook -i inventories/<your>/hosts.yml playbooks/bootstrap.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/push-home.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/deploy.yml
ansible-playbook -i inventories/<your>/hosts.yml playbooks/health.yml
```

After the network is healthy, run product repo or example application
bootstraps against the deployed RPC/BDS endpoints. Product contracts and
application examples are post-start concerns; they are not deploy presets.
