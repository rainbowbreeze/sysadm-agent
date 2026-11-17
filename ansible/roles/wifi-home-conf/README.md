# `wifi-home-conf` — Persistent WiFi Profiles & Dual-Homed Routing (`NetworkManager` & `ConnMan`)

This module provisions up to two persistent WiFi connection profiles from secret variables in `machines/<MACHINE_NAME>/secrets.yml`, activates the highest-priority available network (`profile1` first, falling back to `profile2`), and configures **source-based policy routing** (`table 200`, `ip rule` priority `100`, loose `rp_filter=2`) so the machine remains simultaneously reachable over both **Ethernet (`eth0`)** and **WiFi (`wlan0`)** across different subnets/VLANs.

`tasks/main.yml` automatically dispatches to the native network stack for the target OS:
- **`Debian` / `Ubuntu` / `Alpine` (`tasks/networkmanager.yml`)**: Manages `/etc/NetworkManager/system-connections/<ssid>-profile.nmconnection` + `/etc/NetworkManager/dispatcher.d/99-wifi-source-routing`.
- **`TechNexion i.MX Release Distro` (`tasks/connman.yml`)**: Sets regulatory domain (`/etc/udev/rules.d/85-regulatory.rules`), manages `/var/lib/connman/wifi.config` (`0600`), activates via `connmanctl`, and maintains dual-homed policy routing via `wifi-source-routing.service` (`AF_NETLINK` watcher).

---

## 1. Secret & Configuration Variables

Define the WiFi credentials in `machines/<MACHINE_NAME>/secrets.yml` (gitignored):

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `wifi_profile1_ssid` | At least one of `profile1` or `profile2` | `""` | Primary WiFi network SSID. |
| `wifi_profile1_password` | Required when `wifi_profile1_ssid` is set | `""` | WPA-PSK / WPA3 passphrase for `wifi_profile1_ssid`. |
| `wifi_profile2_ssid` | Optional | `""` | Secondary/fallback WiFi network SSID. |
| `wifi_profile2_password` | Required when `wifi_profile2_ssid` is set | `""` | WPA-PSK / WPA3 passphrase for `wifi_profile2_ssid`. |
| `wifi_home_conf_interface` | Optional (in `vars.yml`) | `"wlan0"` | Target wireless interface. |
| `wifi_home_conf_activate` | Optional (in `vars.yml`) | `true` | Immediately connect to the configured WiFi profile during provisioning. |
| `wifi_home_conf_profile1_priority` | Optional (in `vars.yml`) | `10` | NetworkManager `autoconnect-priority` for `profile1`. |
| `wifi_home_conf_profile2_priority` | Optional (in `vars.yml`) | `5` | NetworkManager `autoconnect-priority` for `profile2`. |
| `wifi_home_conf_regdom` | Optional (in `vars.yml`) | `"IT"` | Regulatory domain applied via udev + `iw reg set` on ConnMan/Yocto targets. |
| `wifi_home_conf_source_routing` | Optional (in `vars.yml`) | `true` | Configures source-based policy routing (`ip rule` + routing table) so the WiFi IP remains reachable across subnets while `eth0` is plugged in. |
| `wifi_home_conf_route_table` | Optional (in `vars.yml`) | `200` | Routing table ID used for WiFi source-based policy routing. |
| `wifi_home_conf_rule_priority` | Optional (in `vars.yml`) | `100` | `ip rule` priority for WiFi source-based policy routing. |

---

## 2. Verifying & Controlling Profiles on the Target Machine

### Debian / Ubuntu / Alpine (`NetworkManager`)

```bash
nmcli connection show
nmcli device status
ip rule show && ip route show table 200
```

### TechNexion Yocto (`ConnMan`)

```bash
connmanctl services
iw reg get
systemctl status wifi-source-routing.service
ip rule show && ip route show table 200
```
