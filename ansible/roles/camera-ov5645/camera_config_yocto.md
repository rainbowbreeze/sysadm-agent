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

### Capture a 1080p JPEG Snapshot via GStreamer
```bash
gst-launch-1.0 v4l2src device=/dev/video1 num-buffers=15 \
  ! "video/x-raw,format=UYVY,width=1920,height=1080" \
  ! videoconvert ! videoflip video-direction=180 \
  ! jpegenc quality=95 ! multifilesink location=/tmp/frame_%03d.jpg
cp /tmp/frame_014.jpg /tmp/snapshot_1080p.jpg
```

### Capture via `/usr/local/bin/camera` CLI
```bash
camera status
camera capture /tmp/photo.jpg --width 1920 --height 1080
```
