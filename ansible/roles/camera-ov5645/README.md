# `camera-ov5645` — OmniVision OV5645 MIPI-CSI Camera on TechNexion PICO-PI-IMX7D (NXP i.MX7D)

This module configures a **TechNexion PICO-PI-IMX7D** (`NXP i.MX7D`) Debian/Ubuntu machine for the **OmniVision OV5645 / OV5640 MIPI-CSI Camera** and deploys the pure-Python driver and CLI (`/opt/camera/camera.py`, symlinked at `/usr/local/bin/camera`).

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

| Subsystem | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **MIPI-CSI2 Capture Pipeline** | `/dev/video1` (`30750000.mipi-csi` -> `30710000.csi1`) | NXP `mx6s-csi` V4L2 capture interface (`UYVY` raw frames) |
| **OmniVision OV5645 Sensor (I2C)** | `/dev/i2c-3` (`30a50000.i2c`) | I2C Slave Address **`0x3c`** (Chip ID `0x5645`, kernel driver `ov5645_camera_mipi_int`) |
| **Master Clock (MCLK)** | `CCM_CLKO1` (`GPIO1_IO02`) | **24 MHz** clock at register `0x3038bd80` (`0x10000000`) |
| **Camera Power Down (`CAM_PWDN`)** | `GPIO1_IO04` (`gpio4`) | Active-high power-down line (kept unexported in sysfs so kernel driver binds cleanly) |
| **Camera Reset (`CAM_RST`)** | `GPIO1_IO05` (`gpio5`) | Active-low hardware reset line (kept unexported in sysfs so kernel driver binds cleanly) |
| **Supported Hardware Resolutions** | `1280x960`, `1920x1080`, `2592x1944` | 4:3 HD (`1280x960`), 1080p Full HD (`1920x1080`), Full 5MP (`2592x1944`) |

---

## 2. Deployed Files & Services

- **`/opt/camera/camera.py`**: Zero-dependency pure-Python library and CLI using Linux `i2c-dev` (`fcntl.ioctl`), `v4l2-ctl`, and GStreamer (`gst-launch-1.0`) with automatic AEC/AWB warm-up frame streaming and orientation correction.
- **`/opt/camera/camera.sh` & `/usr/local/bin/camera`**: Wrapper script that activates `/opt/camera/venv`, exports default capture settings, and invokes `/opt/camera/camera.py`.
- **`/etc/udev/rules.d/99-camera.rules`**: Grants `0660` group permissions (`{{ ansible_user }}`) on `/dev/video*`, `/dev/v4l-subdev*`, `/dev/media*`, and `/dev/i2c-3`.
- **`/usr/local/sbin/camera-init.sh` & `camera-init.service`**: Boot-time systemd oneshot service that enables the 24MHz `CCM_CLKO1` master clock (`busybox devmem 0x3038bd80 32 0x10000000`), sets device permissions, frees `gpio4`/`gpio5` for kernel binding, and re-probes `ov5645_camera_mipi_int`.

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
# Capture a default 1920x1080 JPEG snapshot (15 warmup frames, 180° rotation, 95% quality)
camera capture /tmp/photo.jpg

# Capture a full 5MP (2592x1944) snapshot with custom warmup frames and quality
camera capture /tmp/photo_5mp.jpg --width 2592 --height 1944 --warmup 20 --quality 98

# Capture a 1280x960 snapshot without rotation
camera capture /tmp/photo_raw_orient.jpg --width 1280 --height 960 --rotate 0

# Capture with an auto-generated timestamp filename in /tmp/camera_snapshot_<timestamp>.jpg
camera snapshot
```

---

## 4. Controlling the Camera from Python

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

# 2. Capture a 1920x1080 JPEG snapshot
ok = capture_snapshot(
    output_file="/tmp/snapshot.jpg",
    width=1920,
    height=1080,
    warmup_frames=15,
    rotate=180,
    quality=95,
)
print("Capture succeeded:", ok)
```
