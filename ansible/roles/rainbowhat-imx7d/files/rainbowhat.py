#!/usr/bin/env python3
"""
==============================================================================
File: rainbowhat.py
Remote Path: /opt/rainbowhat/rainbowhat.py
Description: Helper script and library to control all peripherals on the
             Pimoroni Rainbow HAT connected to the TechNexion PICO-PI-IMX7D
             (NXP i.MX7D) host.

Hardware Mapping on TechNexion PICO-PI-IMX7D:
  1. 4-Digit 14-Segment Alphanumeric Display (Holtek HT16K33):
     - I2C Bus:     /dev/i2c-0 (I2C1, 30a20000.i2c)
     - I2C Address: 0x70
  2. BMP280 Temperature & Barometric Pressure Sensor:
     - I2C Bus:     /dev/i2c-0 (I2C1, 30a20000.i2c)
     - I2C Address: 0x77 (Chip ID: 0x58)
  3. 7x APA102 Addressable RGB LEDs (Rainbow Strip):
     - SPI Device:  /dev/spidev2.0 (ECSPI3, 30840000.spi)
  4. 3x Discrete Button Indicator LEDs (Red, Green, Blue):
     - GPIO Controller: gpiochip1 (GPIO2 bank, 30210000.gpio, sysfs base 32)
     - Red LED   (Button A): GPIO2_IO02 -> sysfs gpio34 (line 2, GPIO_P28)
     - Green LED (Button B): GPIO2_IO00 -> sysfs gpio32 (line 0, GPIO_P24)
     - Blue LED  (Button C): GPIO2_IO05 -> sysfs gpio37 (line 5, GPIO_P34)
  5. 3x Capacitive Touch Buttons (A, B, C - AT42QT1070 active-low outputs):
     - Button A: GPIO2_IO03 -> sysfs gpio35 (line 3, GPIO_P30)
     - Button B: GPIO2_IO01 -> sysfs gpio33 (line 1, GPIO_P26)
     - Button C: GPIO2_IO07 -> sysfs gpio39 (line 7, GPIO_P48)
  6. Piezo Buzzer (PWM Speaker):
     - PWM Controller: /sys/class/pwm/pwmchip1/pwm0 (PWM2, 30670000.pwm)
==============================================================================
"""

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
import struct
import sys
import time
from typing import Dict, List, Optional, Tuple

# ==============================================================================
# Hardware Constants & Configuration
# ==============================================================================

# I2C configuration for the HT16K33 4-digit 14-segment display and BMP280 sensor
I2C_BUS_PATH: str = "/dev/i2c-0"
I2C_SLAVE_IOCTL: int = 0x0703
HT16K33_ADDR: int = 0x70
BMP280_ADDR: int = 0x77

# HT16K33 register and command constants
HT16K33_CMD_SYSTEM_SETUP: int = 0x20
HT16K33_OSC_ON: int = 0x01
HT16K33_CMD_DISPLAY_SETUP: int = 0x80
HT16K33_DISPLAY_ON: int = 0x01
HT16K33_CMD_BRIGHTNESS: int = 0xE0

# Blink rate mapping for the HT16K33 display
HT16K33_BLINK_RATES: Dict[str, int] = {
    "off": 0x00,
    "2hz": 0x02,
    "1hz": 0x04,
    "0.5hz": 0x06,
}

# BMP280 register constants
BMP280_REG_CHIP_ID: int = 0xD0
BMP280_EXPECTED_CHIP_ID: int = 0x58
BMP280_REG_CALIB: int = 0x88
BMP280_REG_CTRL_MEAS: int = 0xF4
BMP280_REG_CONFIG: int = 0xF5
BMP280_REG_DATA: int = 0xF7

# SPI configuration for the 7x APA102 RGB LEDs
SPI_DEV_PATH: str = "/dev/spidev2.0"
APA102_NUM_PIXELS: int = 7
APA102_DEFAULT_BRIGHTNESS: int = 15  # Range: 0..31

# Store APA102 pixel state inside the installation directory with restricted 0600
# permissions rather than world-writable /tmp.
APA102_STATE_FILE: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".apa102_state.json"
)

# Sysfs GPIO mapping for the 3 discrete button LEDs on PICO-PI-IMX7D (GPIO2 bank)
GPIO_SYSFS_BASE: str = "/sys/class/gpio"
BUTTON_LED_GPIOS: Dict[str, int] = {
    "red": 34,    # GPIO2_IO02 (GPIO_P28, above Button A)
    "green": 32,  # GPIO2_IO00 (GPIO_P24, above Button B)
    "blue": 37,   # GPIO2_IO05 (GPIO_P34, above Button C)
}

# Sysfs GPIO mapping for the 3 capacitive touch buttons (Active-Low: 0=pressed, 1=released)
TOUCH_BUTTON_GPIOS: Dict[str, int] = {
    "a": 35,  # GPIO2_IO03 (GPIO_P30)
    "b": 33,  # GPIO2_IO01 (GPIO_P26)
    "c": 39,  # GPIO2_IO07 (GPIO_P48)
}

# In-memory cache of verified (pin, direction) -> sysfs value file path (Optimization O3)
_VERIFIED_GPIO_PINS: Dict[Tuple[int, str], str] = {}

# PWM sysfs path for the Piezo Buzzer (PWM2 -> pwmchip1/pwm0)
PIEZO_PWM_CHIP_DIR: str = "/sys/class/pwm/pwmchip1"
PIEZO_PWM_CHANNEL_DIR: str = "/sys/class/pwm/pwmchip1/pwm0"

# Standard musical note frequencies (in Hz) for the piezo buzzer
NOTE_FREQUENCIES: Dict[str, int] = {
    "C4": 262,
    "C#4": 277,
    "D4": 294,
    "D#4": 311,
    "E4": 330,
    "F4": 349,
    "F#4": 370,
    "G4": 392,
    "G#4": 415,
    "A4": 440,
    "A#4": 466,
    "B4": 494,
    "C5": 523,
    "C#5": 554,
    "D5": 587,
    "D#5": 622,
    "E5": 659,
    "F5": 698,
    "F#5": 740,
    "G5": 784,
    "G#5": 831,
    "A5": 880,
    "A#5": 932,
    "B5": 988,
    "C6": 1047,
}

# ==============================================================================
# 14-Segment Alphanumeric Font Table (HT16K33 Quad Alphanumeric Backpack)
# Bit 14 (0x4000) is the decimal point.
# ==============================================================================
DECIMAL_POINT_BIT: int = 0x4000

