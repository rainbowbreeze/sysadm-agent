# `wifi-bcm4339` — Broadcom BCM4339 (AMPAK AP6335) WiFi & Bluetooth on TechNexion PICO-PI-IMX7D

This module configures the **Broadcom BCM4339 (AMPAK AP6335)** SDIO WiFi (`wlan0`) and UART Bluetooth (`hci0`) controller on **TechNexion PICO-PI-IMX7D** across both **Kernel `5.x` (`5.15.71`, Ubuntu 22.04)** and **Kernel `6.x` (`6.18.x`, TechNexion Yocto / Debian)**, installing only what is needed on each system:
- **Kernel Modules (`brcmfmac.ko`, `brcmutil.ko`)**: Installed only on `5.15.71` where the base kernel lacks in-tree `brcmfmac`; skipped automatically on `6.x` where `brcmfmac` is built-in.
- **Firmware (`/lib/firmware/brcm/`)**: Installs `brcmfmac4339-sdio.bin`, `brcmfmac4339-sdio.txt`, and `BCM4335C0.hcd`.
- **32.768 kHz Reference Clock (`CCM_CLKO2`)**:
  - **Kernel `5.x` (`5.15.71`)**: Stock `imx7d-pico-pi-qca.dtb` already enumerates BCM4339 on SDIO (`mmc1:0001:1`), `wlreg_on`, `wifi_pwr_on`, `bt_rfkill`, and `/dev/ttymxc6`, while adding `assigned-clocks` to `clock-controller@30380000` in DTB hangs NXP downstream `lf-5.15.71` during `CLK_OF_DECLARE` early boot. Therefore on `5.x`, `/dev/mmcblk2p1` (`uEnv.txt` and `.dtb`) is left **completely untouched** and `/usr/local/sbin/brcm-clko2-enable.py` enables `CCM_CLKO2` (`0x3038be00` -> `MUX=7` `ckil` `32.768 kHz`, `ENABLE=1`) automatically via an `install brcmfmac` modprobe hook on every boot and `modprobe` call (no reboot required).
  - **Kernel `6.x` (`6.18.x`)**: Patches `imx7d-pico-pi.dtb` in-place via `/usr/local/sbin/wifi-bcm4339-update-boot.py` to configure `usdhc2_pwrseq` (`mmc-pwrseq-simple`) and `rfkill-gpio`, and updates `wifi_module=brcm` in-place inside `uEnv.txt`.
- **Bluetooth Service (`brcm-bluetooth.service`)**: Installs `/usr/local/sbin/brcm-bt-reset.sh` (`ExecStartPre`) and enables `brcm-bluetooth.service` (`TimeoutStartSec=25`), pulsing AP6335 BT reset (`GPIO4_IO18` / `gpio114`) after `CCM_CLKO2` (`32.768 kHz`) is active and verifying `/sys/class/bluetooth/hci0` on both `5.x` and `6.x` (while stopping and masking conflicting `serial-btattach@ttymxc6.{timer,service}` units when present on `6.x`).

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **WiFi Controller (`AMPAK AP6335`)** | SDIO (`30b50000.mmc` / `usdhc2`) | Broadcom **BCM4339** (`02D0:4335`), interface `wlan0`, driver `brcmfmac` |
| **SDIO Reference Clock (`usdhc2_pwrseq`)** | `IMX7D_CLKO2_ROOT_DIV` (`32.768 kHz`) | Configured via `mmc-pwrseq-simple` in `imx7d-pico-pi.dtb` (`wifi_module=brcm`) |
| **Bluetooth Controller (`BCM4335C0`)** | UART7 (`/dev/ttymxc6`, `30a90000.serial`) | 3,000,000 baud RTS/CTS flow control, `bt_rfkill` (`GPIO4_IO17` / `gpio113`) + AP6335 BT reset (`GPIO4_IO18` / `gpio114`), interface `hci0` |
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
- **Modprobe Configuration (`/etc/modprobe.d/brcmfmac.conf`)**:
  - Blacklists legacy `bcmdhd` (`blacklist bcmdhd`) so it never clashes with `brcmfmac` on SDIO, and sets `options brcmfmac feature_disable=0x82000` (disabling `FWSUP` `0x2000` and `SAE` `0x80000` firmware offload so `wpa_supplicant` handles WPA2-PSK/WPA3 handshakes in user space).
- **Boot Partition (`/dev/mmcblk2p1`, managed by `/usr/local/sbin/wifi-bcm4339-update-boot.py`)**:
  - `imx7d-pico-pi.dtb` (`imx7d-pico-pi.dtb.orig` backup saved): Patches the board's native `imx7d-pico-pi.dtb` in-place via pure-Python FDT to configure `usdhc2_pwrseq` (`mmc-pwrseq-simple`, `32.768 kHz` `CLKO2`) and `mmc-pwrseq` on `mmc@30b50000` (plus `rfkill-gpio` on `6.x`), falling back to staged `/lib/firmware/brcm/imx7d-pico-pi-brcm.dtb` only if native `imx7d-pico-pi.dtb` is missing.
  - `uEnv.txt` (`uEnv.txt.orig` backup saved): Updates `wifi_module=brcm` in-place without clobbering existing `mmcroot`, `uenvcmd`, `bootcmd_mmc`, or `boot.scr` settings.
- **Systemd Service**:
  - `/etc/systemd/system/brcm-bluetooth.service` + `/usr/local/sbin/brcm-bt-reset.sh`: Ensures `CCM_CLKO2` (`32.768 kHz`) is active, unblocks `bluetooth` rfkill (`gpio113`), pulses `GPIO4_IO18` (`gpio114`) `0 -> 1` so BCM4335C0 cleanly enters its 115200-baud ROM state, and runs `hciattach /dev/ttymxc6 bcm43xx 3000000 flow` at boot (masks `serial-btattach@ttymxc6.{timer,service}` on `6.x` if present).

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

---

## 4. OS-Specific Deep-Dive & Reproduction Guides

- **Ubuntu 22.04 (`5.15.71`)**: [wifi_config_ubuntu.md](./wifi_config_ubuntu.md) — Root-cause analysis of the `5.15.71` `CLK_OF_DECLARE` DTB boot hang, `CCM_CLKO2` (`32.768 kHz`) bring-up, Bluetooth `GPIO4_IO18` (`gpio114`) hardware reset sequence (`BCM4335C0.hcd` @ 3,000,000 baud), and dual-homed (`eth0` + `wlan0`) source policy routing reproduction steps.
- **TechNexion Yocto (`6.18-wrynose`)**: [wifi_config_yocto.md](./wifi_config_yocto.md) — Regulatory domain (`IT`), `feature_disable=0x82000`, and persistent ConnMan configuration on Kernel `6.x`.
