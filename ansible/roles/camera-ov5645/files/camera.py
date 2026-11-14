#!/usr/bin/env python3
"""
camera.py - Camera Control and Frame Capture Utility
===================================================

This module provides detection, status inspection, and frame capture
capabilities for MIPI-CSI camera sensors (such as OmniVision OV5645 / OV5640)
connected to the NXP i.MX7Dual on the TechNexion PICO-PI-IMX7 baseboard.

Hardware details:
- Interface: MIPI-CSI 2-lane (`30750000.mipi-csi` -> `30710000.csi1` / `/dev/video1`)
- Sensor I2C Bus: `/dev/i2c-3` (`30a50000.i2c`)
- Sensor I2C Address: 0x3c (OV5645 / OV5640)
- Master Clock (MCLK): 24 MHz via CCM_CLKO1 (`GPIO1_IO02`)
- Control Lines:
  - Reset (CAM_RST): GPIO1_IO05 (active-low)
  - Power Down (CAM_PWDN): GPIO1_IO04 (active-high)
"""

import argparse
import errno
import fcntl
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# I2C and V4L2 definitions (configurable via environment variables from camera.sh)
I2C_SLAVE = 0x0703
I2C_SLAVE_FORCE = 0x0706
DEFAULT_I2C_BUS = os.environ.get("CAMERA_I2C_BUS", "/dev/i2c-3")
DEFAULT_I2C_ADDR = int(os.environ.get("CAMERA_I2C_ADDR", "0x3c"), 0)
DEFAULT_VIDEO_DEV = os.environ.get("CAMERA_VIDEO_DEV", "/dev/video1")
DEFAULT_WIDTH = int(os.environ.get("CAMERA_DEFAULT_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.environ.get("CAMERA_DEFAULT_HEIGHT", "1080"))
DEFAULT_ROTATE = int(os.environ.get("CAMERA_DEFAULT_ROTATE", "180"))
DEFAULT_WARMUP = int(os.environ.get("CAMERA_DEFAULT_WARMUP", "15"))
DEFAULT_QUALITY = int(os.environ.get("CAMERA_DEFAULT_QUALITY", "95"))

# CCM CLKO1 register address for master clock verification
CCM_CLKO1_REG = "0x3038bd80"


def check_clko1_status():
    """
    Check if the hardware master clock (CCM_CLKO1) is enabled.
    Returns:
        dict: Information on whether CLKO1 is enabled and its register value.
    """
    try:
        # Query CCM_TARGET_ROOT for CLKO1 using busybox devmem if available
        res = subprocess.run(
            ["busybox", "devmem", CCM_CLKO1_REG],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            val_hex = res.stdout.strip()
            val_int = int(val_hex, 16)
            is_enabled = bool(val_int & (1 << 28))
            return {
                "available": True,
                "register": CCM_CLKO1_REG,
                "value": val_hex,
                "enabled": is_enabled,
                "frequency_hz": 24000000 if is_enabled else 0,
            }
        else:
            # Check if camera-init service is active as fallback for unprivileged users
            svc_res = subprocess.run(
                ["systemctl", "is-active", "camera-init.service"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if svc_res.returncode == 0 and svc_res.stdout.strip() == "active":
                return {
                    "available": True,
                    "register": CCM_CLKO1_REG,
                    "value": "0x10000000 (via camera-init.service)",
                    "enabled": True,
                    "frequency_hz": 24000000,
                }
    except Exception as e:
        return {"available": False, "error": str(e)}

    return {"available": False, "enabled": False}


def enable_clko1():
    """
    Ensure the 24MHz master clock output on GPIO1_IO02 is turned on.
    """
    try:
        subprocess.run(
            ["busybox", "devmem", CCM_CLKO1_REG, "32", "0x10000000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return True
    except Exception:
        return False


def get_gpio_state(pin_num):
    """
    Read the current value of a sysfs GPIO pin.
    Args:
        pin_num (int): The GPIO line number.
    Returns:
        int or None: The value (0 or 1), or None if unexported.
    """
    val_path = f"/sys/class/gpio/gpio{pin_num}/value"
    if os.path.exists(val_path):
        try:
            with open(val_path, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def probe_i2c_sensor(bus_path=DEFAULT_I2C_BUS, addr=DEFAULT_I2C_ADDR):
    """
    Probe the camera sensor over I2C and read the chip ID register (0x300A/0x300B).
    Returns:
        dict: Sensor detection details.
    """
    info = {
        "bus": bus_path,
        "address": hex(addr),
        "detected": False,
        "chip_id": None,
        "model": "Unknown",
        "error": None,
    }

    # Extract bus number from bus_path (e.g. /dev/i2c-3 -> 3)
    bus_num = "3"
    if "-" in bus_path:
        bus_num = bus_path.rsplit("-", 1)[-1]

    # 1. First check if sensor is already bound to a kernel driver
    sysfs_driver_link = f"/sys/bus/i2c/devices/{bus_num}-{addr:04x}/driver"
    if os.path.islink(sysfs_driver_link):
        try:
            drv_name = os.path.basename(os.readlink(sysfs_driver_link))
            info["detected"] = True
            info["driver"] = drv_name
            if "ov5645" in drv_name.lower():
                info["model"] = "OmniVision OV5645 (5MP, Bound to Kernel Driver)"
                info["chip_id"] = "0x5645"
            elif "ov5640" in drv_name.lower():
                info["model"] = "OmniVision OV5640 (5MP, Bound to Kernel Driver)"
                info["chip_id"] = "0x5640"
            else:
                info["model"] = f"Camera Sensor (Bound to {drv_name})"
            return info
        except Exception:
            pass

    # 2. Direct userspace I2C probe if not currently bound
    if not os.path.exists(bus_path):
        info["error"] = f"I2C device node {bus_path} does not exist"
        return info

    try:
        fd = os.open(bus_path, os.O_RDWR)
    except OSError as e:
        info["error"] = f"Failed to open {bus_path}: {e}"
        return info

    try:
        # Use I2C_SLAVE, or fallback to I2C_SLAVE_FORCE if address is claimed
        try:
            fcntl.ioctl(fd, I2C_SLAVE, addr)
        except OSError:
            fcntl.ioctl(fd, I2C_SLAVE_FORCE, addr)

        # Write 16-bit register address 0x300A (Chip ID High)
        os.write(fd, b"\x30\x0a")
        # Read 2 bytes (0x300A High, 0x300B Low)
        data = os.read(fd, 2)
        if len(data) == 2:
            chip_id = (data[0] << 8) | data[1]
            info["detected"] = True
            info["chip_id"] = hex(chip_id)
            if chip_id == 0x5645:
                info["model"] = "OmniVision OV5645 (5MP)"
            elif chip_id == 0x5640:
                info["model"] = "OmniVision OV5640 (5MP)"
            else:
                info["model"] = f"Unknown OmniVision sensor ({hex(chip_id)})"
    except OSError as e:
        if e.errno == errno.EBUSY:
            info["error"] = "Device busy (claimed by active kernel driver)"
        elif e.errno == errno.ENXIO:
            info["error"] = "No acknowledge (NACK) from address 0x3c (verify FPC cable connection & orientation)"
        else:
            info["error"] = f"I2C I/O error ({e.errno}): {e.strerror}"
    finally:
        os.close(fd)

    return info


def get_v4l2_status(video_dev=DEFAULT_VIDEO_DEV):
    """
    Query the status of the V4L2 video capture device.
    Returns:
        dict: Device node status and capabilities.
    """
    status = {
        "device": video_dev,
        "exists": os.path.exists(video_dev),
        "driver": "Unknown",
        "card": "Unknown",
        "formats": [],
    }

    if not status["exists"]:
        return status

    try:
        res = subprocess.run(
            ["v4l2-ctl", "--device", video_dev, "--all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.startswith("Driver name"):
                    status["driver"] = line.split(":", 1)[1].strip()
                elif line.startswith("Card type"):
                    status["card"] = line.split(":", 1)[1].strip()

        # Check supported formats
        fmt_res = subprocess.run(
            ["v4l2-ctl", "--device", video_dev, "--list-formats"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if fmt_res.returncode == 0:
            for line in fmt_res.stdout.splitlines():
                if "[" in line and "]" in line and "'" in line:
                    status["formats"].append(line.strip())
    except Exception as e:
        status["error"] = str(e)

    return status


SUPPORTED_RESOLUTIONS = [
    (1280, 960),
    (1920, 1080),
    (2592, 1944),
]


def capture_snapshot(
    output_file,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    video_dev=DEFAULT_VIDEO_DEV,
    warmup_frames=DEFAULT_WARMUP,
    rotate=DEFAULT_ROTATE,
    quality=DEFAULT_QUALITY,
):
    """
    Capture a high-quality JPEG snapshot from the V4L2 MIPI-CSI camera device.

    Uses GStreamer pipeline with UYVY color format and automatic warm-up streaming.
    The warm-up sequence streams initial frames directly into JPEG memory so that:
    1. The NXP mx6s-csi DMA controller synchronizes ping-pong buffers with the sensor VBI.
    2. The OmniVision OV5645 ISP Auto Exposure Control (AEC) and Auto White Balance (AWB)
       stabilize to true scene illumination.
    3. The optional 180-degree rotation corrects for the ribbon cable's inverted mounting orientation.

    Args:
        output_file (str): Destination path for the saved JPEG file.
        width (int): Frame width in pixels (1280, 1920, or 2592; default 1920).
        height (int): Frame height in pixels (960, 1080, or 1944; default 1080).
        video_dev (str): Path to V4L2 device node (default /dev/video1).
        warmup_frames (int): Number of warmup frames to stream (default 15).
        rotate (int): Image rotation in degrees: 0, 90, 180, or 270 (default 180).
        quality (int): JPEG encoding quality from 1 to 100 (default 95).

    Returns:
        bool: True if capture succeeded and file was verified, False otherwise.
    """
    if not os.path.exists(video_dev):
        print(f"[ERROR] Camera device {video_dev} does not exist.", file=sys.stderr)
        return False

    # Auto-adjust requested resolution to closest supported hardware mode
    if (width, height) not in SUPPORTED_RESOLUTIONS:
        closest = min(SUPPORTED_RESOLUTIONS, key=lambda res: abs(res[0] - width) + abs(res[1] - height))
        print(f"[INFO] Adjusting resolution {width}x{height} -> supported hardware mode {closest[0]}x{closest[1]}")
        width, height = closest

    # Ensure parent output directory exists
    output_abs = os.path.abspath(output_file)
    os.makedirs(os.path.dirname(output_abs), exist_ok=True)

    # Ensure warmup frame count is sensible
    warmup_frames = max(1, int(warmup_frames))

    print(
        f"[*] Capturing {width}x{height} snapshot from {video_dev} "
        f"(warmup={warmup_frames} frames, rotate={rotate}°, quality={quality}) -> {output_abs}..."
    )

    # Use an isolated temporary directory for warmup JPEG frames
    with tempfile.TemporaryDirectory(prefix="cam_warmup_") as temp_dir:
        temp_pattern = os.path.join(temp_dir, "frame_%03d.jpg")

        # Build GStreamer UYVY capture pipeline
        pipeline = [
            "gst-launch-1.0",
            "-q",
            "v4l2src",
            f"device={video_dev}",
            f"num-buffers={warmup_frames}",
            "!",
            f"video/x-raw,format=UYVY,width={width},height={height}",
            "!",
            "videoconvert",
        ]

        # Add hardware-accelerated / efficient videoflip for camera orientation correction
        if rotate == 180:
            pipeline.extend(["!", "videoflip", "video-direction=180"])
        elif rotate == 90:
            pipeline.extend(["!", "videoflip", "video-direction=90r"])
        elif rotate == 270:
            pipeline.extend(["!", "videoflip", "video-direction=90l"])
        elif rotate == 0:
            pass
        else:
            print(f"[WARN] Unsupported rotation '{rotate}deg', proceeding without rotation.", file=sys.stderr)

        # JPEG encoder and multifilesink
        pipeline.extend([
            "!",
            "jpegenc",
            f"quality={int(quality)}",
            "!",
            "multifilesink",
            f"location={temp_pattern}",
        ])

        try:
            res = subprocess.run(
                pipeline,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if res.returncode != 0:
                print(f"[ERROR] GStreamer pipeline failed (code {res.returncode}): {res.stderr.strip()}", file=sys.stderr)
                return False

            # Find all captured frames in the temporary directory
            captured_frames = sorted(glob.glob(os.path.join(temp_dir, "frame_*.jpg")))
            if not captured_frames:
                print("[ERROR] No image frames were generated by the capture pipeline.", file=sys.stderr)
                return False

            # Select the final frame (fully converged exposure and white balance)
            best_frame = captured_frames[-1]

            # Copy to requested destination path
            shutil.copy2(best_frame, output_abs)

            # Validate final file
            if os.path.exists(output_abs) and os.path.getsize(output_abs) > 0:
                size_kb = os.path.getsize(output_abs) / 1024.0
                print(
                    f"[SUCCESS] Snapshot captured successfully: {output_abs} "
                    f"({size_kb:.1f} KB, frame #{len(captured_frames)})"
                )
                return True
            else:
                print(f"[ERROR] Output file {output_abs} is missing or empty.", file=sys.stderr)
                return False

        except Exception as e:
            print(f"[ERROR] Exception during snapshot capture: {e}", file=sys.stderr)
            return False


def cmd_status(args):
    """Handle the 'status' CLI subcommand."""
    enable_clko1()

    clko_info = check_clko1_status()
    i2c_info = probe_i2c_sensor()
    v4l2_info = get_v4l2_status()

    gpio_pwn = get_gpio_state(4)
    gpio_rst = get_gpio_state(5)

    data = {
        "sensor": i2c_info,
        "master_clock": clko_info,
        "v4l2": v4l2_info,
        "gpios": {
            "gpio4_pwn": gpio_pwn,
            "gpio5_rst": gpio_rst,
        },
    }

    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return

    print("======================================================================")
    print(" MIPI-CSI Camera Status Report")
    print("======================================================================")
    print(f" Sensor Model:       {i2c_info.get('model', 'Unknown')}")
    print(f" I2C Bus & Address:  {i2c_info.get('bus')} @ {i2c_info.get('address')}")
    print(f" Sensor Responding:  {'YES' if i2c_info.get('detected') else 'NO'}")
    if i2c_info.get("chip_id"):
        print(f" Sensor Chip ID:     {i2c_info.get('chip_id')}")
    if i2c_info.get("error"):
        print(f" Sensor I2C Note:    {i2c_info.get('error')}")

    print("----------------------------------------------------------------------")
    print(f" V4L2 Device:        {v4l2_info.get('device')} ({'Present' if v4l2_info.get('exists') else 'Not Found'})")
    print(f" Host Capture Driver:{v4l2_info.get('driver')} / {v4l2_info.get('card')}")
    if v4l2_info.get("formats"):
        print(f" Supported Formats:  {', '.join(v4l2_info.get('formats'))}")

    print("----------------------------------------------------------------------")
    print(f" Master Clock (MCLK):{'Active (24 MHz)' if clko_info.get('enabled') else 'Inactive (0 MHz)'}")
    print(f" Power Down (GPIO4): {gpio_pwn if gpio_pwn is not None else 'Unexported'}")
    print(f" Reset (GPIO5):      {gpio_rst if gpio_rst is not None else 'Unexported'}")
    print("======================================================================")


def cmd_capture(args):
    """Handle the 'capture' / 'snapshot' CLI subcommand."""
    enable_clko1()

    out_file = args.output or f"/tmp/camera_snapshot_{int(time.time())}.jpg"
    success = capture_snapshot(
        output_file=out_file,
        width=args.width,
        height=args.height,
        video_dev=args.device,
        warmup_frames=args.warmup,
        rotate=args.rotate,
        quality=args.quality,
    )
    if not success:
        sys.exit(1)


def cmd_detect(args):
    """Handle the 'detect' hardware diagnostic subcommand."""
    print("=== MIPI-CSI Camera Hardware Diagnostic ===")
    print("[1] Checking V4L2 device nodes:")
    video_nodes = sorted(glob.glob("/dev/video*"))
    if video_nodes:
        subprocess.run(["ls", "-l"] + video_nodes, check=False)
    else:
        print("No /dev/video nodes found.")
    print("")

    print("[2] Checking Master Clock (CLKO1 24MHz):")
    clko_info = check_clko1_status()
    if clko_info.get("available"):
        print(f"Register {clko_info.get('register')}: {clko_info.get('value')} (enabled={clko_info.get('enabled')})")
    else:
        print("Unable to read CCM register.")
    print("")

    print("[3] Checking I2C-3 devices:")
    bus_num = DEFAULT_I2C_BUS.rsplit("-", 1)[-1] if "-" in DEFAULT_I2C_BUS else "3"
    res = subprocess.run(["i2cdetect", "-y", "-r", bus_num], check=False)
    if res.returncode != 0:
        print("i2cdetect not available or failed.")
    print("")

    print("[4] Sensor Probe via Python:")
    cmd_status(args)


def main():
    parser = argparse.ArgumentParser(
        description="TechNexion i.MX7D Camera Management & Capture CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # status command
    sub_status = subparsers.add_parser("status", help="Query camera sensor and V4L2 interface status")
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
        help=f"Frame width in pixels (1280, 1920, or 2592; default: {DEFAULT_WIDTH})",
    )
    sub_capture.add_argument(
        "--height",
        "-H",
        type=int,
        default=DEFAULT_HEIGHT,
        help=f"Frame height in pixels (960, 1080, or 1944; default: {DEFAULT_HEIGHT})",
    )
    sub_capture.add_argument(
        "--rotate",
        "-r",
        type=int,
        choices=[0, 90, 180, 270],
        default=DEFAULT_ROTATE,
        help=f"Image rotation angle in degrees (0, 90, 180, or 270; default: {DEFAULT_ROTATE})",
    )
    sub_capture.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=DEFAULT_WARMUP,
        help=f"Number of initial frames to stream for AEC/AWB convergence (default: {DEFAULT_WARMUP})",
    )
    sub_capture.add_argument(
        "--quality",
        "-q",
        type=int,
        default=DEFAULT_QUALITY,
        help=f"JPEG compression quality from 1 to 100 (default: {DEFAULT_QUALITY})",
    )
    sub_capture.add_argument(
        "--device",
        default=DEFAULT_VIDEO_DEV,
        help=f"V4L2 device node (default: {DEFAULT_VIDEO_DEV})",
    )

    # detect command
    sub_detect = subparsers.add_parser("detect", help="Run quick camera hardware diagnostic check")
    sub_detect.add_argument("--json", action="store_true", help="Output sensor probe status in JSON format")

    # help command
    subparsers.add_parser("help", help="Show this help message")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command in ("capture", "snapshot"):
        cmd_capture(args)
    elif args.command == "detect":
        cmd_detect(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
