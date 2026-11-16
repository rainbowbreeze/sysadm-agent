# `wifi-bcm4339-k5` — Broadcom BCM4339 WiFi & Bluetooth on PICO-PI-IMX7D (Linux Kernel `5.x`)

This module configures the **Broadcom BCM4339 (AMPAK AP6335)** SDIO WiFi (`wlan0`) and UART Bluetooth (`hci0`) controller on **TechNexion PICO-PI-IMX7D** running **Ubuntu 22.04 LTS (`Linux 5.15.71`)** without modifying `/dev/mmcblk2p1` (`uEnv.txt` or `.dtb`):

> **Note**: For boards running **Linux Kernel `6.x`** (e.g., TechNexion Yocto `6.18.x` or Debian `6.x`), use **`wifi-bcm4339-k6`** instead.

- **Kernel Modules (`brcmfmac.ko`, `brcmutil.ko`)**: Installs prebuilt out-of-tree `5.15.71` wireless modules and runs `depmod`.
- **Firmware (`/lib/firmware/brcm/`)**: Installs `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, and `BCM4335C0.hcd`.
- **32.768 kHz Reference Clock (`CCM_CLKO2`)**: Stock `imx7d-pico-pi-qca.dtb` on `5.15.71` already enumerates BCM4339 on SDIO (`mmc1:0001:1`), `wlreg_on`, `wifi_pwr_on`, `bt_rfkill`, and `/dev/ttymxc6`, whereas adding `assigned-clocks` onto `clock-controller@30380000` in DTB hangs NXP downstream `lf-5.15.71` during `CLK_OF_DECLARE` early boot. Therefore `/dev/mmcblk2p1` is left **completely untouched** and `/usr/local/sbin/brcm-clko2-enable.py` enables `CCM_CLKO2` (`0x3038be00` -> `MUX=7` `ckil` `32.768 kHz`, `ENABLE=1`) automatically via an `install brcmfmac` modprobe hook on every boot (no reboot required).
- **Bluetooth Service (`brcm-bluetooth.service`)**: Installs `/usr/local/sbin/brcm-bt-reset.sh` (`ExecStartPre`) and enables `brcm-bluetooth.service` (`TimeoutStartSec=25`), pulsing AP6335 BT reset (`GPIO4_IO18` / `gpio114`) `0 -> 1` after `CCM_CLKO2` is active and attaching `/dev/ttymxc6` at `3,000,000` baud RTS/CTS (`hci0`).

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D (`5.15.71`)

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **WiFi Controller (`AMPAK AP6335`)** | SDIO (`30b50000.mmc` / `usdhc2`) | Broadcom **BCM4339** (`02D0:4335`), interface `wlan0`, driver `brcmfmac` |
| **SDIO & BT LPO Clock (`CCM_CLKO2`)** | `0x3038be00` (`CCM_TARGET_ROOT127`) | `32.768 kHz` (`ckil`) enabled at runtime via `/usr/local/sbin/brcm-clko2-enable.py` |
| **Bluetooth Controller (`BCM4335C0`)** | UART7 (`/dev/ttymxc6`, `30a90000.serial`) | 3,000,000 baud RTS/CTS, `bt_rfkill` (`GPIO4_IO17` / `gpio113`) + AP6335 BT reset (`GPIO4_IO18` / `gpio114`), interface `hci0` |

---

## 2. Deployed Files & Services

- **Kernel Modules (`/lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/`)**:
  - `brcmfmac/brcmfmac.ko` & `brcmutil/brcmutil.ko`
- **Firmware (`/lib/firmware/brcm/`)**:
  - `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, `BCM4335C0.hcd`
- **Clock & Modprobe Hook**:
  - `/usr/local/sbin/brcm-clko2-enable.py`
  - `/etc/modprobe.d/brcmfmac.conf` (`blacklist bcmdhd`, `install brcmfmac ...`, `options brcmfmac feature_disable=0x82000`)
- **Bluetooth Systemd Unit & Reset Script**:
  - `/usr/local/sbin/brcm-bt-reset.sh`
  - `/etc/systemd/system/brcm-bluetooth.service`

---

## 3. Verifying & Controlling WiFi (`wlan0`) and Bluetooth (`hci0`)

```bash
# Confirm WiFi driver loaded and wlan0 interface is up
ip link show wlan0
iw dev
dmesg | grep brcmfmac
sudo nmcli dev wifi list

# Confirm Bluetooth HCI interface (hci0) is UP RUNNING
hciconfig -a
systemctl status brcm-bluetooth.service
bluetoothctl show
```

---

## 4. Deep-Dive & Manual Reproduction Guide

- [wifi_config_ubuntu.md](./wifi_config_ubuntu.md) — Root-cause analysis of the `5.15.71` `CLK_OF_DECLARE` DTB boot hang, `CCM_CLKO2` (`32.768 kHz`) bring-up, Bluetooth `GPIO4_IO18` (`gpio114`) reset sequence, and dual-homed (`eth0` + `wlan0`) source policy routing reproduction steps.