FONT_14SEG: Dict[str, int] = {
    " ": 0x0000,
    "!": 0x0006,
    '"': 0x0202,
    "#": 0x12CE,
    "$": 0x12ED,
    "%": 0x0C24,
    "&": 0x235D,
    "'": 0x0200,
    "(": 0x2400,
    ")": 0x0900,
    "*": 0x3FC0,
    "+": 0x12C0,
    ",": 0x0800,
    "-": 0x00C0,
    ".": 0x4000,
    "/": 0x0C00,
    "0": 0x0C3F,
    "1": 0x0006,
    "2": 0x00DB,
    "3": 0x008F,
    "4": 0x00E6,
    "5": 0x2069,
    "6": 0x00FD,
    "7": 0x0007,
    "8": 0x00FF,
    "9": 0x00EF,
    ":": 0x1200,
    ";": 0x0A00,
    "<": 0x2400,
    "=": 0x00C8,
    ">": 0x0900,
    "?": 0x1083,
    "@": 0x02BB,
    "A": 0x00F7,
    "B": 0x128F,
    "C": 0x0039,
    "D": 0x120F,
    "E": 0x00F9,
    "F": 0x0071,
    "G": 0x00BD,
    "H": 0x00F6,
    "I": 0x1209,
    "J": 0x001E,
    "K": 0x2470,
    "L": 0x0038,
    "M": 0x0536,
    "N": 0x2136,
    "O": 0x003F,
    "P": 0x00F3,
    "Q": 0x203F,
    "R": 0x20F3,
    "S": 0x00ED,
    "T": 0x1201,
    "U": 0x003E,
    "V": 0x0C30,
    "W": 0x2836,
    "X": 0x2D00,
    "Y": 0x1500,
    "Z": 0x0C09,
    "[": 0x0039,
    "\\": 0x2100,
    "]": 0x000F,
    "^": 0x0C03,
    "_": 0x0008,
    "`": 0x0100,
    "a": 0x1058,
    "b": 0x2078,
    "c": 0x00D8,
    "d": 0x088E,
    "e": 0x0858,
    "f": 0x0071,
    "g": 0x048E,
    "h": 0x1070,
    "i": 0x1000,
    "j": 0x000E,
    "k": 0x3600,
    "l": 0x0030,
    "m": 0x10D4,
    "n": 0x1050,
    "o": 0x00DC,
    "p": 0x0170,
    "q": 0x0486,
    "r": 0x0050,
    "s": 0x2088,
    "t": 0x0078,
    "u": 0x001C,
    "v": 0x2004,
    "w": 0x2814,
    "x": 0x28C0,
    "y": 0x028E,
    "z": 0x0848,
}


# ==============================================================================
# Custom Exception Class & Shared GPIO Helper (D4 + O3)
# ==============================================================================
class RainbowHatError(Exception):
    """Custom exception raised when Rainbow HAT hardware operations fail."""


def ensure_gpio_pin(pin: int, direction: str) -> str:
    """
    Ensures the given sysfs GPIO pin is exported under /sys/class/gpio and
    configured with the requested direction ('in' or 'out').
    Caches verified pins in memory (_VERIFIED_GPIO_PINS) so repeated polling
    does not re-read direction on every call (Optimization O3).
    """
    cache_key = (pin, direction)
    cached_path = _VERIFIED_GPIO_PINS.get(cache_key)
    if cached_path is not None and os.path.exists(cached_path):
        return cached_path

    gpio_dir = os.path.join(GPIO_SYSFS_BASE, f"gpio{pin}")
    value_path = os.path.join(gpio_dir, "value")
    direction_path = os.path.join(gpio_dir, "direction")
    export_path = os.path.join(GPIO_SYSFS_BASE, "export")

    try:
        if not os.path.isdir(gpio_dir):
            with open(export_path, "w", encoding="utf-8") as f_exp:
                f_exp.write(f"{pin}\n")
            time.sleep(0.05)

        if os.path.exists(direction_path):
            with open(direction_path, "r", encoding="utf-8") as f_dir:
                current_dir = f_dir.read().strip()
            if current_dir != direction:
                with open(direction_path, "w", encoding="utf-8") as f_dir_w:
                    f_dir_w.write(f"{direction}\n")
    except PermissionError as exc:
        raise RainbowHatError(
            f"Permission denied configuring GPIO {pin} ({direction}) in {GPIO_SYSFS_BASE}. "
            "Ensure rainbowhat-init.service has run or execute with sudo."
        ) from exc
    except OSError as exc:
        raise RainbowHatError(f"Failed to configure GPIO {pin} ({direction}): {exc}") from exc

    _VERIFIED_GPIO_PINS[cache_key] = value_path
    return value_path


