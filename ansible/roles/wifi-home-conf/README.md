# `wifi-home-conf` — Persistent NetworkManager WiFi Profiles (`<ssid>-profile`)

This module provisions one or two persistent **NetworkManager** WiFi connection profiles (`/etc/NetworkManager/system-connections/<ssid>-profile.nmconnection`) based on secret variables defined in `machines/<MACHINE_NAME>/secrets.yml`, reloads NetworkManager, and activates the configured profile (`profile1` first, falling back to `profile2` if `profile1` fails or is unset).

---

## 1. Secret & Configuration Variables

Define the WiFi credentials in `machines/<MACHINE_NAME>/secrets.yml` (gitignored):

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `wifi_profile1_ssid` | At least one of `profile1` or `profile2` | `""` | Primary WiFi network SSID. Creates profile `<wifi_profile1_ssid>-profile`. |
| `wifi_profile1_password` | Required when `wifi_profile1_ssid` is set | `""` | WPA-PSK passphrase for `wifi_profile1_ssid`. |
| `wifi_profile2_ssid` | Optional | `""` | Secondary/fallback WiFi network SSID. Creates profile `<wifi_profile2_ssid>-profile`. |
| `wifi_profile2_password` | Required when `wifi_profile2_ssid` is set | `""` | WPA-PSK passphrase for `wifi_profile2_ssid`. |
| `wifi_home_conf_interface` | Optional (in `vars.yml`) | `"wlan0"` | Target wireless interface bound by the NetworkManager profiles. |
| `wifi_home_conf_activate` | Optional (in `vars.yml`) | `true` | Whether to run `nmcli connection up` on the profile(s) at the end of provisioning. |
| `wifi_home_conf_profile1_priority` | Optional (in `vars.yml`) | `10` | `autoconnect-priority` for `profile1`. |
| `wifi_home_conf_profile2_priority` | Optional (in `vars.yml`) | `5` | `autoconnect-priority` for `profile2`. |
| `wifi_home_conf_source_routing` | Optional (in `vars.yml`) | `true` | Configures source-based policy routing (`ip rule` + routing table) so the WiFi IP remains reachable from other subnets/VLANs even while `eth0` is plugged in. |
| `wifi_home_conf_route_table` | Optional (in `vars.yml`) | `200` | Routing table ID used for WiFi source-based policy routing. |
| `wifi_home_conf_rule_priority` | Optional (in `vars.yml`) | `100` | `ip rule` priority for WiFi source-based policy routing. |

---

## 2. Deployed Files & Behavior

- **NetworkManager Keyfiles (`/etc/NetworkManager/system-connections/`)**:
  - `/etc/NetworkManager/system-connections/<wifi_profile1_ssid>-profile.nmconnection` (`0600`, `root:root`, `autoconnect=true`, `autoconnect-priority=10`) when `wifi_profile1_ssid` is non-empty.
  - `/etc/NetworkManager/system-connections/<wifi_profile2_ssid>-profile.nmconnection` (`0600`, `root:root`, `autoconnect=true`, `autoconnect-priority=5`) when `wifi_profile2_ssid` is non-empty.
- **Source-Based Policy Routing (`/etc/NetworkManager/dispatcher.d/99-wifi-source-routing`)**:
  - Populates routing table `200` with `wlan0`'s link route and default gateway, and adds `ip rule add from <wlan0_ip>/32 lookup 200 priority 100` whenever `wlan0` comes up or renews DHCP, preventing asymmetric routing when `eth0` is simultaneously connected on another subnet/VLAN.
- **Activation Flow**:
  1. Reloads NetworkManager profiles (`nmcli connection reload`) whenever a keyfile is created or updated.
  2. Runs `nmcli connection up "<wifi_profile1_ssid>-profile"` when `wifi_profile1_ssid` is set.
  3. Automatically falls back to `nmcli connection up "<wifi_profile2_ssid>-profile"` if `profile1` activation fails (or if only `profile2` is configured).

---

## 3. Verifying & Controlling Profiles on the Target Machine

```bash
# List NetworkManager connection profiles
nmcli connection show

# Check active connection on wlan0
nmcli device status

# Manually switch between configured profiles
sudo nmcli connection up "<SSID>-profile"
sudo nmcli connection down "<SSID>-profile"
```
