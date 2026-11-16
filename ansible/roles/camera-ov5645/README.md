# `camera-ov5645` — OmniVision OV5645 MIPI-CSI Camera on TechNexion PICO-PI-IMX7D (NXP i.MX7D)

This module configures a **TechNexion PICO-PI-IMX7D** (`NXP i.MX7D`) machine running **Debian/Ubuntu** (Kernel `5.x`) or **TechNexion Yocto (`TechNexion i.MX Release Distro`)** (Kernel `6.x`) for the **OmniVision OV5645 / OV5640 MIPI-CSI Camera** and deploys the pure-Python driver and CLI (`/opt/camera/camera.py`, symlinked at `/usr/local/bin/camera`).

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **MIPI-CSI2 Capture Pipeline** | `/dev/video1` (`30750000.mipi-csi` -> `30710000.csi1`) | NXP `mx6s-csi` V4L2 capture interface (`UYVY` raw frames) |
| **OmniVision OV5645 Sensor (I2C)** | `/dev/i2c-3` (`30a50000.i2c`) | I2C Slave Address **`0x3c`** (Chip ID `0x5645`, kernel driver `ov5645_camera_mipi_int` on `5.x` or `ov5645` on `6.x`) |
| **Camera Core Regulator (`DVDD`)** | `VLDO2` on `pfuze3000@8` (`/dev/i2c-3` `0x08` reg `0x6d`) | **1.50V** core supply (`regulator-always-on` in DTB) |
| **Master Clock (MCLK)** | `CCM_CLKO1` (`GPIO1_IO02`) | **24 MHz** clock (`IMX7D_CLKO1_ROOT_DIV` = `340`) at register `0x3038bd80` (`0x10000000`) |
| **Camera Power / Enable (`GPIO4`)** | `GPIO1_IO04` (`gpio4`) | Active-high enable / power-down control line (kept unexported in sysfs so kernel driver binds cleanly) |
| **Camera Reset (`CAM_RST`)** | `GPIO1_IO05` (`gpio5`) | Active-low hardware reset line (kept unexported in sysfs so kernel driver binds cleanly) |
| **Supported Hardware Resolutions** | `1280x960`, `1920x1080`, `2592x1944` | 4:3 HD (`1280x960`), 1080p Full HD (`1920x1080`), Full 5MP (`2592x1944`) |

---

## 2. Deployed Files & Services

- **`/opt/camera/camera.py`**: Zero-dependency pure-Python library and CLI using Linux `i2c-dev` (`fcntl.ioctl`), `v4l2-ctl`, and GStreamer (`gst-launch-1.0`) with automatic AEC/AWB warm-up frame streaming and orientation correction.
- **`/opt/camera/camera.sh` & `/usr/local/bin/camera`**: Wrapper script that activates `/opt/camera/venv` (when present), exports default capture settings, and invokes `/opt/camera/camera.py`.
- **`/etc/udev/rules.d/99-camera.rules`**: Grants `0660` group permissions (`{{ ansible_user }}`) on `/dev/video*`, `/dev/v4l-subdev*`, `/dev/media*`, and `/dev/i2c-3`.
- **`/usr/local/sbin/camera-ov5645-update-dtb.py`**: Pure-Python Flattened Device Tree (FDT) binary updater (no `dtc` dependency) that patches `imx7d-pico-pi.dtb` on `/dev/mmcblk2p1` (and `/lib/firmware/brcm/imx7d-pico-pi-brcm.dtb` when present) for either Kernel `5.x` (`ovti,ov5645_mipi`) or Kernel `6.x` (`ovti,ov5645`, `vldo2` `1.50V` `regulator-always-on`, `clocks = <&clks 340>`, `enable-gpios`, `reset-gpios`, and `data-lanes = <1 2>`).
- **`/usr/local/sbin/camera-init.sh` & `camera-init.service`**: Boot-time systemd oneshot service that enables the 24MHz `CCM_CLKO1` master clock (`0x3038bd80 = 0x10000000`), frees `gpio4`/`gpio5` for kernel binding, binds `ov5645` (`6.x`) or `ov5645_camera_mipi_int` (`5.x`) to I2C `3-003c` if not yet bound, and sets device permissions.

---

## 3. Controlling the Camera via CLI (`camera`)

All commands run directly as the configured SSH user (no `sudo` required):

### Hardware Status & Diagnostics
```bash
# Query sensor model, I2C address, V4L2 device/formats, and 24MHz MCLK status
camera status

# Output hardware status as structured JSON
camera status --json

# Run a 4-step diagnostic check (V4L2 nodes, MCLK register, i2cdetect bus 3, sensor probe)
camera detect
```

