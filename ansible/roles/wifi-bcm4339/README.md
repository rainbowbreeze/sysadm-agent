# `wifi-bcm4339` — Broadcom BCM4339 (AMPAK AP6335) WiFi & Bluetooth on TechNexion PICO-PI-IMX7D

This module configures the **Broadcom BCM4339 (AMPAK AP6335)** SDIO WiFi (`wlan0`) and UART Bluetooth (`hci0`) controller on **TechNexion PICO-PI-IMX7D** across both **Kernel `5.x` (`5.15.71`, Ubuntu 22.04)** and **Kernel `6.x` (`6.18.x`, TechNexion Yocto / Debian)**, installing only what is needed on each system:
- **Kernel Modules (`brcmfmac.ko`, `brcmutil.ko`)**: Installed only on `5.15.71` where the base kernel lacks in-tree `brcmfmac`; skipped automatically on `6.x` where `brcmfmac` is built-in.
- **Firmware (`/lib/firmware/brcm/`)**: Installs `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, and `BCM4335C0.hcd`.
- **Device Tree (`imx7d-pico-pi.dtb`)**: Automatically selects `imx7d-pico-pi-brcm.dtb` on `5.x` (`net,rfkill-gpio`) or `imx7d-pico-pi-brcm-6.18.dtb` on `6.x` (`rfkill-gpio`), both adding `usdhc2_pwrseq` (`mmc-pwrseq-simple`) for the `32.768 kHz` external reference clock.
- **Bluetooth Service (`brcm-bluetooth.service`)**: Installs and enables `brcm-bluetooth.service` on both `5.x` and `6.x`, automatically stopping and masking the conflicting `serial-btattach@ttymxc6.{timer,service}` unit when present on `6.x`.

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **WiFi Controller (`AMPAK AP6335`)** | SDIO (`30b50000.mmc` / `usdhc2`) | Broadcom **BCM4339** (`02D0:4335`), interface `wlan0`, driver `brcmfmac` |
| **SDIO Reference Clock (`usdhc2_pwrseq`)** | `IMX7D_CLKO2_ROOT_DIV` (`32.768 kHz`) | Configured via `mmc-pwrseq-simple` in `imx7d-pico-pi.dtb` (`wifi_module=brcm`) |
| **Bluetooth Controller (`BCM4335C0`)** | UART7 (`/dev/ttymxc6`, `30a90000.serial`) | 3,000,000 baud RTS/CTS flow control, `bt_rfkill` power on `GPIO4_IO17` (`BT_REG_ON`), interface `hci0` |
| **Boot Partition (`U-Boot`)** | `/dev/mmcblk2p1` (FAT, `/mnt` or `/run/media/boot-mmcblk2p1`) | Loads `imx7d-pico-pi.dtb` when `wifi_module=brcm` is set in `uEnv.txt` |

---

## 2. Deployed Files & Services

- **Kernel Modules (`/lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/`, `5.15.71` only)**:
  - `brcmfmac/brcmfmac.ko`: Broadcom FullMAC SDIO wireless driver built for `5.15.71 SMP preempt mod_unload modversions ARMv7 p2v8`
  - `brcmutil/brcmutil.ko`: Broadcom 802.11 utility dependency module
- **Firmware (`/lib/firmware/brcm/`)**:
  - `brcmfmac4339-sdio.bin`: BCM4339 WiFi firmware binary (copied from `cyfmac4339-sdio.bin`)
  - `brcmfmac4339-sdio.txt`: BCM4339 WiFi NVRAM calibration file for TechNexion PICO boards
  - `BCM4335C0.hcd`: BCM4339 (`BCM4335C0`) Bluetooth 4.1 UART patchram firmware (`Revision: 0x242`)
- **Boot Partition (`/dev/mmcblk2p1`)**:
  - `imx7d-pico-pi.dtb`: Kernel-matched DTB (`imx7d-pico-pi-brcm.dtb` for `5.x`, `imx7d-pico-pi-brcm-6.18.dtb` for `6.x`) with `mmc-pwrseq-simple` (`usdhc2_pwrseq`) and `bt_rfkill`
  - `uEnv.txt`: Configures `wifi_module=brcm` so U-Boot loads `imx7d-pico-pi.dtb`
- **Systemd Service**:
  - `/etc/systemd/system/brcm-bluetooth.service`: Unblocks `bluetooth` rfkill and runs `hciattach /dev/ttymxc6 bcm43xx 3000000 flow` at boot (masks `serial-btattach@ttymxc6.{timer,service}` on `6.x` if present).

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