# ==============================================================================
# 1. HT16K33 4-Digit 14-Segment Display Controller
# ==============================================================================
class AlphanumericDisplay:
    """
    Controls the 4-digit 14-segment alphanumeric display (HT16K33 at 0x70)
    over /dev/i2c-0. Caches initialization parameters (Optimization O2) to
    avoid redundant I2C setup writes on every frame during scrolling or clock
    watch updates.
    """

    def __init__(self, bus_path: str = I2C_BUS_PATH, address: int = HT16K33_ADDR) -> None:
        self.bus_path = bus_path
        self.address = address
        self._last_init_config: Optional[Tuple[int, str]] = None

    def _write_i2c(self, payload: bytes) -> None:
        """
        Opens the I2C bus device, binds to the HT16K33 slave address, and writes
        the specified byte sequence with full error handling.
        """
        fd: Optional[int] = None
        try:
            fd = os.open(self.bus_path, os.O_RDWR)
            fcntl.ioctl(fd, I2C_SLAVE_IOCTL, self.address)
            os.write(fd, payload)
        except PermissionError as exc:
            raise RainbowHatError(
                f"Permission denied accessing {self.bus_path}. "
                "Ensure rainbowhat-init.service has run or execute with sudo."
            ) from exc
        except OSError as exc:
            raise RainbowHatError(
                f"I2C communication failed on {self.bus_path} (addr 0x{self.address:02x}): {exc}"
            ) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def initialize(self, brightness: int = 15, blink: str = "off", force: bool = False) -> None:
        """
        Initializes the HT16K33 oscillator, display state, blink frequency, and
        brightness level (0..15). Skips redundant I2C writes if already
        initialized with the same settings in this instance unless force=True.
        """
        if not 0 <= brightness <= 15:
            raise RainbowHatError(f"Display brightness must be between 0 and 15 (got {brightness}).")
        if blink not in HT16K33_BLINK_RATES:
            raise RainbowHatError(
                f"Invalid blink rate '{blink}'. Choose from: {list(HT16K33_BLINK_RATES.keys())}"
            )

        target_cfg = (brightness, blink)
        if not force and self._last_init_config == target_cfg:
            return

        self._write_i2c(bytes([HT16K33_CMD_SYSTEM_SETUP | HT16K33_OSC_ON]))
        self._write_i2c(
            bytes([HT16K33_CMD_DISPLAY_SETUP | HT16K33_DISPLAY_ON | HT16K33_BLINK_RATES[blink]])
        )
        self._write_i2c(bytes([HT16K33_CMD_BRIGHTNESS | (brightness & 0x0F)]))
        self._last_init_config = target_cfg

    @staticmethod
    def encode_string(text: str) -> List[int]:
        """
        Parses an input string into up to 4 16-bit 14-segment character masks,
        automatically attaching '.' decimal points to the preceding character.
        """
        digits: List[int] = []
        for ch in text:
            if ch == "." and digits and not (digits[-1] & DECIMAL_POINT_BIT):
                digits[-1] |= DECIMAL_POINT_BIT
            else:
                if len(digits) >= 4:
                    break
                mask = FONT_14SEG.get(ch, FONT_14SEG.get(ch.upper(), 0x0000))
                digits.append(mask)

        while len(digits) < 4:
            digits.append(0x0000)

        return digits[:4]

    def show_text(self, text: str, brightness: int = 15, blink: str = "off") -> None:
        """
        Displays a 1-to-4 character string (plus optional decimal points) on
        the 4-digit 14-segment display.
        """
        self.initialize(brightness=brightness, blink=blink)
        digits = self.encode_string(text)

        ram_payload = bytearray([0x00])
        for word in digits:
            ram_payload.append(word & 0xFF)
            ram_payload.append((word >> 8) & 0xFF)
        while len(ram_payload) < 17:
            ram_payload.append(0x00)

        self._write_i2c(bytes(ram_payload))

    def show_number(self, value: float, brightness: int = 15, blink: str = "off") -> None:
        """
        Formats and right-aligns a numeric value (int or float) onto the 4-digit
        alphanumeric display.
        """
        if float(value).is_integer():
            formatted = f"{int(value):>4d}"
            if len(formatted) > 4:
                formatted = formatted[-4:]
        else:
            raw = f"{value:.3f}".rstrip("0").rstrip(".")
            non_dot_len = len(raw.replace(".", ""))
            if non_dot_len < 4:
                formatted = (" " * (4 - non_dot_len)) + raw
            else:
                out_chars: List[str] = []
                digit_count = 0
                for ch in raw:
                    if ch == ".":
                        out_chars.append(ch)
                    else:
                        if digit_count >= 4:
                            break
                        out_chars.append(ch)
                        digit_count += 1
                formatted = "".join(out_chars)

        self.show_text(formatted, brightness=brightness, blink=blink)

    def show_time(
        self,
        tz_offset_hours: float = 1.0,
        use_12h: bool = False,
        brightness: int = 15,
        watch_seconds: float = 0.0,
    ) -> str:
        """
        Displays the current time (HH.MM) on the 4-digit display using the
        specified UTC offset in hours (default: +1.0 for CET).
        If watch_seconds > 0, continuously updates the clock with a blinking
        separator dot for the specified duration.
        """
        tz = timezone(timedelta(hours=tz_offset_hours))

        def format_now(show_dot: bool = True) -> str:
            now = datetime.now(tz)
            hour = now.hour
            if use_12h:
                hour = hour % 12 or 12
            sep = "." if show_dot else ""
            return f"{hour:02d}{sep}{now.minute:02d}"

        if watch_seconds <= 0:
            formatted = format_now(show_dot=True)
            self.show_text(formatted, brightness=brightness, blink="off")
            return formatted

        end_time = time.time() + watch_seconds
        dot_state = True
        last_str = ""
        while time.time() < end_time:
            last_str = format_now(show_dot=dot_state)
            self.show_text(last_str, brightness=brightness, blink="off")
            dot_state = not dot_state
            time.sleep(0.5)

        last_str = format_now(show_dot=True)
        self.show_text(last_str, brightness=brightness, blink="off")
        return last_str

    def scroll_text(self, text: str, delay: float = 0.25, brightness: int = 15) -> None:
        """
        Scrolls an arbitrary-length text message across the 4-digit display.
        """
        padded = "    " + text + "    "
        self.initialize(brightness=brightness, blink="off")
        for idx in range(len(padded) - 3):
            window = padded[idx : idx + 8]
            self.show_text(window, brightness=brightness, blink="off")
            time.sleep(max(0.05, delay))

    def clear(self) -> None:
        """
        Clears all segments on the 4-digit display.
        """
        self.initialize(brightness=15, blink="off")
        self._write_i2c(bytes([0x00] + [0x00] * 16))


