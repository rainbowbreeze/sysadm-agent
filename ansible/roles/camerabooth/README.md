# `camerabooth` — Touchscreen GTK 3 + GStreamer Photobooth App & Weston Launcher

This module deploys the single-file **Python 3 + GTK 3 + GStreamer (`PyGObject`)** touchscreen Camera Booth GUI application (`/usr/local/bin/camera-booth`), creates the `~/camera_booth` photo output directory, installs a `32×32` camera launcher icon (`/usr/share/weston/icon_camera.png`), and adds a top-bar `[launcher]` icon right next to `weston-editor` in `/etc/xdg/weston/weston.ini`.

> **Prerequisite**: Requires `/usr/local/bin/camera` (deployed by `camera-ov5645` or an equivalent camera module supporting `camera capture <output_path>`).

---

## 1. Key Photobooth Features

- **Live Low-FPS Camera Viewfinder (`LIVE` Badge)**:
  - Streams live video from the camera (`5 fps` by default via `camerabooth_preview_fps`, ~`12–15%` CPU on i.MX7D) matching the exact resolution, color calibration, and rotation (`camera_ov5645_rotation` / `camerabooth_rotation`) of the final photo so the subject can frame their shot before tapping the button.
- **Animated Visual Countdown + Shutter Flash (`3` $\rightarrow$ `2` $\rightarrow$ `1` $\rightarrow$ Flash)**:
  - Displays a large, high-contrast centered countdown digit and sweeping circular progress ring directly over the live camera stream (`camerabooth_countdown_seconds: 3`) so the subject knows the exact instant the photo will be snapped.
  - Fires an immediate white shutter flash and captures the already-warmed-up full-resolution frame at **`0.00s` shutter lag** the instant the countdown hits `0`.
- **Post-Capture Review**:
  - Displays the saved photo (`PHOTO SAVED` badge) for `camerabooth_review_seconds` (`4s` default, or tap **"Back to Live Camera"** early) before automatically resuming the live stream.

---

## 2. Deployed Files & Configuration

| Path | Description |
| :--- | :--- |
| **`/usr/local/bin/camera-booth`** | Standalone Python 3 + GTK 3 + GStreamer touchscreen photobooth application (`740×410` window sized for `800×480` LCD displays) |
| **`~/camera_booth.py`** | Convenience symlink in the user's home folder pointing to `/usr/local/bin/camera-booth` |
| **`~/camera_booth/`** | Directory where captured photos are saved (`photo_<YYYYMMDD_HHMMSS>.jpg`, default `1280×960`) |
| **`/usr/share/weston/icon_camera.png`** | `32×32` RGBA PNG camera icon displayed in the Weston top panel |
| **`/etc/xdg/weston/weston.ini`** | Configured with `[launcher]` entry for `/usr/local/bin/camera-booth` next to `weston-editor` |

### Configurable Role Variables (`machines/<MACHINE_NAME>/vars.yml`)

```yaml
camerabooth_countdown_seconds: 3   # Countdown timer before capture (set 0 for immediate capture)
camerabooth_preview_enabled: true  # Enable live camera stream in viewfinder
camerabooth_preview_fps: 5         # Live preview frame rate (1..15 fps)
camerabooth_review_seconds: 4      # Seconds to display captured photo before resuming live stream
camerabooth_rotation: ""           # Optional override (0, 90, 180, 270); "" inherits camera_ov5645_rotation
```

---

## 3. Launching & Using Camera Booth

### From the Touchscreen (Weston Panel)
Tap the **Camera icon** in the top-left Weston launcher bar (right next to the text editor icon) to open **Camera Booth**, frame your shot in the live preview, and tap **"Take Picture (3s Timer)"**.

### From SSH or Terminal (Single-Line Command)
Because `camera-booth` automatically sets default Wayland environment variables (`XDG_RUNTIME_DIR=/run/user/0`, `WAYLAND_DISPLAY=wayland-0`, `GDK_BACKEND=wayland`) when unset, it can also be launched directly on the device screen from an SSH session or terminal:

```bash
/usr/local/bin/camera-booth
```
