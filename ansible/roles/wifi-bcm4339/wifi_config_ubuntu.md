# Persistent Wi-Fi & Dual-Homed Setup on TechNexion Ubuntu 22.04 (`5.15.71`)

Reference and reproduction guide for bringing up the **Broadcom BCM4339 (AMPAK AP6335)** SDIO Wi-Fi controller (`wlan0`) and dual-homed **Ethernet + Wi-Fi** routing on **TechNexion PICO-PI-IMX7D** running **Ubuntu 22.04 LTS (Linux kernel `5.15.71`)**.

---

## 1. Root Cause of Early-Boot Hang When Replacing `.dtb` on Kernel `5.15.71`

1. **Stock Boot Partition Layout (`/dev/mmcblk2p1`)**:
   - TechNexion's Ubuntu 22.04 image (`5.15.71`) ships `imx7d-pico-pi-qca.dtb`, `uEnv.txt` (`wifi_module=qca`), `u-boot.img`, and `zImage` on `/dev/mmcblk2p1`.
   - Even with `wifi_module=qca`, `imx7d-pico-pi-qca.dtb` **already** powers on `wlreg_on` (`GPIO4_IO16`), `wifi_pwr_on` (`GPIO2_IO29`), muxes `GPIO1_IO03` to `CCM_CLKO2` (`ALT5`, `0x302c000c = 0x5`), and enumerates the Broadcom BCM4339 card on SDIO (`mmc1:0001:1`, `SDIO_ID=02D0:4335`).
2. **Why Custom `imx7d-pico-pi-brcm.dtb` Bricked Kernel `5.15.71`**:
   - Adding `assigned-clocks = <&clks IMX7D_CLKO2_ROOT_SRC>, <&clks IMX7D_CLKO2_ROOT_DIV>` and `assigned-clock-parents = <&clks IMX7D_CKIL>` directly onto the root `clock-controller@30380000` (`fsl,imx7d-ccm`) node works on mainline Kernel `6.18` (where `clk-imx7d` is a platform driver), **but hangs NXP's downstream `5.15.71` `CLK_OF_DECLARE` (`imx7d_clocks_init`) during early kernel boot** on every warm or cold boot.
3. **Why `brcmfmac.ko` Needed `CCM_CLKO2` (`32.768 kHz`)**:
   - Without the `32.768 kHz` LPO sleep clock on `CCM_CLKO2`, `brcmfmac.ko` loads cleanly without crashing the kernel, but BCM4339 firmware initialization times out with:
     ```text
     brcmfmac: brcmf_sdio_htclk: HT Avail timeout (1000000): clkctl 0x50
     ```
   - Enabling `CCM_TARGET_ROOT127` (`CLKO2_CLK_ROOT` at physical address `0x3038be00`: `MUX=7` -> `ckil` `32.768 kHz`, `ENABLE=1` -> `0x17000000`) immediately before loading `brcmfmac.ko` brings up `wlan0` cleanly **without modifying `/dev/mmcblk2p1` (`uEnv.txt` or `.dtb`) at all**, making bootloader/kernel-boot hangs impossible.

---

## 2. Step-by-Step Manual Reproduction on Target Hardware

### Step 1: Verify Kernel & SDIO Enumeration (`02D0:4335`)

```bash
uname -r
# Expected: 5.15.71

cat /sys/bus/sdio/devices/mmc1:0001:1/uevent
# Expected:
# SDIO_CLASS=00
# SDIO_ID=02D0:4335
# MODALIAS=sdio:c00v02D0d4335
```

> **Important**: Leave `/dev/mmcblk2p1` (`imx7d-pico-pi-qca.dtb` and `uEnv.txt`) completely unmodified on Kernel `5.15.71`.

---

### Step 2: Install Out-of-Tree `brcmutil.ko` & `brcmfmac.ko` + Firmware

Copy the `5.15.71` kernel modules and firmware files from `ansible/roles/wifi-bcm4339/files/`:

```bash
sudo mkdir -p /lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/{brcmfmac,brcmutil}
sudo mkdir -p /lib/firmware/brcm /usr/local/sbin

sudo cp brcmutil.ko /lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/brcmutil/
sudo cp brcmfmac.ko /lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/
sudo cp cyfmac4339-sdio.bin /lib/firmware/brcm/brcmfmac4339-sdio.bin
sudo cp brcmfmac4339-sdio.txt /lib/firmware/brcm/brcmfmac4339-sdio.txt
sudo chmod 0644 \
  /lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/brcmutil/brcmutil.ko \
  /lib/modules/5.15.71/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko \
  /lib/firmware/brcm/brcmfmac4339-sdio.bin \
  /lib/firmware/brcm/brcmfmac4339-sdio.txt

sudo depmod -a 5.15.71
```

---

