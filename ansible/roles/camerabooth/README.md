# `camerabooth` — Touchscreen GTK 3 Camera Booth App & Weston Launcher

This module deploys the single-file **Python 3 + GTK 3 (`PyGObject`)** touchscreen Camera Booth GUI application (`/usr/local/bin/camera-booth`), creates the `~/camera_booth` photo output directory, installs a `32×32` camera launcher icon (`/usr/share/weston/icon_camera.png`), and adds a top-bar `[launcher]` icon right next to `weston-editor` in `/etc/xdg/weston/weston.ini`.

> **Prerequisite**: Requires `/usr/local/bin/camera` (deployed by `camera-ov5645` or an equivalent camera module supporting `camera capture <output_path>`).

---

## 1. Deployed Files & Configuration

| Path | Description |
| :--- | :--- |
| **`/usr/local/bin/camera-booth`** | Standalone Python 3 + GTK 3 touchscreen application (`740×410` window sized for `800×480` LCD displays) |
| **`~/camera_booth.py`** | Convenience symlink in the user's home folder pointing to `/usr/local/bin/camera-booth` |
| **`~/camera_booth/`** | Directory where captured photos are saved (`photo_<YYYYMMDD_HHMMSS>.jpg`, default `1280×960` from `/usr/local/bin/camera`) |
| **`/usr/share/weston/icon_camera.png`** | `32×32` RGBA PNG camera icon displayed in the Weston top panel |
| **`/etc/xdg/weston/weston.ini`** | Configured with `[launcher]` entry for `/usr/local/bin/camera-booth` next to `weston-editor` (restarts `weston.service` when modified) |

---

## 2. Launching & Using Camera Booth

### From the Touchscreen (Weston Panel)
Tap the **Camera icon** in the top-left Weston launcher bar (right next to the text editor icon) to open the **Camera Booth** window, then tap **"Take Picture"**.

### From SSH or Terminal (Single-Line Command)
Because `camera-booth` automatically sets default Wayland environment variables (`XDG_RUNTIME_DIR=/run/user/0`, `WAYLAND_DISPLAY=wayland-0`, `GDK_BACKEND=wayland`) when unset, it can also be launched directly on the device screen from an SSH session or terminal:

```bash
/usr/local/bin/camera-booth
```
