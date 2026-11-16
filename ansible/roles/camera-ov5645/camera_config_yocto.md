# OmniVision OV5645 Camera Configuration on TechNexion Yocto (Kernel 6.x)

Reference notes for bringing up and configuring the **OmniVision OV5645** MIPI-CSI2 camera on **TechNexion PICO-PI-IMX7D** running **TechNexion i.MX Release Distro 6.18-wrynose** (Linux kernel `6.18.x`).

---

## 1. Hardware Architecture on PICO-PI-IMX7D

| Component | Bus / Address / Pin | Register / Value | Description |
| :--- | :--- | :--- | :--- |
| **Sensor I2C** | `/dev/i2c-3` (`30a50000.i2c`) @ `0x3c` | Reg `0x300a:0x300b` = `0x5645` | OmniVision OV5645 5MP MIPI-CSI2 sensor |
| **Core Supply (`DVDD` 1.50V)** | `/dev/i2c-3` @ `0x08` (`pfuze3000@8` PMIC) | Reg `0x6d` (`VLDO2` / `VGEN2`) = `0x1e` | Bits `[3:0]=0xE` (`1.50V`), Bit `4=1` (`VLDO2_EN`) |
| **Master Clock (`XCLK` 24 MHz)** | `GPIO1_IO02` (`ALT5 = CCM_CLKO1`) | `0x3038bd80` = `0x10000000` | `IMX7D_CLKO1_ROOT_DIV` (Clock ID `340` / `0x154`) |
| **Power / Enable (`GPIO4`)** | `GPIO1_IO04` (`gpio4`) | Physical HIGH (`1`) = ON | `enable-gpios = <&gpio1 4 GPIO_ACTIVE_HIGH>` |
| **Hardware Reset (`CAM_RST`)** | `GPIO1_IO05` (`gpio5`) | Physical HIGH (`1`) = Run | `reset-gpios = <&gpio1 5 GPIO_ACTIVE_LOW>` |
| **MIPI-CSI2 Receiver** | `30750000.mipi-csi` (`mxc_mipi-csi.0`) | 2 Data Lanes (`<1 2>`) | Subdevice bridging `ov5645 3-003c` to `mx6s-csi` |
| **V4L2 Capture Device** | `/dev/video1` (`30710000.csi1`) | Driver `mx6s-csi` (`UYVY`) | Supports `1280x960`, `1920x1080`, `2592x1944` |

> **Warning — Never Write Arbitrary Registers to `0x08` on `/dev/i2c-3`**:
> Slave address `0x08` on `/dev/i2c-3` is the board's main **NXP PFUZE3000 PMIC** (`pfuze3000@8`). Writing 16-bit camera register addresses (such as `0x30 0x0a`) to `0x08` overwrites PMIC register `0x30` (`SW2` rail voltage) and immediately powers off the board.

---

## 2. Why Stock Yocto 6.18 Fails to Detect the OV5645

TechNexion's stock `/run/media/boot-mmcblk2p1/imx7d-pico-pi.dtb` on Kernel `6.18.x` has four issues:

1. **PMIC `VLDO2` (`1.50V` Camera `DVDD`) Disabled at Boot**:
   - U-Boot initializes `PFUZE3000` `VLDO2` (register `0x6d`) to `0x1e` (`1.50V`, enabled).
   - In `imx7d-pico-pi.dtb`, `pfuze3000@8/regulators/vldo2` is missing `regulator-always-on` (unlike `vldo1`, `vldo3`, `vldo4`, `vccsd`, and `v33`), so the kernel disables it ~30 seconds into boot (`VLDO2: disabling`, changing register `0x6d` from `0x1e` to `0x0e`), removing the camera's `1.50V` core power.