# ==============================================================================
# 2. Bosch BMP280 Temperature & Pressure Sensor Controller (/dev/i2c-0 @ 0x77)
# ==============================================================================
class BMP280Sensor:
    """
    Reads factory-calibrated temperature (°C / °F) and barometric pressure (hPa)
    from the Bosch BMP280 sensor at I2C address 0x77 on /dev/i2c-0.
    """

    def __init__(self, bus_path: str = I2C_BUS_PATH, address: int = BMP280_ADDR) -> None:
        self.bus_path = bus_path
        self.address = address

    @staticmethod
    def _read_registers(fd: int, reg: int, length: int) -> bytes:
        os.write(fd, bytes([reg & 0xFF]))
        return os.read(fd, length)

    def read(self) -> Dict[str, float]:
        """
        Performs a compensated measurement of Temperature (°C, °F) and Pressure (hPa)
        according to the Bosch BMP280 datasheet compensation formula.
        """
        fd: Optional[int] = None
        try:
            fd = os.open(self.bus_path, os.O_RDWR)
            fcntl.ioctl(fd, I2C_SLAVE_IOCTL, self.address)

            chip_id = self._read_registers(fd, BMP280_REG_CHIP_ID, 1)[0]
            if chip_id != BMP280_EXPECTED_CHIP_ID:
                raise RainbowHatError(
                    f"Unexpected BMP280 chip ID 0x{chip_id:02x} (expected 0x58)."
                )

            calib_raw = self._read_registers(fd, BMP280_REG_CALIB, 24)
            (
                dig_t1,
                dig_t2,
                dig_t3,
                dig_p1,
                dig_p2,
                dig_p3,
                dig_p4,
                dig_p5,
                dig_p6,
                dig_p7,
                dig_p8,
                dig_p9,
            ) = struct.unpack("<HhhHhhhhhhhh", calib_raw)

            os.write(fd, bytes([BMP280_REG_CONFIG, 0x00]))
            os.write(fd, bytes([BMP280_REG_CTRL_MEAS, 0x57]))
            time.sleep(0.05)

            data = self._read_registers(fd, BMP280_REG_DATA, 6)
            adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
            adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)

            var1_t = (((adc_t / 16384.0) - (dig_t1 / 1024.0)) * float(dig_t2))
            var2_t = (
                (((adc_t / 131072.0) - (dig_t1 / 8192.0)) ** 2) * float(dig_t3)
            )
            t_fine = var1_t + var2_t
            temp_c = t_fine / 5120.0
            temp_f = (temp_c * 9.0 / 5.0) + 32.0

            var1_p = (t_fine / 2.0) - 64000.0
            var2_p = var1_p * var1_p * float(dig_p6) / 32768.0
            var2_p = var2_p + var1_p * float(dig_p5) * 2.0
            var2_p = (var2_p / 4.0) + (float(dig_p4) * 65536.0)
            var1_p = (
                (float(dig_p3) * var1_p * var1_p / 524288.0 + float(dig_p2) * var1_p)
                / 524288.0
            )
            var1_p = (1.0 + var1_p / 32768.0) * float(dig_p1)

            if var1_p == 0:
                pressure_hpa = 0.0
            else:
                p_pa = 1048576.0 - float(adc_p)
                p_pa = (p_pa - (var2_p / 4096.0)) * 6250.0 / var1_p
                var1_p = float(dig_p9) * p_pa * p_pa / 2147483648.0
                var2_p = p_pa * float(dig_p8) / 32768.0
                p_pa = p_pa + (var1_p + var2_p + float(dig_p7)) / 16.0
                pressure_hpa = p_pa / 100.0

            return {
                "temperature_c": round(temp_c, 2),
                "temperature_f": round(temp_f, 2),
                "pressure_hpa": round(pressure_hpa, 2),
            }
        except PermissionError as exc:
            raise RainbowHatError(
                f"Permission denied accessing {self.bus_path}. "
                "Ensure rainbowhat-init.service has run or execute with sudo."
            ) from exc
        except OSError as exc:
            raise RainbowHatError(
                f"BMP280 I2C read failed on {self.bus_path} (addr 0x{self.address:02x}): {exc}"
            ) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


# ==============================================================================
# 3. Discrete Button Indicator LEDs Controller (Red, Green, Blue)
# ==============================================================================
class ButtonLeds:
    """
    Controls the 3 discrete indicator LEDs (Red=gpio34, Green=gpio32, Blue=gpio37)
    via Linux sysfs GPIO (/sys/class/gpio) using the shared ensure_gpio_pin helper.
    """

    def get_state(self, color: str) -> int:
        """
        Reads the current state (0 or 1) of the specified LED ('red', 'green', 'blue').
        """
        color_key = color.lower()
        if color_key not in BUTTON_LED_GPIOS:
            raise RainbowHatError(f"Unknown LED '{color}'. Choose from: red, green, blue.")
        pin = BUTTON_LED_GPIOS[color_key]
        value_path = ensure_gpio_pin(pin, "out")
        try:
            with open(value_path, "r", encoding="utf-8") as f_val:
                return 1 if f_val.read().strip() == "1" else 0
        except OSError as exc:
            raise RainbowHatError(f"Failed reading LED '{color}' (GPIO {pin}): {exc}") from exc

    def set_state(self, color: str, state: str) -> None:
        """
        Sets one LED ('red', 'green', 'blue') or 'all' LEDs to 'on', 'off', or 'toggle'.
        """
        color_key = color.lower()
        state_key = state.lower()

        if color_key == "all":
            targets = ["red", "green", "blue"]
        elif color_key in BUTTON_LED_GPIOS:
            targets = [color_key]
        else:
            raise RainbowHatError(
                f"Unknown LED target '{color}'. Choose from: red, green, blue, all."
            )

        for target in targets:
            pin = BUTTON_LED_GPIOS[target]
            value_path = ensure_gpio_pin(pin, "out")
            if state_key in ("on", "1", "true", "high"):
                new_val = "1"
            elif state_key in ("off", "0", "false", "low"):
                new_val = "0"
            elif state_key == "toggle":
                current = self.get_state(target)
                new_val = "0" if current == 1 else "1"
            else:
                raise RainbowHatError(
                    f"Invalid LED state '{state}'. Choose from: on, off, toggle."
                )

            try:
                with open(value_path, "w", encoding="utf-8") as f_val:
                    f_val.write(f"{new_val}\n")
            except PermissionError as exc:
                raise RainbowHatError(
                    f"Permission denied writing to {value_path}. "
                    "Ensure rainbowhat-init.service has run or execute with sudo."
                ) from exc
            except OSError as exc:
                raise RainbowHatError(
                    f"Failed setting LED '{target}' (GPIO {pin}) to {new_val}: {exc}"
                ) from exc

    def set_rgb(self, red_on: int, green_on: int, blue_on: int) -> None:
        """
        Sets the Red, Green, and Blue indicator LEDs simultaneously (0=off, 1=on).
        """
        self.set_state("red", "on" if red_on else "off")
        self.set_state("green", "on" if green_on else "off")
        self.set_state("blue", "on" if blue_on else "off")


# ==============================================================================
# 4. Capacitive Touch Buttons Controller (Buttons A, B, C)
# ==============================================================================
class TouchButtons:
    """
    Reads the 3 capacitive touch buttons (A=gpio35, B=gpio33, C=gpio39) using
    the shared ensure_gpio_pin helper (with cached pin verification).
    Active-low: physical '0' -> PRESSED (True), '1' -> RELEASED (False).
    """

    def is_pressed(self, button: str) -> bool:
        """
        Returns True if the specified button ('a', 'b', or 'c') is currently touched.
        """
        btn_key = button.lower()
        if btn_key not in TOUCH_BUTTON_GPIOS:
            raise RainbowHatError(f"Unknown button '{button}'. Choose from: a, b, c.")
        pin = TOUCH_BUTTON_GPIOS[btn_key]
        value_path = ensure_gpio_pin(pin, "in")
        try:
            with open(value_path, "r", encoding="utf-8") as f_val:
                raw_val = f_val.read().strip()
            return raw_val == "0"
        except OSError as exc:
            raise RainbowHatError(f"Failed reading Button '{button.upper()}': {exc}") from exc

    def read_all(self) -> Dict[str, bool]:
        """
        Returns a dictionary with the pressed state of buttons A, B, and C.
        """
        return {
            "A": self.is_pressed("a"),
            "B": self.is_pressed("b"),
            "C": self.is_pressed("c"),
        }