### Capturing JPEG Snapshots (`capture` / `snapshot`)
```bash
# Capture a default 1280x960 JPEG snapshot (15 warmup frames, 180° rotation, 95% quality)
camera capture /tmp/photo.jpg

# Capture with a custom rotation angle (--rotation, --rotate, or -r: 0, 90, 180, 270)
camera capture /tmp/photo_portrait.jpg --rotation 90

# Capture a 1920x1080 (16:9) snapshot (automatically uses full-array 5MP -> 1080p crop/scale on Kernel 6.x)
camera capture /tmp/photo_1080p.jpg --width 1920 --height 1080

# Capture a full 5MP (2592x1944) snapshot with custom warmup frames and quality
camera capture /tmp/photo_5mp.jpg --width 2592 --height 1944 --warmup 20 --quality 98

# Capture with an auto-generated timestamp filename in /tmp/camera_snapshot_<timestamp>.jpg
camera snapshot
```

---

## 4. Configuring Orientation & Resolution Options in Ansible (`vars.yml`)

### Customizing Default Image Orientation (`camera_ov5645_rotation`)
Set `camera_ov5645_rotation` (`0`, `90`, `180`, or `270`) in `machines/<MACHINE_NAME>/vars.yml` and re-run role provisioning (`--tags camera-ov5645`) to change the persistent default orientation used by `/usr/local/bin/camera` (and `/usr/local/bin/camera-booth`):

```yaml
camera_ov5645_rotation: 90   # Allowed values: 0, 90, 180, 270 (default: 180)
```

### Switching Between Color-Accurate Capture Options (Kernel `6.x` Mainline `ov5645.ko`)
On Kernel `6.x`, mainline `ov5645.ko`'s stock `1920x1080` register table center-crops the sensor (`X_ADDR_START = 0x0150`), skipping the horizontal Optical Black reference columns (`X = 0..15`) and causing a strong green Black Level Calibration (BLC) cast. Three clean options are supported (full hardware & register details in `camera_config_yocto.md`):

1. **Option 1 — Active Default (`1280x960` Native `SXGA` `2×2` Binned)**:
   - Best indoor low-light sensitivity (`4×` analog binning), dead-neutral blacks, full wide FOV, fast `30 fps` warmup.
   - Default in `defaults/main.yml`:
     ```yaml
     camera_ov5645_default_width: 1280
     camera_ov5645_default_height: 960
     ```
2. **Option 2 — `1920x1080` (`16:9`) via Full-Array `2592x1944` Capture + GStreamer Crop/Downscale**:
   - Already built into `camera.py`: setting the default resolution to `1920x1080` in `vars.yml` automatically captures from clean full-width `2592x1944` (`X_ADDR_START = 0x0000`) and crops/downscales `2592x1458` $\rightarrow$ `1920x1080` in GStreamer:
     ```yaml
     camera_ov5645_default_width: 1920
     camera_ov5645_default_height: 1080
     camera_ov5645_native_1080p: false
     ```
3. **Option 3 — Native `1920x1080` via Patched `ov5645.ko` Hardware ISP Scaler**:
   - Patch `ov5645_setting_1080p` in `ov5645.ko` using the register table and procedure in `camera_config_yocto.md` (Section 5), then enable native `1080p` in `vars.yml`:
     ```yaml
     camera_ov5645_default_width: 1920
     camera_ov5645_default_height: 1080
     camera_ov5645_native_1080p: true
     ```

---

## 5. Controlling the Camera from Python

You can also import the camera functions directly from `/opt/camera/camera.py`:

```python
import sys
sys.path.insert(0, "/opt/camera")

from camera import (
    capture_snapshot,
    check_clko1_status,
    get_v4l2_status,
    probe_i2c_sensor,
)

# 1. Inspect sensor and V4L2 status
sensor = probe_i2c_sensor()
v4l2 = get_v4l2_status()
mclk = check_clko1_status()
print(f"Sensor: {sensor['model']} ({sensor['chip_id']}) on {v4l2['device']}, MCLK={mclk['frequency_hz']} Hz")

# 2. Capture a 1280x960 JPEG snapshot with custom rotation
ok = capture_snapshot(
    output_file="/tmp/snapshot.jpg",
    width=1280,
    height=960,
    warmup_frames=15,
    rotation=180,
    quality=95,
)
print("Capture succeeded:", ok)
```