2. **Wrong Clock Index (`342` instead of `340`)**:
   - Stock `ov5640_mipi@3c` specifies `clocks = <&clks 342>` (`0x156`), which is `clko2_pre_div` (`32.768 kHz` fed by `ckil`) instead of `IMX7D_CLKO1_ROOT_DIV` (`340` / `0x154`, `clko1_post_div` at `24 MHz` on `GPIO1_IO02`).
   - This leaves `CCM_CLKO1` (`0x3038bd80`) disabled (`0x00000000`) and causes `ov5645.ko` to fail with `ov5645 3-003c: error -EINVAL: unsupported xclk frequency 32768`.
3. **Wrong Driver & GPIO Polarity**:
   - Stock `imx7d-pico-pi.dtb` uses `compatible = "ovti,ov5640_mipi"`, which binds `ov5640_camera_mipi_v2.ko`. That driver drives `GPIO1_IO04` LOW (`0`) via raw GPIO calls (putting the camera in power-down) and only accepts Chip ID `0x5640`.
   - On this board, the OV5645 requires **both `GPIO1_IO04 = 1` and `GPIO1_IO05 = 1`** to power on and respond at `0x3c`.
   - Mainline `ov5645.ko` (`compatible = "ovti,ov5645"`) calls `gpiod_set_value_cansleep(enable_gpio, 1)` and `gpiod_set_value_cansleep(rst_gpio, 0)` during power-on. With `enable-gpios = <&gpio1 4 GPIO_ACTIVE_HIGH>` and `reset-gpios = <&gpio1 5 GPIO_ACTIVE_LOW>`, both physical pins are driven HIGH (`1, 1`).
4. **Missing `data-lanes` Property in `port/endpoint`**:
   - Mainline `ov5645.ko` calls `v4l2_fwnode_endpoint_parse()` on `port/endpoint`, which requires `data-lanes = <1 2>;` to identify the bus as `V4L2_MBUS_CSI2_DPHY` and configure 2-lane MIPI CSI-2 operation.

---

## 3. Device Tree Changes Applied to `imx7d-pico-pi.dtb`

1. **`/soc/bus@30800000/i2c@30a50000/pfuze3000@8/regulators/vldo2`**:
   ```dts
   vldo2 {
       regulator-min-microvolt = <1500000>;
       regulator-max-microvolt = <1500000>;
       regulator-boot-on;
       regulator-always-on;
   };
   ```

2. **`/soc/bus@30800000/i2c@30a50000/ov5645_mipi@3c`**:
   ```dts
   ov5645_mipi@3c {
       compatible = "ovti,ov5645";
       reg = <0x3c>;
       pinctrl-names = "default";
       pinctrl-0 = <&pinctrl_mipi_csi>;
       clocks = <&clks 340>; /* IMX7D_CLKO1_ROOT_DIV (24 MHz on GPIO1_IO02) */
       clock-names = "xclk";
       clock-frequency = <24000000>;
       vdddo-supply = <&reg_vref_1v8>;
       vdda-supply = <&reg_2p5v>;
       vddd-supply = <&reg_2p5v>;
       enable-gpios = <&gpio1 4 0>; /* GPIO_ACTIVE_HIGH -> physical 1 when enabled */
       reset-gpios = <&gpio1 5 1>;  /* GPIO_ACTIVE_LOW  -> physical 1 when deasserted */

       port {
           endpoint {
               remote-endpoint = <&mipi_sensor_ep>;
               data-lanes = <1 2>;
           };
       };
   };
   ```

---

## 4. Verification & Frame Capture Commands

### Verify Driver Binding After Boot
```bash
dmesg | grep -iE "ov5645|csi"
# Expected output:
# mx6s-csi 30710000.csi1: initialising
# mxc_mipi-csi 30750000.mipi-csi: mipi csi v4l2 device registered
# CSI: Registered sensor subdevice: mxc_mipi-csi.0
# mxc_mipi-csi 30750000.mipi-csi: lanes: 2, hs_settle: 13, clk_settle: 2, wclk: 1, freq: 240000000
# ov5645 3-003c: OV5645 detected at address 0x3c
# mxc_mipi-csi 30750000.mipi-csi: Registered sensor subdevice: ov5645 3-003c
# mxc_mipi-csi 30750000.mipi-csi: complete callback for subdevice called
```

