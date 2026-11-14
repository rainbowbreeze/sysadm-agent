# `rainbowhat-imx7d` — Pimoroni Rainbow HAT on TechNexion PICO-PI-IMX7D (NXP i.MX7D)

This module configures a **TechNexion PICO-PI-IMX7D** (`NXP i.MX7D`) Debian/Ubuntu machine for the **Pimoroni Rainbow HAT** and deploys the pure-Python driver and CLI (`/opt/rainbowhat/rainbowhat.py`, symlinked at `/usr/local/bin/rainbowhat`).

> **Note**: For **Raspberry Pi** hardware (`RPi.GPIO` / BCM pinout), use the [`rainbowhat-raspberry`](../rainbowhat-raspberry/README.md) module instead.

---

## 1. Hardware Mapping on TechNexion PICO-PI-IMX7D

Unlike a Raspberry Pi (which uses `/dev/i2c-1` and Broadcom BCM GPIO pins), the TechNexion PICO-PI-IMX7D routes the 40-pin HAT header to NXP i.MX7D controllers:

| Peripheral | Controller / Device Path | Details |
| :--- | :--- | :--- |
| **4-Digit 14-Segment Display (Holtek HT16K33)** | `/dev/i2c-0` (`30a20000.i2c`) | I2C Slave Address **`0x70`** |
| **BMP280 Temperature & Pressure Sensor** | `/dev/i2c-0` (`30a20000.i2c`) | I2C Slave Address **`0x77`** (Chip ID `0x58`) |
| **7x APA102 Addressable RGB LEDs** | `/dev/spidev2.0` (`30840000.spi`) | ECSPI3 hardware SPI; state persisted in `/opt/rainbowhat/.apa102_state.json` |
| **Red Button LED (above Button A)** | `/sys/class/gpio/gpio34` | `gpiochip1` (`GPIO2_IO02`, line 2, `GPIO_P28`, output) |
| **Green Button LED (above Button B)** | `/sys/class/gpio/gpio32` | `gpiochip1` (`GPIO2_IO00`, line 0, `GPIO_P24`, output) |
| **Blue Button LED (above Button C)** | `/sys/class/gpio/gpio37` | `gpiochip1` (`GPIO2_IO05`, line 5, `GPIO_P34`, output) |
| **Capacitive Touch Button A** | `/sys/class/gpio/gpio35` | `gpiochip1` (`GPIO2_IO03`, line 3, `GPIO_P30`, active-low input: `0`=pressed) |
| **Capacitive Touch Button B** | `/sys/class/gpio/gpio33` | `gpiochip1` (`GPIO2_IO01`, line 1, `GPIO_P26`, active-low input: `0`=pressed) |
| **Capacitive Touch Button C** | `/sys/class/gpio/gpio39` | `gpiochip1` (`GPIO2_IO07`, line 7, `GPIO_P48`, active-low input: `0`=pressed) |
| **Piezo Buzzer (PWM Speaker)** | `/sys/class/pwm/pwmchip1/pwm0` | `PWM2` (`30670000.pwm`) |

---

## 2. Deployed Files & Services

- **`/opt/rainbowhat/rainbowhat.py`**: Zero-dependency pure-Python library and CLI using Linux `i2c-dev` (`fcntl.ioctl`), `spidev`, `sysfs GPIO`, and `sysfs PWM`.
- **`/opt/rainbowhat/rainbowhat.sh` & `/usr/local/bin/rainbowhat`**: Wrapper script that activates `/opt/rainbowhat/venv` and invokes `/opt/rainbowhat/rainbowhat.py`.
- **`/etc/udev/rules.d/99-rainbowhat.rules`**: Grants `0660` group permissions (`{{ ansible_user }}`) on `/dev/i2c-0`, `/dev/spidev2.0`, and `/dev/gpiochip*`.
- **`/usr/local/sbin/rainbowhat-gpio-init.sh` & `rainbowhat-init.service`**: Boot-time systemd oneshot service that exports GPIO pins `32, 34, 37` (`out`), `33, 35, 39` (`in`), and `/sys/class/pwm/pwmchip1/pwm0` with `0660` group permissions so the non-root SSH user can control all peripherals without `sudo`.

---

## 3. Controlling the Rainbow HAT via CLI (`rainbowhat`)

All commands run directly as the configured SSH user (no `sudo` required):