# ==============================================================================
# 5. Piezo Buzzer PWM Controller (/sys/class/pwm/pwmchip1/pwm0)
# ==============================================================================
class PiezoBuzzer:
    """
    Controls the Rainbow HAT piezo buzzer via Linux sysfs PWM
    (/sys/class/pwm/pwmchip1/pwm0 on PICO-PI-IMX7D).
    """

    def __init__(
        self,
        chip_dir: str = PIEZO_PWM_CHIP_DIR,
        channel_dir: str = PIEZO_PWM_CHANNEL_DIR,
    ) -> None:
        self.chip_dir = chip_dir
        self.channel_dir = channel_dir

    def _ensure_exported(self) -> None:
        try:
            if not os.path.isdir(self.channel_dir):
                export_path = os.path.join(self.chip_dir, "export")
                with open(export_path, "w", encoding="utf-8") as f_exp:
                    f_exp.write("0\n")
                time.sleep(0.05)
        except PermissionError as exc:
            raise RainbowHatError(
                f"Permission denied exporting PWM in {self.chip_dir}. "
                "Ensure rainbowhat-init.service has run or execute with sudo."
            ) from exc
        except OSError as exc:
            raise RainbowHatError(f"Failed initializing PWM in {self.chip_dir}: {exc}") from exc

    def _write_attr(self, attr: str, value: str) -> None:
        path = os.path.join(self.channel_dir, attr)
        try:
            with open(path, "w", encoding="utf-8") as f_attr:
                f_attr.write(f"{value}\n")
        except PermissionError as exc:
            raise RainbowHatError(
                f"Permission denied writing to {path}. Ensure rainbowhat-init.service has run or execute with sudo."
            ) from exc
        except OSError as exc:
            raise RainbowHatError(f"Failed writing '{value}' to {path}: {exc}") from exc

    def play_tone(self, freq_hz: float, duration: float = 0.3) -> None:
        """
        Plays a square-wave tone (50% duty cycle) at `freq_hz` Hz.
        """
        if freq_hz <= 0:
            self.stop()
            return

        self._ensure_exported()
        period_ns = int(1_000_000_000 / freq_hz)
        duty_ns = period_ns // 2

        try:
            self._write_attr("duty_cycle", "0")
        except RainbowHatError:
            pass
        self._write_attr("period", str(period_ns))
        self._write_attr("duty_cycle", str(duty_ns))
        self._write_attr("enable", "1")

        if duration > 0:
            time.sleep(duration)
            self.stop()

    def play_note(self, note: str, duration: float = 0.3) -> None:
        """
        Plays a named musical note (e.g. 'C4', 'E4', 'G4', 'C5').
        """
        key = note.upper()
        if key not in NOTE_FREQUENCIES:
            raise RainbowHatError(
                f"Unknown musical note '{note}'. Supported notes: {', '.join(NOTE_FREQUENCIES.keys())}"
            )
        self.play_tone(NOTE_FREQUENCIES[key], duration=duration)

    def stop(self) -> None:
        """
        Disables the PWM output to silence the piezo buzzer.
        """
        self._ensure_exported()
        self._write_attr("enable", "0")