### Capture a 1280x960 JPEG Snapshot via GStreamer
```bash
gst-launch-1.0 v4l2src device=/dev/video1 num-buffers=15 \
  ! "video/x-raw,format=UYVY,width=1280,height=960" \
  ! videoconvert ! videoflip video-direction=180 \
  ! jpegenc quality=95 ! multifilesink max-files=2 location=/tmp/frame_%03d.jpg
cp /tmp/frame_014.jpg /tmp/snapshot_1280x960.jpg
```

### Capture via `/usr/local/bin/camera` CLI
```bash
camera status
camera capture /tmp/photo.jpg
camera capture /tmp/photo_portrait.jpg --rotation 90
camera capture /tmp/photo_1080p.jpg --width 1920 --height 1080
```

---

## 5. `1920x1080` Green Tint Root Cause & Switching Between Options 1, 2, and 3

### Why Stock Mainline `ov5645.ko` Turns Green at `1920x1080`
- Digital test patterns (`v4l2-ctl -d /dev/v4l-subdev0 -c test_pattern=4` / `test_pattern=1`) confirm the MIPI-CSI2 link, `mxc_mipi-csi`, `mx6s-csi` (`/dev/video1`), and GStreamer `UYVY` pipeline are bit-exact (`Y=4, U=128.0, V=128.0` for black).
- In `drivers/media/i2c/ov5645.c`, **`ov5645_setting_sxga` (`1280x960`)** and **`ov5645_setting_full` (`2592x1944`)** both start horizontal pixel readout at **`X_ADDR_START = 0x0000`**, preserving the sensor's shielded horizontal **Optical Black (OB) reference columns (`X = 0..15`)** required by Black Level Calibration (`0x4000 = 0x89`).
- By contrast, **`ov5645_setting_1080p` (`1920x1080`)** leaves the OV5645 ISP scaler disabled (`0x5001 = 0x83`) and center-crops the sensor array starting at **`X_ADDR_START = 0x0150` (`336`), `Y_ADDR_START = 0x01b2` (`434`)** with `0x4514 = 0x88`. Skipping `X = 0..15` corrupts BLC clamping, shifting both `U (Cb)` and `V (Cr)` by ~`-25` counts across the entire image (`U ≈ 103, V ≈ 103`, turning blacks into dark green `Y_min = 31` / `RGB ≈ (1, 54, 0)`) and discarding ~45% of the lens field of view.
- **DMA Sync Caveat**: Do **not** rewrite `0x3800..0x380f` or PLL `0x3035..0x3036` over `/dev/i2c-3` from userspace *after* `VIDIOC_STREAMON` — resetting sensor frame timing while `mx6s-csi` DMA is active desynchronizes ping-pong DMA buffers from VSYNC and introduces a horizontal split line.

| Sensor Mode | Active Start `(X, Y)` | `Y` (min / mean / max) | Mean `(U, V)` | Dark `(U, V)` (`Y < 45`) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `1920x1080` (`ov5645_setting_1080p`) | `(336, 434)` | `31 / 91.0 / 251` | `(102.9, 103.0)` | `(103.3, 101.1)` | Broken BLC green cast + narrow cropped FOV |
| `1280x960` (`ov5645_setting_sxga`) | `(0, 6)` | `10 / 76.2 / 255` | `(122.5, 120.8)` | `(127.9, 121.1)` | **Option 1 (Default)**: neutral blacks, `2×2` binned low-light, `30 fps` |
| `2592x1944` (`ov5645_setting_full`) | `(0, 0)` | `7 / 114.9 / 255` | `(130.9, 130.0)` | `(146.1, 135.2)` | Full `5MP` array (`15 fps`), used by **Option 2** |

---

### Option 1 (Active Default): Native `1280x960` (`SXGA` `2×2` Binned)
Configured out of the box in `defaults/main.yml`:
```yaml
camera_ov5645_default_width: 1280
camera_ov5645_default_height: 960
camera_ov5645_rotation: 180
camera_ov5645_native_1080p: false
```

