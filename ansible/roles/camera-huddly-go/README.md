# `camera-huddly-go` — Huddly GO Wide-Angle USB Camera Module

This module configures a Debian/Ubuntu machine (such as a Raspberry Pi) for the **Huddly GO** wide-angle USB conference camera (`2bd9:0011`) and deploys the zero-dependency Python driver and CLI (`/opt/camera/camera.py`, symlinked at `/usr/local/bin/camera`).

It can be used standalone or combined with the **`stream-ustreamer`** module (`ansible/roles/stream-ustreamer/`) for continuous HTTP MJPEG streaming and instant snapshots in Home Assistant.

---

## 1. Hardware Mapping & Characteristics

| Subsystem | Device / Identifier | Details |
| :--- | :--- | :--- |
| **USB Vendor / Product ID** | `2bd9:0011` (`Huddly GO`) | USB Video Class (UVC) camera with onboard Intel Movidius Myriad 2 VPU/ISP |
| **Kernel Driver** | `uvcvideo` | Standard Linux UVC driver |
| **V4L2 Video Capture Node** | `/dev/video0` (auto-resolved) | Hardware-encoded `MJPG` (Motion-JPEG) stream at **`1280x720` @ `30.000 fps`** |
| **V4L2 Metadata Node** | `/dev/video1` | UVC metadata stream |
| **VPU/ISP Standby Warmup** | `90` frames (`~3.0s`) | When waking from standby, the VPU outputs black frames (`~19 KB`) for ~1–2s (~30–60 frames) while initializing auto-exposure |
| **Hardware Digital PTZ** | `zoom_absolute`, `pan_absolute`, `tilt_absolute` | Zoom `1000..4000` (`1x..4x`), Pan `-216000..216000`, Tilt `-162000..162000` |
| **Image Controls** | `brightness`, `gain`, `saturation`, `sharpness` | Brightness `-600..600`, Gain `100..1200`, Saturation `1..255`, Sharpness `0..255` |

---

## 2. Deployed Files & Configuration

- **`/opt/camera/camera.py`**: Pure-Python library and CLI that auto-discovers the Huddly GO V4L2 capture node, queries USB/V4L2 state, controls hardware digital PTZ and exposure settings, and captures `1280x720` MJPEG snapshots (automatically using `stream-ustreamer` in `<20 ms` when `camera-ustreamer.service` is active, or direct `v4l2-ctl` with warmup frame skipping when stopped).
- **`/opt/camera/camera.sh` & `/usr/local/bin/camera`**: Wrapper script that activates `/opt/camera/venv`, optionally loads `/opt/ustreamer/ustreamer.env` if `stream-ustreamer` is installed, exports default capture settings, and invokes `/opt/camera/camera.py`.
- **`/etc/udev/rules.d/99-camera-huddly-go.rules`**: Grants `0660` group permissions (`{{ ansible_user }}`) on Huddly GO (`2bd9:0011`) `video4linux`, `media`, and `usb` device nodes.

---

## 3. Controlling the Camera via CLI (`camera`)

All commands run directly as the configured SSH user (no `sudo` required):

### Hardware Status & Diagnostics
```bash
# Query USB connection, serial number, V4L2 device/formats, and PTZ/image controls
camera status

# Output status as structured JSON
camera status --json

# Run a 3-step diagnostic check (lsusb, v4l2-ctl --list-devices, and full status report)
camera detect
```

### Capturing JPEG Snapshots (`capture` / `snapshot`)
```bash
# Capture a 1280x720 JPEG snapshot (instant via uStreamer when active, or 90 warmup frames via V4L2)
camera capture /tmp/photo.jpg

# Capture with digital zoom (e.g. 2x = 2000) and 180° lossless rotation
camera capture /tmp/photo_zoomed.jpg --zoom 2000 --rotate 180

# Capture with an auto-generated timestamp filename in /tmp/camera_snapshot_<timestamp>.jpg
camera snapshot
```

### Digital Pan / Tilt / Zoom & Image Controls (`ptz`)
```bash
# View current PTZ and image control values
camera ptz

# Set 2x digital zoom and pan slightly right
camera ptz --zoom 2000 --pan 36000 --tilt 0

# Reset all PTZ and image controls to factory defaults (zoom=1000, pan=0, tilt=0, brightness=0, gain=100)
camera ptz --reset
```