# ==============================================================================
# 6. 7x APA102 Addressable RGB Strip Controller (Rainbow Strip)
# ==============================================================================
class RainbowStrip:
    """
    Controls the 7 APA102 addressable RGB LEDs on the Rainbow HAT via
    /dev/spidev2.0. Persists pixel state in .apa102_state.json
    with restricted 0600 permissions.
    """

    def __init__(self, spi_path: str = SPI_DEV_PATH, state_file: str = APA102_STATE_FILE) -> None:
        self.spi_path = spi_path
        self.state_file = state_file
        self.pixels: List[Tuple[int, int, int, int]] = self._load_state()

    def _load_state(self) -> List[Tuple[int, int, int, int]]:
        default_pixels = [(0, 0, 0, APA102_DEFAULT_BRIGHTNESS) for _ in range(APA102_NUM_PIXELS)]
        if not os.path.exists(self.state_file):
            return default_pixels
        try:
            with open(self.state_file, "r", encoding="utf-8") as f_state:
                data = json.load(f_state)
            if isinstance(data, list) and len(data) == APA102_NUM_PIXELS:
                return [
                    (
                        int(p[0]) & 0xFF,
                        int(p[1]) & 0xFF,
                        int(p[2]) & 0xFF,
                        max(0, min(31, int(p[3]))),
                    )
                    for p in data
                ]
        except Exception:
            pass
        return default_pixels

    def _save_state(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f_state:
                json.dump(self.pixels, f_state)
            os.chmod(self.state_file, 0o600)
        except OSError:
            pass

    def show(self) -> None:
        frame = bytearray([0x00, 0x00, 0x00, 0x00])
        for r, g, b, brightness in self.pixels:
            header = 0xE0 | (brightness & 0x1F)
            frame.extend([header, b & 0xFF, g & 0xFF, r & 0xFF])
        frame.extend([0x00, 0x00, 0x00, 0x00])

        fd: Optional[int] = None
        try:
            fd = os.open(self.spi_path, os.O_RDWR)
            os.write(fd, bytes(frame))
        except PermissionError as exc:
            raise RainbowHatError(
                f"Permission denied accessing {self.spi_path}. "
                "Ensure rainbowhat-init.service has run or execute with sudo."
            ) from exc
        except OSError as exc:
            raise RainbowHatError(
                f"SPI communication failed on {self.spi_path}: {exc}"
            ) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        self._save_state()

    def set_pixel(
        self,
        index: int,
        r: int,
        g: int,
        b: int,
        brightness: int = APA102_DEFAULT_BRIGHTNESS,
        auto_show: bool = True,
    ) -> None:
        if not 0 <= index < APA102_NUM_PIXELS:
            raise RainbowHatError(
                f"Pixel index must be between 0 and {APA102_NUM_PIXELS - 1} (got {index})."
            )
        for channel_name, val in (("R", r), ("G", g), ("B", b)):
            if not 0 <= val <= 255:
                raise RainbowHatError(
                    f"{channel_name} color value must be between 0 and 255 (got {val})."
                )
        if not 0 <= brightness <= 31:
            raise RainbowHatError(
                f"APA102 brightness must be between 0 and 31 (got {brightness})."
            )

        self.pixels[index] = (r, g, b, brightness)
        if auto_show:
            self.show()

    def set_all(
        self, r: int, g: int, b: int, brightness: int = APA102_DEFAULT_BRIGHTNESS
    ) -> None:
        for idx in range(APA102_NUM_PIXELS):
            self.set_pixel(idx, r, g, b, brightness=brightness, auto_show=False)
        self.show()

    def set_rainbow_preset(self, brightness: int = APA102_DEFAULT_BRIGHTNESS) -> None:
        rainbow_colors: List[Tuple[int, int, int]] = [
            (148, 0, 211),  # Pixel 0 (Right): Violet
            (75, 0, 130),   # Pixel 1: Indigo
            (0, 0, 255),    # Pixel 2: Blue
            (0, 255, 0),    # Pixel 3 (Center): Green
            (255, 255, 0),  # Pixel 4: Yellow
            (255, 127, 0),  # Pixel 5: Orange
            (255, 0, 0),    # Pixel 6 (Left): Red
        ]
        for idx, (r, g, b) in enumerate(rainbow_colors):
            self.set_pixel(idx, r, g, b, brightness=brightness, auto_show=False)
        self.show()

    def clear(self) -> None:
        self.set_all(0, 0, 0, brightness=0)


# ==============================================================================
# Hardware Status & Diagnostic Routine
# ==============================================================================
def run_status_check() -> int:
    """
    Probes all Rainbow HAT hardware interfaces on the host and prints a status report.
    """
    print("======================================================================")
    print(" Rainbow HAT Hardware & Sensor Status on TechNexion PICO-PI-IMX7D")
    print("======================================================================")

    # 1. Check I2C Display (0x70 HT16K33)
    try:
        fd = os.open(I2C_BUS_PATH, os.O_RDWR)
        try:
            fcntl.ioctl(fd, I2C_SLAVE_IOCTL, HT16K33_ADDR)
            os.write(fd, bytes([HT16K33_CMD_SYSTEM_SETUP | HT16K33_OSC_ON]))
            ht16k33_status = "DETECTED & READY (0x70 on /dev/i2c-0)"
        except OSError as exc:
            ht16k33_status = f"ERROR ({exc})"
        finally:
            os.close(fd)
    except OSError as exc:
        ht16k33_status = f"BUS ERROR ({exc})"
    print(f"  [I2C Display] HT16K33 14-Seg : {ht16k33_status}")

    # 2. Check & Read BMP280 Temperature/Pressure Sensor (0x77)
    try:
        reading = BMP280Sensor().read()
        bmp280_status = (
            f"OK -> Temp: {reading['temperature_c']:.2f} °C ({reading['temperature_f']:.2f} °F), "
            f"Pressure: {reading['pressure_hpa']:.2f} hPa"
        )
    except RainbowHatError as exc:
        bmp280_status = f"ERROR ({exc})"
    print(f"  [I2C Sensor ] BMP280 (0x77)  : {bmp280_status}")

    # 3. Check SPI APA102 strip (/dev/spidev2.0)
    if os.path.exists(SPI_DEV_PATH) and os.access(SPI_DEV_PATH, os.R_OK | os.W_OK):
        spi_status = f"READY ({SPI_DEV_PATH}, writable)"
    elif os.path.exists(SPI_DEV_PATH):
        spi_status = f"PRESENT ({SPI_DEV_PATH}, requires rainbowhat-init.service or sudo)"
    else:
        spi_status = f"MISSING ({SPI_DEV_PATH})"
    print(f"  [SPI Strip  ] 7x APA102 LEDs : {spi_status}")

    # 4. Check Discrete Button LEDs (Red=34, Green=32, Blue=37)
    leds = ButtonLeds()
    for name, pin in BUTTON_LED_GPIOS.items():
        try:
            val = leds.get_state(name)
            state_str = "ON (1)" if val == 1 else "OFF (0)"
            print(f"  [Button LED ] {name.upper():<5} (gpio{pin}) : {state_str}")
        except RainbowHatError as exc:
            print(f"  [Button LED ] {name.upper():<5} (gpio{pin}) : ERROR ({exc})")

    # 5. Check Capacitive Touch Buttons (A=35, B=33, C=39)
    buttons = TouchButtons()
    for btn_label, pin in TOUCH_BUTTON_GPIOS.items():
        try:
            pressed = buttons.is_pressed(btn_label)
            btn_str = "PRESSED" if pressed else "RELEASED"
            print(f"  [Touch Btn  ] BTN {btn_label.upper()} (gpio{pin}) : {btn_str}")
        except RainbowHatError as exc:
            print(f"  [Touch Btn  ] BTN {btn_label.upper()} (gpio{pin}) : ERROR ({exc})")

    # 6. Check Piezo Buzzer PWM (/sys/class/pwm/pwmchip1)
    if os.path.isdir(PIEZO_PWM_CHIP_DIR):
        pwm_status = f"READY ({PIEZO_PWM_CHANNEL_DIR})"
    else:
        pwm_status = f"MISSING ({PIEZO_PWM_CHIP_DIR})"
    print(f"  [PWM Buzzer ] Piezo Speaker  : {pwm_status}")

    print("======================================================================")
    return 0


# ==============================================================================
# Demo Sequence
# ==============================================================================
def run_demo() -> None:
    """
    Runs an interactive demonstration of all Rainbow HAT peripherals.
    """
    display = AlphanumericDisplay()
    leds = ButtonLeds()
    strip = RainbowStrip()
    sensor = BMP280Sensor()

    print("[Demo] 1/4: Testing Red, Green, and Blue indicator LEDs...")
    leds.set_state("all", "off")
    for color, label in (("red", "RED "), ("green", "GRN "), ("blue", "BLUE")):
        display.show_text(label)
        leds.set_state(color, "on")
        time.sleep(0.5)
        leds.set_state(color, "off")

    print("[Demo] 2/4: Lighting up the 7-pixel APA102 Rainbow arch...")
    strip.set_rainbow_preset(brightness=10)
    leds.set_state("all", "on")
    display.show_text("RAIN")
    time.sleep(0.6)
    display.show_text("BOW ")
    time.sleep(0.6)

    print("[Demo] 3/4: Reading BMP280 temperature & displaying it...")
    reading = sensor.read()
    temp_str = f"{reading['temperature_c']:.1f}C"
    print(
        f"       BMP280 Temperature: {reading['temperature_c']:.2f} °C, "
        f"Pressure: {reading['pressure_hpa']:.2f} hPa"
    )
    display.show_text(temp_str)
    time.sleep(1.2)

    print("[Demo] 4/4: Showing current local time on 4-digit display...")
    shown_time = display.show_time(tz_offset_hours=1.0)
    print(f"       Displayed Time: {shown_time}")


# ==============================================================================
# CLI Argument Parser & Entrypoint
# ==============================================================================
def build_parser() -> argparse.ArgumentParser:
    """
    Constructs the command-line argument parser for rainbowhat.py.
    """
    parser = argparse.ArgumentParser(
        prog="rainbowhat",
        description=(
            "Control the Pimoroni Rainbow HAT lights, 4-digit display, "
            "BMP280 sensor, capacitive touch buttons, and piezo buzzer."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- status ---
    subparsers.add_parser("status", help="Check all Rainbow HAT hardware and sensor states")

    # --- display ---
    disp_parser = subparsers.add_parser(
        "display", help="Control the 4-digit 14-segment alphanumeric display"
    )
    disp_sub = disp_parser.add_subparsers(dest="display_cmd", required=True)

    disp_text = disp_sub.add_parser("text", help="Show a 1-4 character string (supports '.')")
    disp_text.add_argument("text", type=str, help="Text string to display (e.g. 'HI!', '12.34')")
    disp_text.add_argument(
        "--brightness", "-b", type=int, default=15, help="Brightness 0..15 (default: 15)"
    )
    disp_text.add_argument(
        "--blink",
        choices=["off", "2hz", "1hz", "0.5hz"],
        default="off",
        help="Hardware blink rate (default: off)",
    )

    disp_num = disp_sub.add_parser("number", help="Show an integer or float number")
    disp_num.add_argument("value", type=float, help="Numeric value to display (e.g. 42, 23.5)")
    disp_num.add_argument(
        "--brightness", "-b", type=int, default=15, help="Brightness 0..15 (default: 15)"
    )
    disp_num.add_argument(
        "--blink",
        choices=["off", "2hz", "1hz", "0.5hz"],
        default="off",
        help="Hardware blink rate (default: off)",
    )

    disp_time = disp_sub.add_parser("time", help="Show the current time (HH.MM) on the display")
    disp_time.add_argument(
        "--tz-offset",
        type=float,
        default=1.0,
        help="Timezone offset from UTC in hours (default: 1.0 for CET)",
    )
    disp_time.add_argument(
        "--12h", dest="use_12h", action="store_true", help="Use 12-hour clock format"
    )
    disp_time.add_argument(
        "--watch",
        type=float,
        default=0.0,
        help="Continuously update clock with blinking dot for N seconds (default: 0 = one-shot)",
    )
    disp_time.add_argument(
        "--brightness", "-b", type=int, default=15, help="Brightness 0..15 (default: 15)"
    )

    disp_scroll = disp_sub.add_parser("scroll", help="Scroll a message across the 4-digit display")
    disp_scroll.add_argument("text", type=str, help="Message string to scroll")
    disp_scroll.add_argument(
        "--delay", "-d", type=float, default=0.25, help="Scroll step delay in seconds (default: 0.25)"
    )
    disp_scroll.add_argument(
        "--brightness", "-b", type=int, default=15, help="Brightness 0..15 (default: 15)"
    )

    disp_sub.add_parser("clear", help="Clear the 4-digit display")

    # --- sensor (BMP280 temperature & pressure) ---
    sens_parser = subparsers.add_parser(
        "sensor", help="Read the BMP280 temperature and barometric pressure sensor"
    )
    sens_sub = sens_parser.add_subparsers(dest="sensor_cmd", required=True)

    sens_read = sens_sub.add_parser("read", help="Read temperature (°C/°F) and pressure (hPa)")
    sens_read.add_argument("--json", action="store_true", help="Output reading as JSON")
    sens_read.add_argument(
        "--show-temp",
        action="store_true",
        help="Also display the temperature (e.g. '25.4C') on the 4-digit display",
    )
    sens_read.add_argument(
        "--show-pressure",
        action="store_true",
        help="Also display the pressure in hPa on the 4-digit display",
    )

    # --- button (Capacitive touch buttons A, B, C) ---
    btn_parser = subparsers.add_parser(
        "button", help="Read or watch the 3 capacitive touch buttons (A, B, C)"
    )
    btn_sub = btn_parser.add_subparsers(dest="button_cmd", required=True)

    btn_read = btn_sub.add_parser("read", help="Read current state of Buttons A, B, and C")
    btn_read.add_argument("--json", action="store_true", help="Output states as JSON")

    btn_watch = btn_sub.add_parser(
        "watch",
        help="Monitor buttons for N seconds, lighting LEDs and updating the display when pressed",
    )
    btn_watch.add_argument(
        "--duration", "-d", type=float, default=10.0, help="Duration to watch in seconds (default: 10)"
    )

    # --- buzzer (Piezo speaker PWM) ---
    buz_parser = subparsers.add_parser("buzzer", help="Control the PWM piezo buzzer")
    buz_sub = buz_parser.add_subparsers(dest="buzzer_cmd", required=True)

    buz_tone = buz_sub.add_parser("tone", help="Play a tone at the given frequency in Hz")
    buz_tone.add_argument("freq", type=float, help="Frequency in Hz (e.g. 440)")
    buz_tone.add_argument(
        "--duration", "-d", type=float, default=0.3, help="Duration in seconds (default: 0.3)"
    )

    buz_note = buz_sub.add_parser("note", help="Play a musical note (e.g. C4, E4, G4, C5)")
    buz_note.add_argument("note", type=str, help="Musical note name (C4..C6)")
    buz_note.add_argument(
        "--duration", "-d", type=float, default=0.3, help="Duration in seconds (default: 0.3)"
    )

    buz_sub.add_parser("melody", help="Play a short musical chime on the piezo buzzer")
    buz_sub.add_parser("stop", help="Stop/silence the piezo buzzer")

    # --- led (Red, Green, Blue button LEDs) ---
    led_parser = subparsers.add_parser(
        "led", help="Control the 3 discrete button LEDs (red, green, blue)"
    )
    led_sub = led_parser.add_subparsers(dest="led_cmd", required=True)

    led_set = led_sub.add_parser("set", help="Set red, green, blue, or all to on/off/toggle")
    led_set.add_argument(
        "color", choices=["red", "green", "blue", "all"], help="Target LED color or 'all'"
    )
    led_set.add_argument("state", choices=["on", "off", "toggle"], help="Desired state")

    led_rgb = led_sub.add_parser("rgb", help="Set Red, Green, and Blue states simultaneously (0 or 1)")
    led_rgb.add_argument("red", type=int, choices=[0, 1], help="Red LED state (0 or 1)")
    led_rgb.add_argument("green", type=int, choices=[0, 1], help="Green LED state (0 or 1)")
    led_rgb.add_argument("blue", type=int, choices=[0, 1], help="Blue LED state (0 or 1)")

    # --- rainbow (7x APA102 RGB strip) ---
    rb_parser = subparsers.add_parser(
        "rainbow", help="Control the 7 APA102 addressable RGB LEDs"
    )
    rb_sub = rb_parser.add_subparsers(dest="rainbow_cmd", required=True)

    rb_set = rb_sub.add_parser("set", help="Set one pixel (0..6) or 'all' to an RGB color")
    rb_set.add_argument("target", type=str, help="Pixel index (0..6) or 'all'")
    rb_set.add_argument("r", type=int, help="Red value (0..255)")
    rb_set.add_argument("g", type=int, help="Green value (0..255)")
    rb_set.add_argument("b", type=int, help="Blue value (0..255)")
    rb_set.add_argument(
        "--brightness", "-b", type=int, default=APA102_DEFAULT_BRIGHTNESS, help="Brightness 0..31"
    )

    rb_preset = rb_sub.add_parser("preset", help="Display a 7-color rainbow gradient across the strip")
    rb_preset.add_argument(
        "--brightness", "-b", type=int, default=APA102_DEFAULT_BRIGHTNESS, help="Brightness 0..31"
    )

    rb_sub.add_parser("clear", help="Turn off all 7 APA102 RGB LEDs")

    # --- demo & off/clear ---
    subparsers.add_parser("demo", help="Run a visual demonstration of LEDs, sensor, and display")
    subparsers.add_parser("off", help="Turn off all LEDs, buzzer, and clear the 4-digit display")
    subparsers.add_parser("clear", help="Alias for 'off': turn off all LEDs and clear display")

    return parser


def main() -> int:
    """
    Main CLI dispatcher with top-level error handling block.
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "status":
            return run_status_check()

        if args.command == "display":
            display = AlphanumericDisplay()
            if args.display_cmd == "text":
                display.show_text(args.text, brightness=args.brightness, blink=args.blink)
            elif args.display_cmd == "number":
                display.show_number(args.value, brightness=args.brightness, blink=args.blink)
            elif args.display_cmd == "time":
                shown = display.show_time(
                    tz_offset_hours=args.tz_offset,
                    use_12h=args.use_12h,
                    brightness=args.brightness,
                    watch_seconds=args.watch,
                )
                print(f"Displayed time: {shown}")
            elif args.display_cmd == "scroll":
                display.scroll_text(args.text, delay=args.delay, brightness=args.brightness)
            elif args.display_cmd == "clear":
                display.clear()
            return 0

        if args.command == "sensor":
            sensor = BMP280Sensor()
            data = sensor.read()
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print(
                    f"Temperature : {data['temperature_c']:.2f} °C ({data['temperature_f']:.2f} °F)\n"
                    f"Pressure    : {data['pressure_hpa']:.2f} hPa"
                )
            if args.show_temp:
                AlphanumericDisplay().show_text(f"{data['temperature_c']:.1f}C")
            elif args.show_pressure:
                AlphanumericDisplay().show_number(round(data["pressure_hpa"]))
            return 0

        if args.command == "button":
            buttons = TouchButtons()
            if args.button_cmd == "read":
                states = buttons.read_all()
                if args.json:
                    print(json.dumps(states, indent=2))
                else:
                    for k, v in states.items():
                        print(f"Button {k}: {'PRESSED' if v else 'RELEASED'}")
            elif args.button_cmd == "watch":
                leds = ButtonLeds()
                display = AlphanumericDisplay()
                print(f"Watching Touch Buttons A, B, C for {args.duration}s...")
                end_t = time.time() + args.duration
                last_state = None
                while time.time() < end_t:
                    states = buttons.read_all()
                    if states != last_state:
                        leds.set_rgb(
                            1 if states["A"] else 0,
                            1 if states["B"] else 0,
                            1 if states["C"] else 0,
                        )
                        if states["A"]:
                            display.show_text("BTNA")
                            print("Button A PRESSED")
                        elif states["B"]:
                            display.show_text("BTNB")
                            print("Button B PRESSED")
                        elif states["C"]:
                            display.show_text("BTNC")
                            print("Button C PRESSED")
                        last_state = states
                    time.sleep(0.05)
            return 0

        if args.command == "buzzer":
            buzzer = PiezoBuzzer()
            if args.buzzer_cmd == "tone":
                buzzer.play_tone(args.freq, duration=args.duration)
            elif args.buzzer_cmd == "note":
                buzzer.play_note(args.note, duration=args.duration)
            elif args.buzzer_cmd == "melody":
                for note_name, dur in [("C5", 0.15), ("E5", 0.15), ("G5", 0.15), ("C6", 0.3)]:
                    buzzer.play_note(note_name, duration=dur)
                    time.sleep(0.05)
            elif args.buzzer_cmd == "stop":
                buzzer.stop()
            return 0

        if args.command == "led":
            leds = ButtonLeds()
            if args.led_cmd == "set":
                leds.set_state(args.color, args.state)
            elif args.led_cmd == "rgb":
                leds.set_rgb(args.red, args.green, args.blue)
            return 0

        if args.command == "rainbow":
            strip = RainbowStrip()
            if args.rainbow_cmd == "set":
                if args.target.lower() == "all":
                    strip.set_all(args.r, args.g, args.b, brightness=args.brightness)
                else:
                    try:
                        idx = int(args.target)
                    except ValueError as exc:
                        raise RainbowHatError(
                            f"Invalid pixel target '{args.target}'. Must be 0..6 or 'all'."
                        ) from exc
                    strip.set_pixel(idx, args.r, args.g, args.b, brightness=args.brightness)
            elif args.rainbow_cmd == "preset":
                strip.set_rainbow_preset(brightness=args.brightness)
            elif args.rainbow_cmd == "clear":
                strip.clear()
            return 0

        if args.command == "demo":
            run_demo()
            return 0

        if args.command in ("off", "clear"):
            AlphanumericDisplay().clear()
            ButtonLeds().set_state("all", "off")
            RainbowStrip().clear()
            try:
                PiezoBuzzer().stop()
            except RainbowHatError:
                pass
            return 0

    except RainbowHatError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