### Step 3: Install `CCM_CLKO2` (`32.768 kHz`) Helper & `modprobe` Hook

1. Install `ansible/roles/wifi-bcm4339/files/brcm-clko2-enable.py` to `/usr/local/sbin/brcm-clko2-enable.py` (`chmod 0755`), which maps `0x3038b000` via `/dev/mem` and sets `0x3038be00` (`CCM_TARGET_ROOT127`) to `0x07000000` (`MUX=7`, `ckil` while gated) then `0x17000000` (`ENABLE=1`), waiting `50ms` for clock stabilization.
2. Create `/etc/modprobe.d/brcmfmac.conf`:
   ```ini
   # Prevent legacy bcmdhd driver from conflicting on SDIO
   blacklist bcmdhd
   # Enable 32.768 kHz CCM_CLKO2 reference clock before loading brcmfmac on 5.x
   install brcmfmac /usr/local/sbin/brcm-clko2-enable.py && /sbin/modprobe --ignore-install brcmfmac $CMDLINE_OPTS
   # Disable firmware WPA/SAE offload so wpa_supplicant handles handshakes in user space
   options brcmfmac feature_disable=0x82000
   ```
3. Load `brcmfmac` and verify `wlan0` comes up and scans:
   ```bash
   sudo modprobe brcmfmac
   dmesg | grep brcmfmac
   # Expected: Firmware: BCM4339/2 wl0: Sep  5 2019 11:05:52 version 6.37.39.113 (r722271 CY)

   ip link show wlan0
   sudo nmcli dev wifi list ifname wlan0
   ```

Because `systemd-udevd` automatically matches `MODALIAS=sdio:c00v02D0d4335` at boot and invokes `modprobe`, the `install brcmfmac` rule enables `CCM_CLKO2` and brings up `wlan0` automatically on every warm or cold boot.

---

### Step 4: Persistent Wi-Fi Profile & Dual-Homed Source Policy Routing (`eth0` + `wlan0`)

When `eth0` and `wlan0` are connected to **different subnets/VLANs** at the same time (`eth0` holding the lower-metric default route in the `main` table), inbound connections to `<WIFI_IP>` from other subnets require **source-based policy routing** so replies leave via `wlan0`'s gateway instead of `eth0`'s gateway:

1. Connect and persist the NetworkManager profile (`wifi-home-conf` role):
   ```bash
   sudo nmcli dev wifi connect "<WIFI_SSID>" password "<WIFI_PASSWORD>" ifname wlan0 name "<WIFI_SSID>-profile"
   sudo nmcli connection modify "<WIFI_SSID>-profile" connection.autoconnect yes ipv4.route-metric 600
   ```
2. Deploy `/etc/NetworkManager/dispatcher.d/99-wifi-source-routing` (`chmod 0755`, `root:root`, see `ansible/roles/wifi-home-conf/templates/99-wifi-source-routing.j2`) so table `200` and `ip rule` priority `100` (`from <WIFI_IP>/32 lookup 200`) are maintained automatically on `up` and `dhcp4-change`:
   ```bash
   sudo /etc/NetworkManager/dispatcher.d/99-wifi-source-routing wlan0 up
   ip rule show
   ip route show table 200
   ```

---

## 3. Automated Reproduction via Ansible

```bash
# 1. Validate secrets.yml and SSH keys
python3 scripts/check-env.py <MACHINE_NAME>

# 2. Provision all configured roles idempotently (auto-bootstraps SSH port if fresh OS)
./scripts/run-machine.sh <MACHINE_NAME>

# 3. Verify SSH and HTTP streaming over both Ethernet and Wi-Fi IPs
ssh -p <SSH_PORT> -i ssh_keys/<KEY_NAME> <USER>@<ETH_IP> "ip -4 addr show eth0 wlan0 && iw dev wlan0 link"
ssh -p <SSH_PORT> -i ssh_keys/<KEY_NAME> <USER>@<WIFI_IP> "hostname && ustreamerctl status"
curl -fsS -u "<STREAM_USER>:<STREAM_PASSWORD>" "http://<ETH_IP>:<STREAM_PORT>/state"
curl -fsS -u "<STREAM_USER>:<STREAM_PASSWORD>" "http://<WIFI_IP>:<STREAM_PORT>/snapshot" -o /tmp/snapshot_wifi.jpg
```

---

## 4. Note on Bluetooth (`brcm-bluetooth.service`) on Kernel `5.15.71`

On Kernel `5.15.71`, `hciattach /dev/ttymxc6 bcm43xx 3000000 flow` may time out (`bcm43xx_init: Initialization timed out`) if UART7 RTS/CTS/DMA handshake is not initialized for the AP6335 BT core. On headless machines that only require Wi-Fi, set:

```yaml
wifi_bcm4339_enable_bluetooth_service: false
```

in `machines/<MACHINE_NAME>/vars.yml`.
