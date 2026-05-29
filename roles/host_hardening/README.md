# host_hardening

Applies the host-level baseline used before Docker and the Xian runtime are
installed.

Default behavior is intentionally conservative:

- sysctl network/kernel hardening is enabled
- SSH hardening is disabled until explicitly enabled
- UFW firewall management is disabled until explicitly enabled
- unattended upgrades and fail2ban are disabled until explicitly enabled

Enable the access-affecting controls only after confirming the host's SSH port,
operator key access, and required public service ports.
