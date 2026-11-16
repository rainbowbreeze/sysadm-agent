# `wifi-bcm4339` — Broadcom BCM4339 (AMPAK AP6335) WiFi & Bluetooth on TechNexion PICO-PI-IMX7D

This module installs the prebuilt **Broadcom BCM4339 (AMPAK AP6335)** SDIO WiFi kernel modules (`brcmfmac.ko`, `brcmutil.ko`), WiFi/Bluetooth firmware, Bluetooth UART attach service (`brcm-bluetooth.service`), and custom Device Tree Blob (`imx7d-pico-pi-brcm.dtb` -> `/mnt/imx7d-pico-pi.dtb`) on **TechNexion PICO-PI-IMX7D** running kernel `5.15.71` (`Ubuntu 22.04`), following [carlossg/TechNexion-PICO-PI-IMX7](https://github.com/carlossg/TechNexion-PICO-PI-IMX7) (`Step 5 — Deploy to the board` through `Step 7 — Verify and connect`).

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **WiFi Controller (`AMPAK AP6335`)** | SDIO (`30b50000.mmc` / `usdhc2`) | Broadcom **BCM4339** (`02D0:4335`), interface `wlan0`, driver `brcmfmac` |
| **SDIO Reference Clock (`usdhc2_pwrseq`)** | `IMX7D_CLKO2_ROOT_DIV` (`32.768 kHz`) | Configured via `mmc-pwrseq-simple` in `imx7d-pico-pi.dtb` (`wifi_module=brcm`) |
| **Bluetooth Controller (`BCM4335C0`)** | UART7 (`/dev/ttymxc6`, `30a90000.serial`) | 3,000,000 baud RTS/CTS flow control, `bt_rfkill` power on `GPIO4_IO17` (`BT_REG_ON`), interface `hci0` |
| **Boot Partition (`U-Boot 2021.04`)** | `/dev/mmcblk2p1` (FAT, mounted at `/mnt`) | Loads `/mnt/imx7d-pico-pi.dtb` when `wifi_module=brcm` is set in `/mnt/uEnv.txt` |

---

## 2. Deployed Files & Services

- **Kernel Modules (`/lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/`)**:
  - `brcmfmac/brcmfmac.ko`: Broadcom FullMAC SDIO wireless driver built for `5.15.71 SMP preempt mod_unload modversions ARMv7 p2v8`
  - `brcmutil/brcmutil.ko`: Broadcom 802.11 utility dependency module
- **Firmware (`/lib/firmware/brcm/`)**:
  - `brcmfmac4339-sdio.bin`: BCM4339 WiFi firmware binary (copied from `dist/cyfmac4339-sdio.bin`)
  - `brcmfmac4339-sdio.txt`: BCM4339 WiFi NVRAM calibration file for TechNexion PICO boards
  - `BCM4339A0.hcd` & `BCM4335C0.hcd`: BCM4339 Bluetooth UART patchram firmware
- **Boot Partition (`/dev/mmcblk2p1` -> `/mnt`)**:
  - `/mnt/imx7d-pico-pi.dtb`: Custom DTB (`dist/imx7d-pico-pi-brcm.dtb`) with `mmc-pwrseq-simple` (`usdhc2_pwrseq`) and `bt_rfkill`
  - `/mnt/uEnv.txt`: Configures `wifi_module=brcm` so U-Boot loads `imx7d-pico-pi.dtb`
- **Systemd Service**:
  - `/etc/systemd/system/brcm-bluetooth.service`: Unblocks `bluetooth` rfkill and runs `hciattach /dev/ttymxc6 bcm43xx 3000000 flow` at boot.

---

## 3. Verifying & Controlling WiFi (`wlan0`) and Bluetooth (`hci0`)

```bash
# Confirm WiFi driver loaded and wlan0 interface is up
ip link show wlan0
iw dev
dmesg | grep brcmfmac

# Scan for available WiFi networks
sudo nmcli dev wifi list

# Connect to a WiFi network
sudo nmcli dev wifi connect "<SSID>" password "<PASSWORD>"

# Confirm Bluetooth HCI interface (hci0) is UP RUNNING
hciconfig -a
systemctl status brcm-bluetooth.service
sudo hcitool lescan
```
