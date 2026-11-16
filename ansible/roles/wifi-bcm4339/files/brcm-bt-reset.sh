#!/usr/bin/env bash
# ==============================================================================
# File: /usr/local/sbin/brcm-bt-reset.sh
# Description: Pre-start hardware reset helper for Broadcom BCM4339 (AP6335)
#              Bluetooth UART (/dev/ttymxc6) on TechNexion PICO-PI-IMX7D:
#                1. Ensures the 32.768 kHz CCM_CLKO2 reference clock is enabled
#                   on Kernel 5.x (no-op on Kernel 6.x).
#                2. Unblocks the Bluetooth rfkill switch (GPIO4_IO17 / gpio113).
#                3. Pulses GPIO4_IO18 (gpio114, MX7D_PAD_ECSPI1_MISO, AP6335 BT
#                   reset/enable) 0 -> 1 when sysfs GPIO is available so the
#                   BCM4335C0 controller cleanly enters its 115200-baud ROM
#                   bootloader with the 32.768 kHz reference clock active.
# ==============================================================================
set -euo pipefail

if command -v pkill >/dev/null 2>&1; then
    if pkill -x hciattach 2>/dev/null; then
        sleep 0.3
    fi
fi

/usr/local/sbin/brcm-clko2-enable.py

if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock bluetooth || true
fi

if [[ -w /sys/class/gpio/export || -d /sys/class/gpio/gpio114 ]]; then
    if [[ ! -d /sys/class/gpio/gpio114 ]]; then
        echo 114 > /sys/class/gpio/export 2>/dev/null || true
    fi
    if [[ -d /sys/class/gpio/gpio114 ]]; then
        echo out > /sys/class/gpio/gpio114/direction
        echo 0 > /sys/class/gpio/gpio114/value
        sleep 0.5
        echo 1 > /sys/class/gpio/gpio114/value
        sleep 1.0
    fi
fi
