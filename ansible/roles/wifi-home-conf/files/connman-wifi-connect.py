#!/usr/bin/env python3
"""
Idempotently activates the highest-priority available ConnMan WiFi service
provisioned in /var/lib/connman/wifi.config without exposing SSIDs or
passphrases on the command line.

Prints "UNCHANGED" if already connected to the target profile, or "CONNECTED"
when a new connection (or forced reconnection) succeeds.
"""

import argparse
import re
import subprocess
import sys
import time


def parse_provisioned_ssids(config_path):
    ssids = []
    in_service = False
    with open(config_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                sec = line[1:-1].strip()
                in_service = sec.startswith("service_")
                continue
            if in_service:
                m = re.match(r"^Name\s*=\s*(.+)$", line)
                if m:
                    ssids.append(m.group(1).strip())
    return ssids


def list_connman_services():
    """
    Returns list of tuples: (flags_str, service_id) from `connmanctl services`.
    ConnMan formats lines as:
      `*AO ExampleWiFi          wifi_442c05..._4578616d..._managed_psk`
      `    OtherNet             wifi_442c05..._4f746865..._managed_psk`
    """
    res = subprocess.run(
        ["connmanctl", "services"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    entries = []
    for line in res.stdout.splitlines():
        if len(line) < 5:
            continue
        flags = line[:4].strip()
        parts = line[4:].split()
        if parts:
            service_id = parts[-1]
            entries.append((flags, service_id))
    return entries


def find_service_for_ssid(entries, ssid):
    ssid_hex = ssid.encode("utf-8").hex().lower()
    pattern = re.compile(rf"^wifi_[0-9a-f]+_{re.escape(ssid_hex)}_managed_\S+$", re.IGNORECASE)
    for flags, service_id in entries:
        if pattern.match(service_id):
            return flags, service_id
    return None, None


def is_connected_flag(flags):
    return ("O" in flags) or ("R" in flags)


def has_global_ipv4(interface):
    res = subprocess.run(
        ["ip", "-4", "addr", "show", "dev", interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    for line in res.stdout.splitlines():
        if "inet " in line and "scope global" in line:
            return True
    return False


def wait_for_ipv4(interface, timeout_sec=15):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if has_global_ipv4(interface):
            return True
        time.sleep(1.0)
    return has_global_ipv4(interface)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Activate provisioned ConnMan WiFi profile from /var/lib/connman/wifi.config."
    )
    parser.add_argument(
        "--config",
        default="/var/lib/connman/wifi.config",
        help="Path to ConnMan provisioning .config file",
    )
    parser.add_argument(
        "--interface",
        default="wlan0",
        help="Wireless network interface (default: wlan0)",
    )
    parser.add_argument(
        "--force-reconnect",
        action="store_true",
        help="Reconnect even if already associated (e.g. when wifi.config changed)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    ssids = parse_provisioned_ssids(args.config)
    if not ssids:
        print("No [service_*] Name entries found in", args.config, file=sys.stderr)
        return 1

    subprocess.run(
        ["connmanctl", "enable", "wifi"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    entries = list_connman_services()
    if not args.force_reconnect:
        # If primary SSID is already connected (or fallback is connected and primary is out of range)
        primary_flags, primary_svc = find_service_for_ssid(entries, ssids[0])
        if primary_svc and is_connected_flag(primary_flags) and has_global_ipv4(args.interface):
            print("UNCHANGED")
            return 0
        if primary_svc is None and len(ssids) > 1:
            fb_flags, fb_svc = find_service_for_ssid(entries, ssids[1])
            if fb_svc and is_connected_flag(fb_flags) and has_global_ipv4(args.interface):
                print("UNCHANGED")
                return 0

    # Scan for WiFi networks (retry scan once if target SSID has not appeared yet)
    for attempt in range(2):
        subprocess.run(
            ["connmanctl", "scan", "wifi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        entries = list_connman_services()
        if any(find_service_for_ssid(entries, s)[1] is not None for s in ssids):
            break
        if attempt == 0:
            time.sleep(2.0)

    errors = []
    for ssid in ssids:
        flags, service_id = find_service_for_ssid(entries, ssid)
        if not service_id:
            errors.append(f"SSID '{ssid}' not visible in connmanctl scan")
            continue

        if args.force_reconnect and is_connected_flag(flags):
            subprocess.run(
                ["connmanctl", "disconnect", service_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            time.sleep(1.0)

        if not is_connected_flag(flags) or args.force_reconnect:
            res = subprocess.run(
                ["connmanctl", "connect", service_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if res.returncode != 0 and "Already connected" not in (res.stdout + res.stderr):
                errors.append(f"Failed connecting {service_id}: {(res.stderr or res.stdout).strip()}")
                continue

        if wait_for_ipv4(args.interface, timeout_sec=15):
            print("CONNECTED")
            return 0
        errors.append(f"Timed out waiting for IPv4 lease on {args.interface} for {service_id}")

    print("; ".join(errors), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
