#!/usr/bin/env python3
"""
Idempotently configures the U-Boot boot partition (e.g. /dev/mmcblk2p1) for
Broadcom BCM4339 (AP6335) SDIO WiFi & UART Bluetooth on TechNexion PICO-PI-IMX7D
running Linux Kernel 6.x without overwriting the OS image's native boot
environment or Device Tree Blob:

1. uEnv.txt (in-place key update, preserving native boot flow):
   - Saves a one-time backup `uEnv.txt.orig` if `uEnv.txt` exists.
   - Updates `wifi_module=<module>` in-place (and updates any hardcoded
     `fdt_file`/`fdtfile=imx7d-pico-pi-qca.dtb` to `imx7d-pico-pi.dtb`),
     never clobbering `mmcroot`, `bootcmd_mmc`, `uenvcmd`, `dtoverlay`, or `boot.scr`.

2. imx7d-pico-pi.dtb (in-place pure-Python FDT binary patch, no external `dtc` needed):
   - Saves a one-time backup `imx7d-pico-pi.dtb.orig` if `imx7d-pico-pi.dtb` exists.
   - Preserves all native board nodes (memory/CMA, eMMC, OP-TEE, regulators, and any
     camera-ov5645 patches) while ensuring:
       * `/soc/bus@30000000/clock-controller@30380000` configures `IMX7D_CLKO2_ROOT_DIV`
         (`0x157`) at `32.768 kHz` (`IMX7D_CKIL` `0x1b6`).
       * `/usdhc2_pwrseq` (`compatible = "mmc-pwrseq-simple"`, `ext_clock = <&clks 0x157>`)
         exists with a non-colliding `phandle`.
       * `/soc/bus@30800000/mmc@30b50000` (`usdhc2`) has `status = "okay"` and
         `mmc-pwrseq = <&usdhc2_pwrseq>`.
       * `/regulators/wlreg_on` and `/regulators/wifi_pwr_on` keep `regulator-always-on`.
       * Upgrades `/bt_rfkill` from legacy `net,rfkill-gpio` to mainline `rfkill-gpio`
         (`radio-type = "bluetooth"`).
   - Falls back to staged `--fallback-dtb` only if neither `imx7d-pico-pi.dtb` nor
     `imx7d-pico-pi-qca.dtb` exists on the boot partition.
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import tempfile

DTB_FILENAME = "imx7d-pico-pi.dtb"
UENV_FILENAME = "uEnv.txt"

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

IMX7D_CLKO2_ROOT_SRC = 0x155
IMX7D_CLKO2_ROOT_DIV = 0x157
IMX7D_CKIL = 0x1B6
CLKO2_RATE_HZ = 0x8000


def _write_atomic(dest_path, content_bytes):
    parent_dir = os.path.dirname(dest_path) or "."
    with tempfile.NamedTemporaryFile(
        prefix=".wifi_bcm4339_k6_",
        dir=parent_dir,
        delete=False,
    ) as tmp:
        tmp.write(content_bytes)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    shutil.move(tmp_path, dest_path)


def _backup_once(src_path):
    backup_path = src_path + ".orig"
    if os.path.isfile(src_path) and not os.path.exists(backup_path):
        shutil.copy2(src_path, backup_path)


def _parse_fdt_tree(raw_bytes):
    if len(raw_bytes) < 40:
        raise ValueError("File is too small to be a valid FDT blob")

    (
        magic,
        totalsize,
        off_dt_struct,
        off_dt_strings,
        off_mem_rsvmap,
        version,
        last_comp_version,
        boot_cpuid_phys,
        size_dt_strings,
        size_dt_struct,
    ) = struct.unpack(">10I", raw_bytes[:40])

    if magic != FDT_MAGIC or totalsize > len(raw_bytes):
        raise ValueError(f"Invalid FDT header (magic=0x{magic:08x}, size={totalsize})")

    rsv_end = off_mem_rsvmap
    while rsv_end + 16 <= len(raw_bytes):
        addr, sz = struct.unpack(">QQ", raw_bytes[rsv_end : rsv_end + 16])
        rsv_end += 16
        if addr == 0 and sz == 0:
            break
    rsvmap_bytes = raw_bytes[off_mem_rsvmap:rsv_end]
    strings_bytes = bytearray(raw_bytes[off_dt_strings : off_dt_strings + size_dt_strings])

    def get_string(offset):
        end = strings_bytes.index(b"\x00", offset)
        return bytes(strings_bytes[offset:end]).decode("ascii")

    def find_or_add_string(s):
        b = s.encode("ascii") + b"\x00"
        idx = 0
        while idx < len(strings_bytes):
            end = strings_bytes.index(b"\x00", idx) + 1
            if bytes(strings_bytes[idx:end]) == b:
                return idx
            idx = end
        new_off = len(strings_bytes)
        strings_bytes.extend(b)
        return new_off

    pos = off_dt_struct
    end_struct = off_dt_struct + size_dt_struct
    stack = []
    root = None

    while pos < end_struct:
        token = struct.unpack(">I", raw_bytes[pos : pos + 4])[0]
        pos += 4
        if token == FDT_BEGIN_NODE:
            name_end = raw_bytes.index(b"\x00", pos)
            name = raw_bytes[pos:name_end].decode("ascii")
            pos = (name_end + 4) & ~3
            node = [name, [], []]
            if stack:
                stack[-1][2].append(node)
            else:
                root = node
            stack.append(node)
        elif token == FDT_END_NODE:
            stack.pop()
        elif token == FDT_PROP:
            plen, nameoff = struct.unpack(">II", raw_bytes[pos : pos + 8])
            pos += 8
            pval = raw_bytes[pos : pos + plen]
            pos = (pos + plen + 3) & ~3
            pname = get_string(nameoff)
            stack[-1][1].append([pname, pval])
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"Unexpected FDT token {token}")

    return (
        version,
        last_comp_version,
        boot_cpuid_phys,
        rsvmap_bytes,
        strings_bytes,
        find_or_add_string,
        root,
    )


def _serialize_fdt_tree(
    version,
    last_comp_version,
    boot_cpuid_phys,
    rsvmap_bytes,
    strings_bytes,
    find_or_add_string,
    root,
):
    struct_buf = bytearray()

    def emit_node(node):
        struct_buf.extend(struct.pack(">I", FDT_BEGIN_NODE))
        name_b = node[0].encode("ascii") + b"\x00"
        struct_buf.extend(name_b)
        while len(struct_buf) % 4 != 0:
            struct_buf.append(0)
        for pname, pval in node[1]:
            nameoff = find_or_add_string(pname)
            struct_buf.extend(struct.pack(">III", FDT_PROP, len(pval), nameoff))
            struct_buf.extend(pval)
            while len(struct_buf) % 4 != 0:
                struct_buf.append(0)
        for child in node[2]:
            emit_node(child)
        struct_buf.extend(struct.pack(">I", FDT_END_NODE))

    emit_node(root)
    struct_buf.extend(struct.pack(">I", FDT_END))

    off_mem_rsvmap = 40
    if not rsvmap_bytes:
        rsvmap_bytes = b"\x00" * 16
    off_dt_struct = off_mem_rsvmap + len(rsvmap_bytes)
    while off_dt_struct % 4 != 0:
        rsvmap_bytes += b"\x00"
        off_dt_struct += 1
    size_dt_struct = len(struct_buf)
    off_dt_strings = off_dt_struct + size_dt_struct
    size_dt_strings = len(strings_bytes)
    totalsize = off_dt_strings + size_dt_strings

    header = struct.pack(
        ">10I",
        FDT_MAGIC,
        totalsize,
        off_dt_struct,
        off_dt_strings,
        off_mem_rsvmap,
        version,
        last_comp_version,
        boot_cpuid_phys,
        size_dt_strings,
        size_dt_struct,
    )
    return header + rsvmap_bytes + bytes(struct_buf) + bytes(strings_bytes)


def _find_node(root, path_parts):
    curr = root
    for part in path_parts:
        found = None
        for child in curr[2]:
            if child[0] == part:
                found = child
                break
        if found is None:
            return None
        curr = found
    return curr


def _get_prop(node, name):
    for p in node[1]:
        if p[0] == name:
            return p[1]
    return None


def _set_prop(node, name, val):
    for p in node[1]:
        if p[0] == name:
            if p[1] == val:
                return False
            p[1] = val
            return True
    node[1].append([name, val])
    return True


def _del_prop(node, name):
    for idx, p in enumerate(node[1]):
        if p[0] == name:
            del node[1][idx]
            return True
    return False


def _max_phandle(node):
    best = 0
    for pname, pval in node[1]:
        if pname in ("phandle", "linux,phandle") and len(pval) == 4:
            val = struct.unpack(">I", pval)[0]
            if 0 < val < 0xFFFFFFFF and val > best:
                best = val
    for child in node[2]:
        c_best = _max_phandle(child)
        if c_best > best:
            best = c_best
    return best


def patch_fdt_wifi_brcm(raw_bytes):
    """
    Patches native imx7d-pico-pi.dtb in-place for Broadcom BCM4339 SDIO WiFi & BT
    on Linux Kernel 6.x. Returns (patched_bytes, was_modified).
    """
    (
        version,
        last_comp_version,
        boot_cpuid_phys,
        rsvmap_bytes,
        strings_bytes,
        find_or_add_string,
        root,
    ) = _parse_fdt_tree(raw_bytes)

    ccm = _find_node(root, ["soc", "bus@30000000", "clock-controller@30380000"])
    usdhc2 = _find_node(root, ["soc", "bus@30800000", "mmc@30b50000"])
    if ccm is None or usdhc2 is None:
        raise RuntimeError(
            "Required i.MX7D nodes (clock-controller@30380000 or mmc@30b50000) not found in DTB"
        )

    ccm_ph_raw = _get_prop(ccm, "phandle") or _get_prop(ccm, "linux,phandle")
    if ccm_ph_raw is None or len(ccm_ph_raw) != 4:
        raise RuntimeError("clock-controller@30380000 is missing a valid 32-bit phandle")
    ccm_phandle = struct.unpack(">I", ccm_ph_raw)[0]

    modified = False

    # 1. Ensure CLKO2 (32.768 kHz external sleep clock) is configured on CCM
    assigned_clks = _get_prop(ccm, "assigned-clocks")
    has_clko2 = False
    if assigned_clks and len(assigned_clks) % 8 == 0:
        pairs = [
            struct.unpack(">II", assigned_clks[i : i + 8])
            for i in range(0, len(assigned_clks), 8)
        ]
        has_clko2 = (ccm_phandle, IMX7D_CLKO2_ROOT_DIV) in pairs

    if not has_clko2:
        if _set_prop(
            ccm,
            "assigned-clocks",
            struct.pack(">IIII", ccm_phandle, IMX7D_CLKO2_ROOT_SRC, ccm_phandle, IMX7D_CLKO2_ROOT_DIV),
        ):
            modified = True
        if _set_prop(
            ccm,
            "assigned-clock-parents",
            struct.pack(">II", ccm_phandle, IMX7D_CKIL),
        ):
            modified = True
        if _set_prop(
            ccm,
            "assigned-clock-rates",
            struct.pack(">II", 0, CLKO2_RATE_HZ),
        ):
            modified = True

    # 2. Ensure /usdhc2_pwrseq (mmc-pwrseq-simple) exists under root
    pwrseq = _find_node(root, ["usdhc2_pwrseq"])
    if pwrseq is None:
        pwrseq_phandle = _max_phandle(root) + 1
        pwrseq = [
            "usdhc2_pwrseq",
            [
                ["compatible", b"mmc-pwrseq-simple\x00"],
                ["clocks", struct.pack(">II", ccm_phandle, IMX7D_CLKO2_ROOT_DIV)],
                ["clock-names", b"ext_clock\x00"],
                ["phandle", struct.pack(">I", pwrseq_phandle)],
            ],
            [],
        ]
        root[2].append(pwrseq)
        modified = True
    else:
        existing_ph = _get_prop(pwrseq, "phandle") or _get_prop(pwrseq, "linux,phandle")
        if existing_ph and len(existing_ph) == 4:
            pwrseq_phandle = struct.unpack(">I", existing_ph)[0]
        else:
            pwrseq_phandle = _max_phandle(root) + 1
            if _set_prop(pwrseq, "phandle", struct.pack(">I", pwrseq_phandle)):
                modified = True
        if _set_prop(pwrseq, "compatible", b"mmc-pwrseq-simple\x00"):
            modified = True
        if _set_prop(pwrseq, "clocks", struct.pack(">II", ccm_phandle, IMX7D_CLKO2_ROOT_DIV)):
            modified = True
        if _set_prop(pwrseq, "clock-names", b"ext_clock\x00"):
            modified = True

    # 3. Ensure usdhc2 (mmc@30b50000) is enabled and references usdhc2_pwrseq
    if _set_prop(usdhc2, "status", b"okay\x00"):
        modified = True
    for bool_prop in ("no-1-8-v", "keep-power-in-suspend", "non-removable"):
        if _get_prop(usdhc2, bool_prop) is None:
            _set_prop(usdhc2, bool_prop, b"")
            modified = True
    if _set_prop(usdhc2, "mmc-pwrseq", struct.pack(">I", pwrseq_phandle)):
        modified = True

    # 4. Ensure wlreg_on and wifi_pwr_on regulators stay enabled if present
    for reg_name in ("wlreg_on", "wifi_pwr_on"):
        reg_node = _find_node(root, ["regulators", reg_name])
        if reg_node is not None and _get_prop(reg_node, "regulator-always-on") is None:
            _set_prop(reg_node, "regulator-always-on", b"")
            modified = True

    # 5. Migrate legacy net,rfkill-gpio -> mainline rfkill-gpio
    bt_rfkill = _find_node(root, ["bt_rfkill"])
    if bt_rfkill is not None and _get_prop(bt_rfkill, "compatible") == b"net,rfkill-gpio\x00":
        _set_prop(bt_rfkill, "compatible", b"rfkill-gpio\x00")
        _set_prop(bt_rfkill, "label", b"bt_rfkill\x00")
        _set_prop(bt_rfkill, "radio-type", b"bluetooth\x00")
        _del_prop(bt_rfkill, "type")
        modified = True

    # 6. Update board model string if derived from stock QCA DTB
    cur_model = _get_prop(root, "model")
    if cur_model == b"TechNexion PICO-IMX7D with QCA WLAN module and PI baseboard\x00":
        _set_prop(root, "model", b"TechNexion PICO-IMX7D with Broadcom WiFi and PI baseboard\x00")
        modified = True

    if not modified:
        return raw_bytes, False

    patched_bytes = _serialize_fdt_tree(
        version,
        last_comp_version,
        boot_cpuid_phys,
        rsvmap_bytes,
        strings_bytes,
        find_or_add_string,
        root,
    )
    return patched_bytes, True


def update_uenv_content(raw_text, wifi_module="brcm"):
    """
    Updates `wifi_module=<wifi_module>` in-place inside `uEnv.txt` (and updates any
    explicit `fdt_file`/`fdtfile=imx7d-pico-pi-qca.dtb` to `imx7d-pico-pi.dtb`),
    leaving all other variables and boot commands untouched.
    Returns (new_text, was_modified).
    """
    if not raw_text:
        return f"wifi_module={wifi_module}\n", True

    newline = "\r\n" if "\r\n" in raw_text else "\n"
    lines = raw_text.splitlines(keepends=True)
    new_lines = []
    found_wifi = False

    wifi_re = re.compile(r"^(\s*wifi_module\s*=\s*)([^\s\r\n#]*)(\s*(?:#[^\r\n]*)?[\r\n]*)$")
    fdt_re = re.compile(r"^(\s*fdt_?file\s*=\s*)imx7d-pico-pi-qca\.dtb(\s*(?:#[^\r\n]*)?[\r\n]*)$")

    for line in lines:
        m_wifi = wifi_re.match(line)
        if m_wifi:
            found_wifi = True
            new_lines.append(f"{m_wifi.group(1)}{wifi_module}{m_wifi.group(3)}")
            continue
        m_fdt = fdt_re.match(line)
        if m_fdt:
            new_lines.append(f"{m_fdt.group(1)}imx7d-pico-pi.dtb{m_fdt.group(2)}")
            continue
        new_lines.append(line)

    if not found_wifi:
        if new_lines and not new_lines[-1].endswith(("\n", "\r")):
            new_lines[-1] = new_lines[-1] + newline
        new_lines.append(f"wifi_module={wifi_module}{newline}")

    updated = "".join(new_lines)
    return updated, (updated != raw_text)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Idempotently update imx7d-pico-pi.dtb and uEnv.txt on U-Boot partition for Kernel 6.x."
    )
    parser.add_argument(
        "--boot-partition",
        default="/dev/mmcblk2p1",
        help="U-Boot block partition device (default: /dev/mmcblk2p1)",
    )
    parser.add_argument(
        "--mount-point",
        default="/mnt",
        help="Temporary mount directory when partition is not already mounted (default: /mnt)",
    )
    parser.add_argument(
        "--wifi-module",
        default="brcm",
        help="Value for wifi_module in uEnv.txt (default: brcm)",
    )
    parser.add_argument(
        "--fallback-dtb",
        default="/lib/firmware/brcm/imx7d-pico-pi-brcm.dtb",
        help="Fallback DTB path if neither imx7d-pico-pi.dtb nor imx7d-pico-pi-qca.dtb exists",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.mount_point, exist_ok=True)
    mnt = args.mount_point
    mounted_by_us = False

    res = subprocess.run(
        ["findmnt", "-rn", "-o", "TARGET", "-S", args.boot_partition],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    existing_mnt = (
        res.stdout.strip().splitlines()[0]
        if res.returncode == 0 and res.stdout.strip()
        else ""
    )
    if existing_mnt:
        mnt = existing_mnt
    elif not os.path.ismount(args.mount_point):
        subprocess.run(["mount", args.boot_partition, args.mount_point], check=True)
        mounted_by_us = True

    changed = False
    try:
        dtb_path = os.path.join(mnt, DTB_FILENAME)
        qca_dtb_path = os.path.join(mnt, "imx7d-pico-pi-qca.dtb")
        uenv_path = os.path.join(mnt, UENV_FILENAME)

        if os.path.isfile(dtb_path):
            _backup_once(dtb_path)
            with open(dtb_path, "rb") as f:
                raw_dtb = f.read()
            patched_dtb, dtb_modified = patch_fdt_wifi_brcm(raw_dtb)
            if dtb_modified:
                _write_atomic(dtb_path, patched_dtb)
                changed = True
        elif os.path.isfile(qca_dtb_path):
            with open(qca_dtb_path, "rb") as f:
                raw_qca_dtb = f.read()
            patched_dtb, _ = patch_fdt_wifi_brcm(raw_qca_dtb)
            _write_atomic(dtb_path, patched_dtb)
            changed = True
        elif os.path.isfile(args.fallback_dtb):
            with open(args.fallback_dtb, "rb") as f:
                fallback_bytes = f.read()
            _write_atomic(dtb_path, fallback_bytes)
            changed = True
        else:
            raise FileNotFoundError(
                f"Neither {dtb_path} nor fallback {args.fallback_dtb} exists"
            )

        if os.path.isfile(uenv_path):
            _backup_once(uenv_path)
            with open(uenv_path, "rb") as f:
                raw_uenv = f.read().decode("utf-8", errors="surrogateescape")
        else:
            raw_uenv = ""

        updated_uenv, uenv_modified = update_uenv_content(raw_uenv, wifi_module=args.wifi_module)
        if uenv_modified:
            _write_atomic(uenv_path, updated_uenv.encode("utf-8", errors="surrogateescape"))
            changed = True

        if changed:
            subprocess.run(["sync"], check=True)
    finally:
        if mounted_by_us:
            subprocess.run(["umount", args.mount_point], check=True)

    print("UPDATED" if changed else "UNCHANGED")


if __name__ == "__main__":
    main()
