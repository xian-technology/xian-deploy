# Presets

## Purpose
- This folder contains reusable variable presets for common remote deployment postures.

## Contents
- `templates/`: template-aligned runtime presets for `xian-deploy`

## Notes
- Apply these with `ansible-playbook ... -e @presets/templates/<name>.yml`.
- Keep environment-specific secrets and host-specific values in your private
  inventory, not in these public presets.
