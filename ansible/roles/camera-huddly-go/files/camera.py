#!/usr/bin/env python3
"""
camera.py - Huddly GO USB Camera Control and Frame Capture Utility
==================================================================

This module provides USB/UVC detection, status inspection, hardware digital PTZ
control, and MJPEG frame capture capabilities for the Huddly GO wide-angle USB
camera (USB ID 2bd9:0011).

Hardware details:
- Manufacturer / Model: Huddly / Huddly GO
- USB Vendor / Product ID: 2bd9:0011
- Kernel Driver: uvcvideo (Linux USB Video Class)
- V4L2 Capture Device: /dev/video0 (MJPG 1280x720 @ 30fps)
- V4L2 Metadata Device: /dev/video1
- Onboard VPU/ISP Warmup: Requires ~60-90 warmup frames (~2-3s) when waking from
  standby before auto-exposure converges and outputs non-black frames.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_VIDEO_DEV = os.environ.get("CAMERA_VIDEO_DEV", "/dev/video0")
DEFAULT_USB_VID = os.environ.get("CAMERA_USB_VID", "2bd9").lower()
DEFAULT_USB_PID = os.environ.get("CAMERA_USB_PID", "0011").lower()
DEFAULT_WIDTH = int(os.environ.get("CAMERA_DEFAULT_WIDTH", "1280"))
DEFAULT_HEIGHT = int(os.environ.get("CAMERA_DEFAULT_HEIGHT", "720"))
DEFAULT_ROTATE = int(os.environ.get("CAMERA_DEFAULT_ROTATE", "0"))
DEFAULT_WARMUP = int(os.environ.get("CAMERA_DEFAULT_WARMUP", "90"))
DEFAULT_ZOOM = int(os.environ.get("CAMERA_DEFAULT_ZOOM", "1000"))
DEFAULT_PAN = int(os.environ.get("CAMERA_DEFAULT_PAN", "0"))
DEFAULT_TILT = int(os.environ.get("CAMERA_DEFAULT_TILT", "0"))

SUPPORTED_RESOLUTIONS = [
    (1280, 720),
]


def _read_sysfs(path):
    """Read and strip a single-line sysfs file if present."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read().strip()
    except Exception:
        pass
    return None


def probe_usb_camera(vid=DEFAULT_USB_VID, pid=DEFAULT_USB_PID):
    """
    Inspect sysfs USB devices to detect the Huddly GO camera.
    Returns:
        dict: USB hardware detection details.
    """
    info = {
        "vendor_id": vid,
        "product_id": pid,
        "usb_id": f"{vid}:{pid}",
        "detected": False,
        "manufacturer": None,
        "product": None,
        "serial": None,
        "bcd_device": None,
        "bus_path": None,
        "speed_mbps": None,
    }

    for dev_dir in sorted(glob.glob("/sys/bus/usb/devices/*")):
        v = _read_sysfs(os.path.join(dev_dir, "idVendor"))
        p = _read_sysfs(os.path.join(dev_dir, "idProduct"))
        if v and p and v.lower() == vid.lower() and p.lower() == pid.lower():
            info["detected"] = True
            info["manufacturer"] = _read_sysfs(os.path.join(dev_dir, "manufacturer")) or "Huddly"
            info["product"] = _read_sysfs(os.path.join(dev_dir, "product")) or "Huddly GO"
            info["serial"] = _read_sysfs(os.path.join(dev_dir, "serial"))
            info["bcd_device"] = _read_sysfs(os.path.join(dev_dir, "bcdDevice"))
            info["bus_path"] = os.path.basename(dev_dir)
            info["speed_mbps"] = _read_sysfs(os.path.join(dev_dir, "speed"))
            break

    return info


