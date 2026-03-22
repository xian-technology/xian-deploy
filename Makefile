ANSIBLE ?= uvx --from ansible-core ansible-playbook

.PHONY: validate
validate:
	$(ANSIBLE) --syntax-check playbooks/bootstrap.yml
	$(ANSIBLE) --syntax-check playbooks/push-home.yml
	$(ANSIBLE) --syntax-check playbooks/deploy.yml
	$(ANSIBLE) --syntax-check playbooks/status.yml
	$(ANSIBLE) --syntax-check playbooks/restart.yml
	$(ANSIBLE) --syntax-check playbooks/stop.yml

