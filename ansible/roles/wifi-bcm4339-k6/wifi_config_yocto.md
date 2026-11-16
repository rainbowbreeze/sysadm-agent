# Persistent Wi-Fi Configuration on TechNexion Yocto (`6.18-wrynose`)

Reference notes for connecting a TechNexion PICO-PI-IMX7D board running **TechNexion i.MX Release Distro (`6.18-wrynose`, kernel `6.18.x`)** with the Broadcom **BCM4339 (`wlan0`)** controller (`wifi-bcm4339-k6` role) to a WPA2-PSK Wi-Fi network and making the connection persistent across reboots.

---

## Step 1: Disable `brcmfmac` Firmware WPA2/SAE Supplicant Offload (Kernel 6.x Fix)

On kernel `6.18.x`, `brcmfmac` enables `BRCMF_FEAT_FWSUP` (`0x2000`, `4WAY_HANDSHAKE_STA_PSK`) and `BRCMF_FEAT_SAE` (`0x80000`) by default, offloading the WPA2-PSK 4-way handshake to the 2019 BCM4339 firmware (`6.37.39.113`), where authentication times out after 10 seconds (`Authentication with <BSSID> timed out`).

Create `/etc/modprobe.d/brcmfmac.conf` so `wpa_supplicant` handles the 4-way handshake in user space:

```ini
# /etc/modprobe.d/brcmfmac.conf
options brcmfmac feature_disable=0x82000
```

*(Note: This file is also deployed automatically by `ansible/roles/wifi-bcm4339-k6/tasks/main.yml`.)*

---

## Step 2: Set Persistent Wi-Fi Regulatory Domain (`IT`) at Boot

To ensure Linux `cfg80211` applies the `IT` (`DFS-ETSI`) regulatory domain as soon as `wlan0` is initialized at boot (before scanning or associating), create `/etc/udev/rules.d/85-regulatory.rules`:

```udev
# /etc/udev/rules.d/85-regulatory.rules
SUBSYSTEM=="net", ACTION=="add", KERNEL=="wlan*", RUN+="/usr/sbin/iw reg set IT"
```

> **Important NVRAM Note**: Keep `ccode=0` (`regrev=0`) unchanged inside `/lib/firmware/brcm/brcmfmac4339-sdio.txt`. The BCM4339 firmware (`6.37.39.113`) does not contain an internal CLM table entry for `ccode=IT` and will disable channel scanning if `ccode` is changed in NVRAM. Leaving `ccode=0` in NVRAM unlocks all 2.4 GHz and 5 GHz hardware channels while Linux `cfg80211` enforces `country IT: DFS-ETSI`.

---

## Step 3: Create a Persistent ConnMan Provisioning Profile

TechNexion Yocto uses **ConnMan** (`connman.service`) + `wpa_supplicant.service` instead of NetworkManager. ConnMan automatically marks any service defined in `/var/lib/connman/*.config` as **Favorite (`*`)** and **AutoConnect (`A`)** across reboots.

Create `/var/lib/connman/wifi.config` (permissions `0600`, owned by `root:root`):

```ini
[global]
Name = WiFi Provisioning
Description = Persistent WiFi connection profile

[service_primary_wifi]
Type = wifi
Name = <WIFI_SSID>
Passphrase = <WIFI_PASSWORD>
```

Set strict permissions:

```bash
chown root:root /var/lib/connman/wifi.config
chmod 0600 /var/lib/connman/wifi.config
```

> **Note**: Do **not** put `AutoConnect = true` inside `[service_*]` in a `.config` provisioning file — `connmand` logs `Unknown configuration key AutoConnect` for `.config` files and already sets `Favorite=true` and `AutoConnect=true` automatically for all provisioned services.

---

## Step 4: Activate or Reboot & Verify

Reboot the board (so `brcmfmac` loads with `feature_disable=0x82000` and ConnMan auto-connects on boot), or trigger a scan and connection immediately with `connmanctl`:

```bash
# Ensure Wi-Fi technology is powered and scan
connmanctl enable wifi
connmanctl scan wifi

# List services (*AO = Favorite, AutoConnect, Online; *AR = Ready)
connmanctl services

# Manually connect if needed
connmanctl connect wifi_<MAC>_<SSID_HEX>_managed_psk

# Verify regulatory domain, link status, and IPv4 address
iw reg get
iw dev wlan0 link
ip addr show wlan0
```
