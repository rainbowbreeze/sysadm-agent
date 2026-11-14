# `rainbowhat-raspberry` — Pimoroni Rainbow HAT on Raspberry Pi

This module configures a **Raspberry Pi** (`Debian` / Raspberry Pi OS / Ubuntu) for the **Pimoroni Rainbow HAT** using the upstream `rainbowhat` and `RPi.GPIO` Python libraries inside `/opt/rainbowhat/venv`.

---

## Hardware Mapping (Raspberry Pi BCM GPIO & I2C)

| Peripheral | Interface / Pin |
| :--- | :--- |
| **4-Digit 14-Segment Display (HT16K33)** | `/dev/i2c-1` @ `0x70` |
| **BMP280 Temperature & Pressure Sensor** | `/dev/i2c-1` @ `0x77` |
| **7x APA102 RGB LEDs** | BCM `10` (MOSI/DAT), BCM `11` (SCLK/CLK), BCM `8` (CE0/CS) |
| **3x Button LEDs (Red, Green, Blue)** | BCM `6` (Red), BCM `19` (Green), BCM `26` (Blue) |
| **3x Capacitive Touch Buttons (A, B, C)** | BCM `21` (A), BCM `20` (B), BCM `16` (C) |
| **Piezo Buzzer** | BCM `13` (PWM) |

---

## Controlling the Rainbow HAT on Raspberry Pi

Execute Python scripts using the isolated virtualenv interpreter at `/opt/rainbowhat/venv/bin/python`:

```bash
# Display a 4-character string on the 14-segment display
sudo /opt/rainbowhat/venv/bin/python -c "import rainbowhat as rh; rh.display.clear(); rh.display.print_str('HI!'); rh.display.show()"

# Read temperature (°C) and pressure (hPa) from the BMP280 sensor
sudo /opt/rainbowhat/venv/bin/python -c "import rainbowhat as rh; print(f'{rh.weather.temperature():.1f} C, {rh.weather.pressure():.1f} hPa')"

# Light up all 7 APA102 RGB LEDs
sudo /opt/rainbowhat/venv/bin/python -c "import rainbowhat as rh; rh.rainbow.set_all(0, 128, 255, brightness=0.2); rh.rainbow.show()"
```
