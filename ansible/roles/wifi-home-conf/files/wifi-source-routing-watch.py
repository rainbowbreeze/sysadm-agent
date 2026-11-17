#!/usr/bin/env python3
"""
Event-driven IPv4 address watcher for WiFi source-based policy routing on
systems without NetworkManager dispatcher.d (e.g. ConnMan on TechNexion Yocto).

Listens on Linux AF_NETLINK (NETLINK_ROUTE, RTMGRP_IPV4_IFADDR) with 0% idle CPU
and invokes `/usr/local/sbin/wifi-source-routing <iface> up|down` whenever the
configured wireless interface acquires, changes, or drops its IPv4 address.
"""

import argparse
import subprocess
import time

RTMGRP_IPV4_IFADDR = 0x10


def current_ipv4_cidr(interface):
    res = subprocess.run(
        ["ip", "-4", "addr", "show", "dev", interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    for line in res.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet" and "scope global" in line:
            return parts[1]
    return ""


def sync_routing(interface, script_path, last_cidr):
    cidr = current_ipv4_cidr(interface)
    if cidr:
        # Wait briefly on new lease so DHCP gateway route is installed before reading routes
        if cidr != last_cidr:
            time.sleep(0.5)
        subprocess.run([script_path, interface, "up"], check=False)
    elif last_cidr:
        subprocess.run([script_path, interface, "down"], check=False)
    return cidr


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Watch IPv4 address events and maintain WiFi source policy routing."
    )
    parser.add_argument("--interface", default="wlan0", help="Wireless interface (default: wlan0)")
    parser.add_argument(
        "--script",
        default="/usr/local/sbin/wifi-source-routing",
        help="Path to wifi-source-routing helper script",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    last_cidr = sync_routing(args.interface, args.script, "")

    try:
        import socket

        sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE)
        sock.bind((0, RTMGRP_IPV4_IFADDR))
    except Exception:
        sock = None

    if sock is not None:
        with sock:
            while True:
                sock.recv(4096)
                last_cidr = sync_routing(args.interface, args.script, last_cidr)
    else:
        while True:
            time.sleep(5.0)
            last_cidr = sync_routing(args.interface, args.script, last_cidr)


if __name__ == "__main__":
    main()
