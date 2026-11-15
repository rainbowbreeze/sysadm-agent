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

---

## 4. Stream Stability, Root Causes of Drops & Tuning Guide

When streaming the Huddly GO over WiFi (e.g. via `stream-ustreamer` on a Raspberry Pi 3 Model B), be aware of the camera's hardware constraints and the four root causes that can trigger stream drops:

### A. Hardware Streaming Constraints (`2bd9:0011` on USB 2.0)
- **Single Fixed UVC Mode**: On USB 2.0 (`480 Mbps`), the Huddly GO exposes only one discrete format and frame interval: **`MJPG 1280x720 @ 30.000 fps`** (`0.033s`). If a lower FPS (such as `15 fps`) is requested, the camera's UVC firmware coerces the stream back to `30 fps` (`Using HW FPS: 15 -> 30 (coerced)`) and stalls V4L2 buffer delivery unless `--desired-fps=30` is passed to `ustreamer`.
- **No VPU Standby (`--slowdown` Must Be Disabled)**: When idle, the Huddly GO's Intel Movidius Myriad 2 VPU enters standby and outputs ~30–60 black warmup frames when re-opened. Set `stream_ustreamer_slowdown: false` so the VPU stays continuously active at 30 fps.
- **High Fixed Bitrate (`~24.3 Mbps` per client)**: The Huddly GO does not support V4L2 hardware JPEG quality controls (`~101 KB` per `1280x720` frame). At `30 fps`, **each connected `/stream` client consumes `~24.3 Mbps` (`~2.9 MB/s`) of continuous TCP upload**.

### B. Root Causes of Stream Drops & Implemented Mitigations

| # | Root Cause | Symptom in Logs / Diagnostics | Mitigation Implemented |
| :--- | :--- | :--- | :--- |
| **1** | **2.4 GHz WiFi Bandwidth Saturation** | Single-stream 2.4 GHz 802.11n (`72.2 Mbps` PHY on Pi 3 `BCM43430`) has a real-world TCP ceiling of ~25–32 Mbps. Opening a 2nd concurrent `/stream` client (`~48 Mbps` demand) or 2.4 GHz airtime contention stalls TCP writes until `ustreamer` drops the client (`Broken pipe` / `Bad file descriptor`). | Pass `--tcp-nodelay --server-timeout=30 --drop-same-frames=15` in `stream_ustreamer_extra_args`, avoid opening multiple concurrent `/stream` tabs (use `/snapshot` for periodic polling), and prefer Ethernet (`eth0`) or 5 GHz WiFi when available. |
| **2** | **WiFi Power Save (`brcmfmac` `power_save on`)** | `dmesg` logs `brcmf_cfg80211_set_power_mgmt: power save enabled` and `iw dev wlan0 get power_save` shows `Power save: on`, causing periodic SDIO radio sleep and TCP ACK stalls. | Automatically disabled by `camera-huddly-go` (`camera_huddly_go_disable_wifi_powersave: true`) via `/etc/udev/rules.d/99-camera-huddly-go.rules`, `/etc/NetworkManager/conf.d/99-camera-wifi-powersave.conf`, and `iw dev wlan0 set power_save off`. |
| **3** | **USB Autosuspend (`power/control=auto`)** | `/sys/bus/usb/devices/*/power/control` defaults to `auto` (`autosuspend_delay_ms=2000`) on the Huddly GO USB port. | `/etc/udev/rules.d/99-camera-huddly-go.rules` sets `ATTR{power/control}="on"` for USB device `2bd9:0011`. |
| **4** | **5V Rail Under-Voltage (`throttled=0x50000`)** | `vcgencmd get_throttled` reports `0x50000` (Bit 16 under-voltage `< 4.63V` + Bit 18 CPU throttling occurred) because the Huddly GO's Movidius VPU draws ~450–500 mA over USB during 720p30 MJPEG encoding alongside WiFi TX bursts. | **Hardware mitigation**: Power the Raspberry Pi with a dedicated **5.1V / 3.0A** power supply (using a short, thick 18–20 AWG power cable) or connect the Huddly GO through a powered USB hub. |

### C. Recommended `vars.yml` Settings for Huddly GO + `stream-ustreamer`
```yaml
stream_ustreamer_enabled: true
stream_ustreamer_video_device: "/dev/video0"
stream_ustreamer_format: "MJPEG"
stream_ustreamer_width: 1280
stream_ustreamer_height: 720
stream_ustreamer_fps: 30
stream_ustreamer_slowdown: false
stream_ustreamer_extra_args: "--persistent --buffers=4 --tcp-nodelay --server-timeout=30 --drop-same-frames=15"
```
