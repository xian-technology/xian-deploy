ANSIBLE ?= uvx --from ansible-core ansible-playbook
ANSIBLE_INVENTORY_CMD ?= uvx --from ansible-core ansible-inventory
ANSIBLE_LINT ?= uvx --from ansible-lint ansible-lint --profile min

.PHONY: lint validate
lint:
	$(ANSIBLE_LINT) playbooks roles inventories

validate:
	$(ANSIBLE_INVENTORY_CMD) -i inventories/example/hosts.yml --list >/dev/null
	$(ANSIBLE) --syntax-check playbooks/bootstrap.yml
	$(ANSIBLE) --syntax-check playbooks/push-home.yml
	$(ANSIBLE) --syntax-check playbooks/deploy.yml
	$(ANSIBLE) --syntax-check playbooks/health.yml
	$(ANSIBLE) --syntax-check playbooks/status.yml
	$(ANSIBLE) --syntax-check playbooks/bootstrap-state-sync.yml
	$(ANSIBLE) --syntax-check playbooks/restart.yml
	$(ANSIBLE) --syntax-check playbooks/stop.yml
	$(ANSIBLE) --syntax-check playbooks/upgrade.yml
	$(ANSIBLE) --syntax-check playbooks/restore-state-snapshot.yml
	$(ANSIBLE) --syntax-check playbooks/smoke.yml
