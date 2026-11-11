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

UFW does not filter Docker-published container ports: Docker inserts its own
iptables rules ahead of UFW. Keep RPC, metrics, and monitoring bound to
loopback unless they are intentionally public; the firewall alone does not
close a port published on `0.0.0.0`.
