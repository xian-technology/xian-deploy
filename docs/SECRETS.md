# Secrets

`xian-deploy` inventories should describe topology and runtime intent. Private
keys, validator keys, RPC credentials, backup passphrases, and cloud tokens must
stay encrypted outside normal YAML files.

## Recommended Storage

Use one of these patterns:

- `ansible-vault` encrypted variable files committed to the private operations
  repository.
- `sops` encrypted YAML files committed to the private operations repository.
- Runtime injection from a secret manager in CI or an operator shell.

Do not commit plaintext `priv_validator_key.json`, node keys, wallet keys,
mnemonic phrases, state snapshot passphrases, or provider access tokens.

## Inventory Shape

Keep public deployment data in normal inventory files:

- hostnames and SSH users
- profile paths
- deploy roots
- public peer IDs and RPC endpoints
- non-sensitive service flags

Keep sensitive values in encrypted files and load them through `vars_files` or
CI-provided environment variables:

```yaml
vars_files:
  - secrets/validator-keys.vault.yml
```

## Operator Checks

Before pushing deployment changes:

```bash
git grep -nE '(private_key|mnemonic|seed_phrase|secret|token|password)'
```

False positives are expected, but every match should either be documentation,
an obvious placeholder, or encrypted content.