### Hardware Status & Demo
```bash
# Probe all Rainbow HAT interfaces, LEDs, buttons, and sensor readings
rainbowhat status

# Run a visual demonstration of LEDs, rainbow strip, sensor, and clock display
rainbowhat demo

# Turn off all LEDs, silence the buzzer, and clear the 4-digit display
rainbowhat off
```

### 4-Digit 14-Segment Alphanumeric Display (`HT16K33` @ `0x70`)
```bash
# Display a 1-to-4 character string (supports '.' decimal points)
rainbowhat display text "HI!"
rainbowhat display text "12.34" --brightness 10 --blink off

# Display an integer or float number (right-aligned)
rainbowhat display number 23.5

# Display the current time (HH.MM) or watch continuously with a blinking separator dot
rainbowhat display time --tz-offset 1.0
rainbowhat display time --watch 30

# Scroll a longer message across the display
rainbowhat display scroll "HELLO IMX7D" --delay 0.25

# Clear the display
rainbowhat display clear
```

### BMP280 Temperature & Barometric Pressure Sensor (`0x77`)
```bash
# Print temperature (°C / °F) and pressure (hPa)
rainbowhat sensor read

# Output as JSON
rainbowhat sensor read --json

# Read sensor and immediately show temperature or pressure on the 4-digit display
rainbowhat sensor read --show-temp
rainbowhat sensor read --show-pressure
```

### 7x APA102 Addressable RGB Strip (`/dev/spidev2.0`)
```bash
# Display a 7-color rainbow gradient across pixels 0..6 (brightness 0..31)
rainbowhat rainbow preset --brightness 10

# Set all 7 pixels to an RGB color (R G B in 0..255)
rainbowhat rainbow set all 0 128 255 --brightness 12

# Set a single pixel (index 0..6, where 0 is rightmost and 6 is leftmost)
rainbowhat rainbow set 3 255 0 0 --brightness 15

# Clear the RGB strip
rainbowhat rainbow clear
```

### 3x Discrete Button Indicator LEDs (`gpio34`, `gpio32`, `gpio37`)
```bash
# Turn individual or all button LEDs on, off, or toggle
rainbowhat led set red on
rainbowhat led set green toggle
rainbowhat led set all off

# Set Red, Green, and Blue states simultaneously (0 or 1)
rainbowhat led rgb 1 0 1
```

### 3x Capacitive Touch Buttons A, B, C (`gpio35`, `gpio33`, `gpio39`)
```bash
# Read current button states (or --json)
rainbowhat button read
rainbowhat button read --json

# Interactively watch buttons for N seconds (lights matching LED and shows BTNA/BTNB/BTNC)
rainbowhat button watch --duration 15
```

### Piezo Buzzer (`/sys/class/pwm/pwmchip1/pwm0`)
```bash
# Play a musical note (C4..C6) or frequency in Hz
rainbowhat buzzer note C5 --duration 0.3
rainbowhat buzzer tone 440 --duration 0.3

# Play a 4-note chime melody or stop the buzzer
rainbowhat buzzer melody
rainbowhat buzzer stop
```

---

## 4. Controlling the Rainbow HAT from Python

You can also import the hardware controller classes directly from `/opt/rainbowhat/rainbowhat.py`:

```python
import sys
sys.path.insert(0, "/opt/rainbowhat")

from rainbowhat import (
    AlphanumericDisplay,
    BMP280Sensor,
    ButtonLeds,
    PiezoBuzzer,
    RainbowStrip,
    TouchButtons,
)

# 1. 4-Digit 14-Segment Display
display = AlphanumericDisplay()
display.show_text("HI!")

# 2. BMP280 Temperature & Pressure Sensor
sensor = BMP280Sensor()
reading = sensor.read()
print(f"{reading['temperature_c']:.2f} C, {reading['pressure_hpa']:.2f} hPa")

# 3. 7x APA102 RGB Strip
strip = RainbowStrip()
strip.set_rainbow_preset(brightness=10)

# 4. Discrete Button LEDs (Red, Green, Blue)
leds = ButtonLeds()
leds.set_rgb(1, 0, 1)

# 5. Capacitive Touch Buttons (A, B, C)
buttons = TouchButtons()
print(buttons.read_all())  # {'A': False, 'B': False, 'C': False}

# 6. Piezo Buzzer
buzzer = PiezoBuzzer()
buzzer.play_note("C5", duration=0.2)
```