---

### Option 2 (Pure-Userspace `1920x1080` Switch): `2592x1944` Capture + GStreamer `16:9` Crop/Downscale
`camera.py` already implements automatic `2592x1944` $\rightarrow$ `2592x1458` (`videocrop top=242 bottom=244`) $\rightarrow$ `1920x1080` (`videoscale`) supersampling whenever `1920x1080` is requested on mainline `ov5645` (`camera_ov5645_native_1080p: false`).

To make `1920x1080` the default without touching kernel modules, set in `machines/<MACHINE_NAME>/vars.yml` and re-run `--tags camera-ov5645`:
```yaml
camera_ov5645_default_width: 1920
camera_ov5645_default_height: 1080
camera_ov5645_native_1080p: false
```

---

### Option 3 (Kernel Module Fix): Patch `ov5645_setting_1080p` in `ov5645.ko` for Hardware ISP Scaling
If native `1920x1080` V4L2 streaming is needed for **all** V4L2 consumers (such as `ustreamer` at `1080p`) with zero CPU scaling overhead, update `ov5645_setting_1080p` inside `/lib/modules/$(uname -r)/kernel/drivers/media/i2c/ov5645.ko` so the sensor reads the full `2592`-pixel width (`2592x1458` `16:9`, `X_ADDR_START = 0x0000` including OB columns) and enables the OV5645 internal hardware ISP scaler (`0x5001 = 0xa3`) *before* `STREAMON`:

| Register | Stock `1080p` | Patched `1080p` (`16:9` Full-Width + ISP Scaler) | Purpose |
| :--- | :--- | :--- | :--- |
| `0x3800:0x3801` | `0x0150` (`336`) | **`0x0000`** (`0`) | Start at column `0` so BLC reads horizontal OB pixels |
| `0x3802:0x3803` | `0x01b2` (`434`) | **`0x00f2`** (`242`) | Vertical `16:9` window start (`1470` raw lines $\rightarrow$ `1458` active) |
| `0x3804:0x3805` | `0x08ef` (`2287`) | **`0x0a3f`** (`2623`) | Full sensor width (`2624` raw $\rightarrow$ `2592` active) |
| `0x3806:0x3807` | `0x05f1` (`1521`) | **`0x06af`** (`1711`) | Vertical `16:9` window end |
| `0x380c:0x380d` | `0x09c4` (`2500`) | **`0x0b1c`** (`2844`) | Horizontal total size (`HTS`) for `2624`-pixel line readout |
| `0x380e:0x380f` | `0x0460` (`1120`) | **`0x05dc`** (`1500`) | Vertical total size (`VTS`) for `1470`-line readout |
| `0x3813` | `0x04` | **`0x06`** | Vertical ISP pre-window offset (`1470 - 12 = 1458`) |
| `0x5001` *(replace `0x4202: 0x00` slot or add)* | *(global `0x83`)* | **`0xa3`** | Enable OV5645 internal hardware ISP scaler (`BIT(5)`) |

*(Note: In `ov5645_global_init_setting`, `0x5001 = 0x83`; if patching `ov5645_setting_1080p` in-place within the fixed 47-entry `.rodata` array, replace the redundant `{0x4202, 0x00}` entry with `{0x5001, 0xa3}` and `{0x5001, 0x83}` in `ov5645_setting_sxga` / `ov5645_setting_full` so switching back from `1080p` disables the scaler cleanly. Optionally set `{0x3035, 0x21}, {0x3036, 0x70}, {0x4837, 0x16}` for `224 MHz` MIPI link / tighter dark clamp.)*

After reloading the patched `ov5645.ko` (`modprobe -r ov5645 && modprobe ov5645`), set in `vars.yml`:
```yaml
camera_ov5645_default_width: 1920
camera_ov5645_default_height: 1080
camera_ov5645_native_1080p: true
```
