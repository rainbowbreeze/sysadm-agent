# `stream-ustreamer` — Composable uStreamer HTTP MJPEG & Snapshot Module

This module installs and configures **`uStreamer`** (`pikvm/ustreamer`) as a standalone composable streaming service (`camera-ustreamer.service`) and CLI (`/usr/local/bin/ustreamerctl`).

It can be combined with **any V4L2 camera module** (`camera-huddly-go`, `camera-ov5645`, or any USB/CSI V4L2 camera) to expose lightweight HTTP MJPEG live streams (`/stream`) and instant JPEG snapshots (`/snapshot`) for **Home Assistant**, and can be enabled or disabled on demand via Ansible or CLI.

---

## 1. Architecture & Camera Compatibility

| Setting | Default | Notes |
| :--- | :--- | :--- |
| **Systemd Service** | `camera-ustreamer.service` | Controlled via Ansible (`stream_ustreamer_enabled`) or `ustreamerctl` |
| **Config & Secrets File** | `/opt/ustreamer/ustreamer.env` (`0600`) | Shared with camera CLIs (`/usr/local/bin/camera`) for seamless snapshot integration |
| **V4L2 Device (`stream_ustreamer_video_device`)** | `/dev/video0` | E.g. `/dev/video0` for Huddly GO USB camera, `/dev/video1` for OV5645 MIPI-CSI |
| **Input Format (`stream_ustreamer_format`)** | `MJPEG` | Use `MJPEG` for hardware-MJPEG cameras (Huddly GO, <1% CPU), or `UYVY`/`YUYV` for raw sensors |
| **Idle Warmup (`stream_ustreamer_slowdown`)** | `true` (`--slowdown`) | Keeps camera VPU/ISP warm at 1 FPS when no clients are connected so `/snapshot` responds in `<20 ms` |
| **HTTP Basic Auth** | Optional (`stream_ustreamer_user` / `_password`) | Protects `/stream`, `/snapshot`, and `/state` endpoints |

---

## 2. Enabling / Disabling On Demand

### Option A: Via CLI on the Target Machine (`ustreamerctl`)
No `sudo` password is required for the configured SSH user:
```bash
# Inspect service state, V4L2 source, FPS, and endpoints
ustreamerctl status
ustreamerctl status --json

# Temporarily stop or start streaming (stopping releases /dev/video* immediately)
ustreamerctl stop
ustreamerctl start
ustreamerctl restart

# Permanently enable or disable streaming across reboots
ustreamerctl disable
ustreamerctl enable

# Grab an instant JPEG snapshot from the running stream
ustreamerctl snapshot /tmp/snap.jpg
```

### Option B: Via Ansible (`vars.yml` & `--tags stream-ustreamer`)
Set `stream_ustreamer_enabled: true` or `false` in `machines/<MACHINE_NAME>/vars.yml` and run:
```bash
./scripts/run-machine.sh <MACHINE_NAME> --tags stream-ustreamer
```

---

## 3. Home Assistant Integration (MJPEG IP Camera)

In Home Assistant, go to **Settings → Devices & Services → Add Integration → MJPEG IP Camera**:
- **MJPEG URL**: `http://<machine_ip>:<stream_ustreamer_port>/stream`
- **Still Image URL**: `http://<machine_ip>:<stream_ustreamer_port>/snapshot`
- **Authentication**: `Basic`
- **Username**: `<stream_ustreamer_user>` (stored in `machines/<MACHINE_NAME>/secrets.yml`)
- **Password**: `<stream_ustreamer_password>` (stored in `machines/<MACHINE_NAME>/secrets.yml`)
