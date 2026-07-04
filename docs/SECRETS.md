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

When BDS is enabled, set `xian_bds_password` from a vault or secret manager.
The deploy role rejects empty or weak example passwords. On the remote host it
writes BDS runtime secrets, including DSNs that may contain credentials, under
`xian_runtime_secret_dir` with directory mode `0700` and file mode `0600`;
rendered Compose files only reference those file paths. Do not edit or commit
generated files such as `bds.env`, `bds-dsn`, `bds-password`, or
`validator-private-key.hex`.

Prefer preparing validator keys in the node-home archive. If
`xian_validator_private_key_hex` is supplied for a deployment, load it from a
vault; the role writes it to a private remote file and passes it to the
configure wrapper without exposing the key in host command-line arguments.

## Operator Checks

Before pushing deployment changes:

```bash
git grep -nE '(private_key|mnemonic|seed_phrase|secret|token|password)'
```

False positives are expected, but every match should either be documentation,
an obvious placeholder, or encrypted content.