def resolve_video_device(preferred_dev=DEFAULT_VIDEO_DEV):
    """
    Resolve the V4L2 video capture node for the Huddly GO camera.
    Checks preferred_dev first, then scans /sys/class/video4linux/video* for
    a 'Huddly' node with Video Capture capability.
    """
    candidates = []
    if preferred_dev and os.path.exists(preferred_dev):
        candidates.append(preferred_dev)

    for sys_node in sorted(glob.glob("/sys/class/video4linux/video*")):
        name = _read_sysfs(os.path.join(sys_node, "name")) or ""
        dev_path = f"/dev/{os.path.basename(sys_node)}"
        if "huddly" in name.lower() and dev_path not in candidates and os.path.exists(dev_path):
            candidates.append(dev_path)

    for dev_path in candidates:
        res = subprocess.run(
            ["v4l2-ctl", "--device", dev_path, "--info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0 and "Device Caps" in res.stdout:
            after_caps = res.stdout.split("Device Caps", 1)[1]
            if "Video Capture" in after_caps:
                return dev_path

    return preferred_dev


def get_v4l2_status(video_dev=None):
    """
    Query the status, capabilities, formats, and control values of the V4L2 device.
    Returns:
        dict: Device node status, formats, and current control values.
    """
    resolved_dev = resolve_video_device(video_dev or DEFAULT_VIDEO_DEV)
    status = {
        "device": resolved_dev,
        "exists": os.path.exists(resolved_dev),
        "driver": "Unknown",
        "card": "Unknown",
        "bus_info": "Unknown",
        "serial": None,
        "formats": [],
        "controls": {},
    }

    if not status["exists"]:
        return status

    try:
        res = subprocess.run(
            ["v4l2-ctl", "--device", resolved_dev, "--info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                s = line.strip()
                if s.startswith("Driver name"):
                    status["driver"] = s.split(":", 1)[1].strip()
                elif s.startswith("Card type"):
                    status["card"] = s.split(":", 1)[1].strip()
                elif s.startswith("Bus info") and status["bus_info"] == "Unknown":
                    status["bus_info"] = s.split(":", 1)[1].strip()
                elif s.startswith("Serial"):
                    status["serial"] = s.split(":", 1)[1].strip()

        fmt_res = subprocess.run(
            ["v4l2-ctl", "--device", resolved_dev, "--list-formats-ext"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if fmt_res.returncode == 0:
            current_fmt = None
            for line in fmt_res.stdout.splitlines():
                s = line.strip()
                if s.startswith("[") and "'" in s:
                    current_fmt = s
                    status["formats"].append(current_fmt)
                elif s.startswith("Size:") and status["formats"]:
                    status["formats"][-1] += f" ({s})"
                elif s.startswith("Interval:") and status["formats"]:
                    status["formats"][-1] += f" [{s}]"

        ctrl_res = subprocess.run(
            ["v4l2-ctl", "--device", resolved_dev, "--list-ctrls"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if ctrl_res.returncode == 0:
            for line in ctrl_res.stdout.splitlines():
                s = line.strip()
                if "0x" in s and ":" in s and "value=" in s:
                    name_part = s.split("0x", 1)[0].strip()
                    val_part = s.split("value=", 1)[1].split()[0].strip()
                    try:
                        status["controls"][name_part] = int(val_part)
                    except ValueError:
                        status["controls"][name_part] = val_part
    except Exception as e:
        status["error"] = str(e)

    return status


def set_camera_controls(video_dev=None, **controls):
    """
    Set V4L2 user or camera controls on the Huddly GO device.
    Supported keys: pan_absolute, tilt_absolute, zoom_absolute, brightness,
    saturation, gain, sharpness, power_line_frequency, auto_exposure,
    exposure_time_absolute.
    """
    resolved_dev = resolve_video_device(video_dev or DEFAULT_VIDEO_DEV)
    pairs = [f"{k}={v}" for k, v in controls.items() if v is not None]
    if not pairs:
        return True

    ctrl_arg = ",".join(pairs)
    res = subprocess.run(
        ["v4l2-ctl", "--device", resolved_dev, f"--set-ctrl={ctrl_arg}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        print(f"[ERROR] Failed to set controls ({ctrl_arg}): {res.stderr.strip()}", file=sys.stderr)
        return False
    return True


def capture_snapshot(
    output_file,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    video_dev=DEFAULT_VIDEO_DEV,
    warmup_frames=DEFAULT_WARMUP,
    rotate=DEFAULT_ROTATE,
    zoom=None,
    pan=None,
    tilt=None,
    brightness=None,
    gain=None,
):
    """
    Capture a 1280x720 MJPEG snapshot from the Huddly GO USB camera.

    Streams `warmup_frames` (default 90 frames / ~3.0s at 30fps) before saving
    the target frame so the Huddly GO's onboard VPU/ISP wakes from standby and
    converges auto-exposure and white balance.
    """
    resolved_dev = resolve_video_device(video_dev)
    if not os.path.exists(resolved_dev):
        print(f"[ERROR] Camera device {resolved_dev} does not exist.", file=sys.stderr)
        return False

    if (width, height) not in SUPPORTED_RESOLUTIONS:
        closest = min(SUPPORTED_RESOLUTIONS, key=lambda res: abs(res[0] - width) + abs(res[1] - height))
        print(f"[INFO] Adjusting resolution {width}x{height} -> supported hardware mode {closest[0]}x{closest[1]}")
        width, height = closest

    # Apply any optional PTZ or exposure controls prior to capture
    set_camera_controls(
        resolved_dev,
        zoom_absolute=zoom,
        pan_absolute=pan,
        tilt_absolute=tilt,
        brightness=brightness,
        gain=gain,
    )

    output_abs = os.path.abspath(output_file)
    os.makedirs(os.path.dirname(output_abs), exist_ok=True)
    warmup_frames = max(1, int(warmup_frames))

    print(
        f"[*] Capturing {width}x{height} MJPG snapshot from {resolved_dev} "
        f"(warmup={warmup_frames} frames, rotate={rotate}°) -> {output_abs}..."
    )

    with tempfile.TemporaryDirectory(prefix="huddly_capture_") as temp_dir:
        raw_jpg = os.path.join(temp_dir, "capture.jpg")
        cmd = [
            "v4l2-ctl",
            f"--device={resolved_dev}",
            f"--set-fmt-video=width={width},height={height},pixelformat=MJPG",
            "--stream-mmap",
            f"--stream-skip={warmup_frames}",
            "--stream-count=1",
            f"--stream-to={raw_jpg}",
        ]

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            print(f"[ERROR] v4l2-ctl capture failed (code {res.returncode}): {res.stderr.strip()}", file=sys.stderr)
            return False

        if not os.path.exists(raw_jpg) or os.path.getsize(raw_jpg) == 0:
            print("[ERROR] No frame was written by v4l2-ctl.", file=sys.stderr)
            return False

        if rotate in (90, 180, 270):
            jpegtran_bin = shutil.which("jpegtran")
            if jpegtran_bin:
                rot_res = subprocess.run(
                    [jpegtran_bin, "-rotate", str(rotate), "-outfile", output_abs, raw_jpg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if rot_res.returncode != 0:
                    print(f"[WARN] jpegtran rotation failed ({rot_res.stderr.strip()}); copying unrotated frame.", file=sys.stderr)
                    shutil.copy2(raw_jpg, output_abs)
            else:
                print("[WARN] 'jpegtran' not found; saving unrotated frame.", file=sys.stderr)
                shutil.copy2(raw_jpg, output_abs)
        else:
            shutil.copy2(raw_jpg, output_abs)

        if os.path.exists(output_abs) and os.path.getsize(output_abs) > 0:
            size_kb = os.path.getsize(output_abs) / 1024.0
            print(
                f"[SUCCESS] Snapshot captured successfully: {output_abs} "
                f"({size_kb:.1f} KB, after {warmup_frames} warmup frames)"
            )
            return True

        print(f"[ERROR] Output file {output_abs} is missing or empty.", file=sys.stderr)
        return False


def cmd_status(args):
    """Handle the 'status' CLI subcommand."""
    usb_info = probe_usb_camera()
    v4l2_info = get_v4l2_status(getattr(args, "device", DEFAULT_VIDEO_DEV))

    data = {
        "usb": usb_info,
        "v4l2": v4l2_info,
    }

    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return

    print("======================================================================")
    print(" Huddly GO USB Camera Status Report")
    print("======================================================================")
    print(f" Camera Model:       {usb_info.get('manufacturer') or 'Huddly'} {usb_info.get('product') or 'Huddly GO'}")
    print(f" USB ID & Bus:       {usb_info.get('usb_id')} (bus {usb_info.get('bus_path')}, {usb_info.get('speed_mbps')} Mbps)")
    print(f" USB Connected:      {'YES' if usb_info.get('detected') else 'NO'}")
    print(f" Serial Number:      {usb_info.get('serial') or v4l2_info.get('serial') or 'Unknown'}")
    print(f" Hardware Revision:  {usb_info.get('bcd_device') or 'Unknown'}")
    print("----------------------------------------------------------------------")
    print(f" V4L2 Capture Node:  {v4l2_info.get('device')} ({'Present' if v4l2_info.get('exists') else 'Not Found'})")
    print(f" Kernel Driver:      {v4l2_info.get('driver')} / {v4l2_info.get('card')}")
    if v4l2_info.get("formats"):
        print(f" Stream Formats:     {', '.join(v4l2_info.get('formats'))}")
    if v4l2_info.get("controls"):
        ctrls = v4l2_info["controls"]
        print("----------------------------------------------------------------------")
        print(
            f" Digital PTZ:        zoom={ctrls.get('zoom_absolute')} "
            f"pan={ctrls.get('pan_absolute')} tilt={ctrls.get('tilt_absolute')}"
        )
        print(
            f" Image Controls:     brightness={ctrls.get('brightness')} "
            f"gain={ctrls.get('gain')} saturation={ctrls.get('saturation')} "
            f"sharpness={ctrls.get('sharpness')}"
        )
    print("======================================================================")


def cmd_capture(args):
    """Handle the 'capture' / 'snapshot' CLI subcommand."""
    out_file = args.output or f"/tmp/camera_snapshot_{int(time.time())}.jpg"
    success = capture_snapshot(
        output_file=out_file,
        width=args.width,
        height=args.height,
        video_dev=args.device,
        warmup_frames=args.warmup,
        rotate=args.rotate,
        zoom=args.zoom,
        pan=args.pan,
        tilt=args.tilt,
        brightness=args.brightness,
        gain=args.gain,
    )
    if not success:
        sys.exit(1)


def cmd_ptz(args):
    """Handle the 'ptz' CLI subcommand to view or update PTZ and image controls."""
    dev = resolve_video_device(args.device)
    if args.reset:
        ok = set_camera_controls(
            dev,
            zoom_absolute=1000,
            pan_absolute=0,
            tilt_absolute=0,
            brightness=0,
            gain=100,
            saturation=255,
            sharpness=120,
        )
        if not ok:
            sys.exit(1)
        print("[OK] Reset Huddly GO digital PTZ and image controls to defaults.")
    else:
        ok = set_camera_controls(
            dev,
            zoom_absolute=args.zoom,
            pan_absolute=args.pan,
            tilt_absolute=args.tilt,
            brightness=args.brightness,
            gain=args.gain,
            saturation=args.saturation,
            sharpness=args.sharpness,
        )
        if not ok:
            sys.exit(1)

    v4l2_info = get_v4l2_status(dev)
    if getattr(args, "json", False):
        print(json.dumps(v4l2_info.get("controls", {}), indent=2))
    else:
        for k, v in v4l2_info.get("controls", {}).items():
            print(f"  {k}: {v}")


def cmd_detect(args):
    """Handle the 'detect' hardware diagnostic subcommand."""
    if getattr(args, "json", False):
        cmd_status(args)
        return

    print("=== Huddly GO USB Camera Hardware Diagnostic ===")
    print("[1] Checking USB devices (lsusb):")
    subprocess.run(["lsusb"], check=False)
    print("")

    print("[2] Checking V4L2 device list (v4l2-ctl --list-devices):")
    subprocess.run(["v4l2-ctl", "--list-devices"], check=False)
    print("")

    print("[3] Detailed Camera Status:")
    cmd_status(args)


def main():
    parser = argparse.ArgumentParser(
        description="Huddly GO USB Camera Management, PTZ & Capture CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # status command
    sub_status = subparsers.add_parser("status", help="Query Huddly GO USB and V4L2 status")
    sub_status.add_argument("--device", default=DEFAULT_VIDEO_DEV, help=f"V4L2 device node (default: {DEFAULT_VIDEO_DEV})")
    sub_status.add_argument("--json", action="store_true", help="Output results in JSON format")

    # capture / snapshot command
    sub_capture = subparsers.add_parser(
        "capture",
        aliases=["snapshot"],
        help="Capture a still snapshot (JPEG)",
    )
    sub_capture.add_argument("output", nargs="?", default=None, help="Output image file path (e.g. /tmp/photo.jpg)")
    sub_capture.add_argument(
        "--width",
        "-W",
        type=int,
        default=DEFAULT_WIDTH,
        help=f"Frame width in pixels (default: {DEFAULT_WIDTH})",
    )
    sub_capture.add_argument(
        "--height",
        "-H",
        type=int,
        default=DEFAULT_HEIGHT,
        help=f"Frame height in pixels (default: {DEFAULT_HEIGHT})",
    )
    sub_capture.add_argument(
        "--rotate",
        "-r",
        type=int,
        choices=[0, 90, 180, 270],
        default=DEFAULT_ROTATE,
        help=f"Lossless JPEG rotation angle in degrees (0, 90, 180, or 270; default: {DEFAULT_ROTATE})",
    )
    sub_capture.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=DEFAULT_WARMUP,
        help=f"Number of initial frames to skip for VPU/ISP wakeup & AEC convergence (default: {DEFAULT_WARMUP})",
    )
    sub_capture.add_argument("--zoom", type=int, default=None, help="Digital zoom (1000..4000, default 1000)")
    sub_capture.add_argument("--pan", type=int, default=None, help="Digital pan (-216000..216000, default 0)")
    sub_capture.add_argument("--tilt", type=int, default=None, help="Digital tilt (-162000..162000, default 0)")
    sub_capture.add_argument("--brightness", type=int, default=None, help="Brightness (-600..600, default 0)")
    sub_capture.add_argument("--gain", type=int, default=None, help="Gain (100..1200, default 100)")
    sub_capture.add_argument(
        "--device",
        default=DEFAULT_VIDEO_DEV,
        help=f"V4L2 device node (default: {DEFAULT_VIDEO_DEV})",
    )

    # ptz command
    sub_ptz = subparsers.add_parser("ptz", help="Get or set digital Pan/Tilt/Zoom and image controls")
    sub_ptz.add_argument("--zoom", type=int, default=None, help="Digital zoom (1000..4000)")
    sub_ptz.add_argument("--pan", type=int, default=None, help="Digital pan (-216000..216000)")
    sub_ptz.add_argument("--tilt", type=int, default=None, help="Digital tilt (-162000..162000)")
    sub_ptz.add_argument("--brightness", type=int, default=None, help="Brightness (-600..600)")
    sub_ptz.add_argument("--gain", type=int, default=None, help="Gain (100..1200)")
    sub_ptz.add_argument("--saturation", type=int, default=None, help="Saturation (1..255)")
    sub_ptz.add_argument("--sharpness", type=int, default=None, help="Sharpness (0..255)")
    sub_ptz.add_argument("--reset", action="store_true", help="Reset PTZ and image controls to defaults")
    sub_ptz.add_argument("--device", default=DEFAULT_VIDEO_DEV, help=f"V4L2 device node (default: {DEFAULT_VIDEO_DEV})")
    sub_ptz.add_argument("--json", action="store_true", help="Output controls in JSON format")

    # detect command
    sub_detect = subparsers.add_parser("detect", help="Run USB and V4L2 camera hardware diagnostic check")
    sub_detect.add_argument("--device", default=DEFAULT_VIDEO_DEV, help=f"V4L2 device node (default: {DEFAULT_VIDEO_DEV})")
    sub_detect.add_argument("--json", action="store_true", help="Output camera status in JSON format")

    # help command
    subparsers.add_parser("help", help="Show this help message")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command in ("capture", "snapshot"):
        cmd_capture(args)
    elif args.command == "ptz":
        cmd_ptz(args)
    elif args.command == "detect":
        cmd_detect(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
