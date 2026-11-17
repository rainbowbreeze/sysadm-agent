# `wifi-bcm4339-k6` — Broadcom BCM4339 WiFi & Bluetooth on PICO-PI-IMX7D (Linux Kernel `6.x`)

This module configures the **Broadcom BCM4339 (AMPAK AP6335)** SDIO WiFi (`wlan0`) and UART Bluetooth (`hci0`) controller on **TechNexion PICO-PI-IMX7D** running **Linux Kernel `6.x`** (e.g., **TechNexion i.MX Release Distro `6.18.x`** or **Debian `6.x`**):

> **Note**: For boards running **Linux Kernel `5.x`** (e.g., Ubuntu 22.04 `5.15.71`), use **`wifi-bcm4339-k5`** instead.

- **Built-in Kernel Driver (`brcmfmac`)**: Uses the running `6.x` kernel's built-in `brcmfmac` driver and configures `/etc/modprobe.d/brcmfmac.conf` (`feature_disable=0x82000`, `blacklist bcmdhd`).
- **Firmware (`/lib/firmware/brcm/`)**: Installs `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, and `BCM4335C0.hcd`.
- **In-Place DTB & `uEnv.txt` Updater (`/usr/local/sbin/wifi-bcm4339-update-boot.py`)**: Static CLI script that saves `.orig` backups and patches `imx7d-pico-pi.dtb` in-place via pure-Python FDT to configure `usdhc2_pwrseq` (`mmc-pwrseq-simple`, `32.768 kHz` `IMX7D_CLKO2_ROOT_DIV`), `mmc-pwrseq` on `mmc@30b50000`, and mainline `rfkill-gpio`, while updating `wifi_module=brcm` in-place inside `uEnv.txt` without clobbering `mmcroot`, `uenvcmd`, or `camera-ov5645` nodes.
- **Bluetooth Service (`brcm-bluetooth.service`)**: Stops and masks conflicting `serial-btattach@ttymxc6.{timer,service}` units when present, unblocks `bluetooth` `rfkill`, attaches `/dev/ttymxc6` at `3,000,000` baud RTS/CTS, and verifies `/sys/class/bluetooth/hci0`.

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D (`6.x`)

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **WiFi Controller (`AMPAK AP6335`)** | SDIO (`30b50000.mmc` / `usdhc2`) | Broadcom **BCM4339** (`02D0:4335`), interface `wlan0`, built-in driver `brcmfmac` |
| **SDIO Reference Clock (`usdhc2_pwrseq`)** | `IMX7D_CLKO2_ROOT_DIV` (`32.768 kHz`) | Configured via `mmc-pwrseq-simple` in `imx7d-pico-pi.dtb` (`wifi_module=brcm`) |
| **Bluetooth Controller (`BCM4335C0`)** | UART7 (`/dev/ttymxc6`, `30a90000.serial`) | 3,000,000 baud RTS/CTS flow control, `rfkill-gpio` (`GPIO4_IO17`), interface `hci0` |
| **Boot Partition (`U-Boot`)** | `/dev/mmcblk2p1` (FAT, `/mnt` or `/run/media/boot-mmcblk2p1`) | Loads `imx7d-pico-pi.dtb` when `wifi_module=brcm` is set in `uEnv.txt` |

---

## 2. Deployed Files & Services

- **Firmware (`/lib/firmware/brcm/`)**:
  - `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, `BCM4335C0.hcd`, and fallback `imx7d-pico-pi-brcm.dtb`
- **Modprobe Configuration**:
  - `/etc/modprobe.d/brcmfmac.conf` (`blacklist bcmdhd`, `options brcmfmac feature_disable=0x82000`)
- **Boot Partition CLI Updater**:
  - `/usr/local/sbin/wifi-bcm4339-update-boot.py` (`--boot-partition`, `--mount-point`, `--wifi-module`, `--fallback-dtb`)
- **Bluetooth Systemd Service & Reset Helper**:
  - `/usr/local/sbin/brcm-bt-reset.sh` (power-cycles `bt_rfkill` `GPIO4_IO17` and pulses `GPIO4_IO18` `BT_RST_N` so `BCM4335C0` cleanly enters its `115,200` baud ROM bootloader on both cold boot and service restarts)
  - `/etc/systemd/system/brcm-bluetooth.service`

---

## 3. Verifying & Controlling WiFi (`wlan0`) and Bluetooth (`hci0`)

```bash
# Confirm WiFi driver loaded and wlan0 interface is up
ip link show wlan0
iw dev
dmesg | grep brcmfmac

# Confirm Bluetooth HCI interface (hci0) is UP RUNNING
hciconfig -a
systemctl status brcm-bluetooth.service
```

---

## 4. Deep-Dive & Reproduction Guide

- [wifi_config_yocto.md](./wifi_config_yocto.md) — Regulatory domain (`IT`), `feature_disable=0x82000`, and persistent ConnMan WiFi configuration on TechNexion Yocto (`6.18-wrynose`).
