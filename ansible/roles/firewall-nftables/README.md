# `firewall-nftables` — Stateful Dual-Stack (`inet`) `nftables` Firewall

This module installs and configures **`nftables`** (`table inet filter`) on Debian/Ubuntu (`Debian`) and Alpine (`Alpine`) hosts. It enforces a default-drop policy on unsolicited inbound and forwarded packets while guaranteeing SSH access on `machine_ssh_port` (anti-lockout safeguard) and opening any configured TCP/UDP service ports.

---

## 1. Configuration & Secret Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `firewall_nftables_enabled` | Optional | `true` | Enables and starts `nftables` with the configured ruleset. When `false`, stops/disables `nftables` and flushes active rules. |
| `firewall_nftables_ssh_port` | Auto | `{{ machine_ssh_port \| default(21979) }}` | Inbound TCP SSH port that is **always** allowed to prevent lockout. |
| `firewall_nftables_allow_icmp` | Optional | `true` | Allows inbound IPv4 ICMP and IPv6 ICMPv6 (when `false`, only essential IPv6 neighbor discovery is allowed). |
| `firewall_nftables_allow_mdns` | Optional | `false` | When `true`, allows inbound UDP port `5353` for Avahi/mDNS `.local` discovery. |
| `firewall_nftables_allowed_tcp_ports` | Optional | `[]` | List of extra inbound TCP ports to allow (e.g., `["{{ stream_ustreamer_port }}", "{{ node_exporter_port }}"]`). |
| `firewall_nftables_allowed_udp_ports` | Optional | `[]` | List of extra inbound UDP ports to allow. |

> **Security Note**: In real machine configurations, store custom service port numbers in `machines/<MACHINE_NAME>/secrets.yml` and reference them via Jinja2 variables in `vars.yml` (or define the port lists directly in `secrets.yml`).

---

## 2. Deployed Files & Services

- **Ruleset File**:
  - Debian/Ubuntu: `/etc/nftables.conf` (`0600`, `root:root`, syntax-validated via `/usr/sbin/nft -c -f` before deployment)
  - Alpine Linux: `/etc/nftables.nft` (`0600`, `root:root`)
- **System Service**:
  - `nftables` enabled at boot and reloaded atomically via `/usr/sbin/nft -f`.

---

## 3. Verifying & Controlling the Firewall on the Target Machine

```bash
# View the active nftables ruleset
sudo nft list ruleset

# Check nftables systemd service status
sudo systemctl status nftables

# Validate config file syntax manually
sudo nft -c -f /etc/nftables.conf

# Reload rules from /etc/nftables.conf
sudo nft -f /etc/nftables.conf
```
