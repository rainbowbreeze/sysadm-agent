#!/usr/bin/env bash
# ==============================================================================
# File: /usr/local/sbin/brcm-bt-reset.sh
# Description: Pre-start hardware reset helper for Broadcom BCM4339 (AP6335)
#              Bluetooth UART (/dev/ttymxc6) on TechNexion PICO-PI-IMX7D (6.x):
#                1. Terminates any stray hciattach process holding /dev/ttymxc6.
#                2. Power-cycles the Bluetooth rfkill switch (GPIO4_IO17,
#                   rfkill-gpio shutdown-gpios) via block -> unblock.
#                3. Pulses GPIO4_IO18 (30230000.gpio line 18, AP6335 BT_RST_N)
#                   0 -> 1 so the BCM4335C0 controller cleanly enters its
#                   115200-baud ROM bootloader on both cold boot and restarts.
# ==============================================================================
set -euo pipefail

if command -v pkill >/dev/null 2>&1; then
    if pkill -x hciattach 2>/dev/null; then
        sleep 0.3
    fi
fi

if command -v rfkill >/dev/null 2>&1; then
    rfkill block bluetooth || true
    sleep 0.2
    rfkill unblock bluetooth || true
fi

BT_RST_GPIO=""
for chip in /sys/class/gpio/gpiochip*; do
    [[ -f "$chip/label" && -f "$chip/base" ]] || continue
    if [[ "$(cat "$chip/label")" == "30230000.gpio" ]]; then
        BT_RST_GPIO="$(( $(cat "$chip/base") + 18 ))"
        break
    fi
done

if [[ -n "$BT_RST_GPIO" && -w /sys/class/gpio/export ]]; then
    if [[ ! -d "/sys/class/gpio/gpio${BT_RST_GPIO}" ]]; then
        echo "$BT_RST_GPIO" > /sys/class/gpio/export 2>/dev/null || true
    fi
    if [[ -d "/sys/class/gpio/gpio${BT_RST_GPIO}" ]]; then
        echo out > "/sys/class/gpio/gpio${BT_RST_GPIO}/direction"
        echo 0 > "/sys/class/gpio/gpio${BT_RST_GPIO}/value"
        sleep 0.3
        echo 1 > "/sys/class/gpio/gpio${BT_RST_GPIO}/value"
        sleep 0.8
    fi
else
    sleep 0.5
fi
