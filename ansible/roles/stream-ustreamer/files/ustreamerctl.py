#!/usr/bin/env python3
"""
ustreamerctl.py - On-Demand Control & Inspection CLI for uStreamer
==================================================================

Manages the `camera-ustreamer.service` daemon on demand (`status`, `start`,
`stop`, `restart`, `enable`, `disable`, `snapshot`) and inspects live stream
telemetry from `http://127.0.0.1:<port>/state`.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

SERVICE_NAME = "camera-ustreamer.service"
USTREAMER_DEVICE = os.environ.get("CAMERA_USTREAMER_DEVICE", "/dev/video0")
USTREAMER_FORMAT = os.environ.get("CAMERA_USTREAMER_FORMAT", "MJPEG")
USTREAMER_WIDTH = int(os.environ.get("CAMERA_USTREAMER_WIDTH", "1280"))
USTREAMER_HEIGHT = int(os.environ.get("CAMERA_USTREAMER_HEIGHT", "720"))
USTREAMER_HOST = os.environ.get("CAMERA_USTREAMER_HOST", "0.0.0.0")
USTREAMER_PORT = int(os.environ.get("CAMERA_USTREAMER_PORT", "8080"))
USTREAMER_FPS = int(os.environ.get("CAMERA_USTREAMER_FPS", "15"))
USTREAMER_USER = os.environ.get("CAMERA_USTREAMER_USER", "")
USTREAMER_PASSWORD = os.environ.get("CAMERA_USTREAMER_PASSWORD", "")


def _build_request(path):
    url = f"http://127.0.0.1:{USTREAMER_PORT}{path}"
    req = urllib.request.Request(url)
    if USTREAMER_USER:
        token = base64.b64encode(f"{USTREAMER_USER}:{USTREAMER_PASSWORD}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    return req


def get_status():
    active_res = subprocess.run(
        ["systemctl", "is-active", SERVICE_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    enabled_res = subprocess.run(
        ["systemctl", "is-enabled", SERVICE_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    service_active = active_res.returncode == 0 and active_res.stdout.strip() == "active"
    service_enabled = enabled_res.returncode == 0 and enabled_res.stdout.strip() == "enabled"

    info = {
        "service": SERVICE_NAME,
        "active": service_active,
        "enabled": service_enabled,
        "device": USTREAMER_DEVICE,
        "format": USTREAMER_FORMAT,
        "resolution": f"{USTREAMER_WIDTH}x{USTREAMER_HEIGHT}",
        "desired_fps": USTREAMER_FPS,
        "host": USTREAMER_HOST,
        "port": USTREAMER_PORT,
        "auth_enabled": bool(USTREAMER_USER),
        "auth_user": USTREAMER_USER if USTREAMER_USER else None,
        "stream_path": "/stream",
        "snapshot_path": "/snapshot",
        "online": False,
        "captured_fps": None,
    }

    if service_active:
        try:
            req = _build_request("/state")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                source = payload.get("result", {}).get("source", {})
                info["online"] = bool(source.get("online", True))
                info["captured_fps"] = source.get("captured_fps")
        except Exception:
            pass

    return info


def run_systemctl(action):
    res = subprocess.run(
        ["sudo", "-n", "systemctl", action, SERVICE_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        print(f"[ERROR] systemctl {action} {SERVICE_NAME} failed: {res.stderr.strip()}", file=sys.stderr)
        return False
    return True


def cmd_status(args):
    info = get_status()
    if getattr(args, "json", False):
        print(json.dumps(info, indent=2))
        return

    print("======================================================================")
    print(" uStreamer HTTP Camera Streaming Status")
    print("======================================================================")
    print(f" Systemd Unit:       {info['service']}")
    print(f" Service State:      {'ACTIVE (running)' if info['active'] else 'INACTIVE (stopped)'}")
    print(f" Boot Autostart:     {'ENABLED' if info['enabled'] else 'DISABLED'}")
    print("----------------------------------------------------------------------")
    print(f" V4L2 Source:        {info['device']} ({info['format']} {info['resolution']} @ target {info['desired_fps']} fps)")
    if info["active"]:
        print(f" Source Online:      {'YES' if info['online'] else 'NO'} (captured_fps={info['captured_fps']})")
    print(f" HTTP Listen:        {info['host']}:{info['port']}")
    print(f" Authentication:     {'Basic Auth (user: ' + info['auth_user'] + ')' if info['auth_enabled'] else 'None'}")
    print(f" Stream Endpoint:    http://<host>:{info['port']}/stream")
    print(f" Snapshot Endpoint:  http://<host>:{info['port']}/snapshot")
    print("======================================================================")


def cmd_service_action(action, args):
    if action == "enable":
        if not run_systemctl("enable") or not run_systemctl("start"):
            sys.exit(1)
        time.sleep(0.5)
        print(f"[OK] Enabled and started {SERVICE_NAME}.")
    elif action == "disable":
        if not run_systemctl("stop") or not run_systemctl("disable"):
            sys.exit(1)
        print(f"[OK] Stopped and disabled {SERVICE_NAME}.")
    else:
        if not run_systemctl(action):
            sys.exit(1)
        if action in ("start", "restart"):
            time.sleep(0.5)
        print(f"[OK] Executed '{action}' on {SERVICE_NAME}.")
    cmd_status(args)


def cmd_snapshot(args):
    info = get_status()
    if not info["active"]:
        print(f"[ERROR] {SERVICE_NAME} is not active. Start it first with 'ustreamerctl start'.", file=sys.stderr)
        sys.exit(1)

    out_file = os.path.abspath(args.output or f"/tmp/ustreamer_snapshot_{int(time.time())}.jpg")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    try:
        req = _build_request("/snapshot")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = resp.read()
        with open(out_file, "wb") as f:
            f.write(data)
        size_kb = os.path.getsize(out_file) / 1024.0
        print(f"[SUCCESS] Snapshot saved: {out_file} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"[ERROR] Failed to fetch snapshot from uStreamer: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="uStreamer HTTP Camera Streaming Control CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    sub_status = subparsers.add_parser("status", help="Show uStreamer service and stream status")
    sub_status.add_argument("--json", action="store_true", help="Output status in JSON format")

    for act, desc in (
        ("start", "Start uStreamer service now"),
        ("stop", "Stop uStreamer service now (releases V4L2 camera)"),
        ("restart", "Restart uStreamer service"),
        ("enable", "Enable at boot and start uStreamer service"),
        ("disable", "Stop and disable uStreamer service"),
    ):
        p = subparsers.add_parser(act, help=desc)
        p.add_argument("--json", action="store_true", help="Output status in JSON format")

    sub_snap = subparsers.add_parser("snapshot", help="Fetch an instant JPEG snapshot from uStreamer")
    sub_snap.add_argument("output", nargs="?", default=None, help="Output JPEG path (default: /tmp/ustreamer_snapshot_<ts>.jpg)")

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command in ("start", "stop", "restart", "enable", "disable"):
        cmd_service_action(args.command, args)
    elif args.command == "snapshot":
        cmd_snapshot(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
