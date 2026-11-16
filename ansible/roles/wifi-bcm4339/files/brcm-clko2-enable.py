#!/usr/bin/env python3
"""
Enables the 32.768 kHz external LPO reference clock on i.MX7D CCM_CLKO2
(CCM_TARGET_ROOT127 at physical address 0x3038be00: MUX=7 -> ckil 32.768 kHz,
ENABLE=1 -> 0x17000000) before loading brcmfmac on Kernel 5.x, avoiding early-boot
CLK_OF_DECLARE hangs from CCM assigned-clocks in the Device Tree.
"""

import mmap
import os
import struct
import time

CCM_BASE_PAGE = 0x3038B000
CLKO2_OFFSET = 0xE00
CLKO2_MUX_CKIL = 0x07000000
CLKO2_ENABLE_CKIL = 0x17000000


def main():
    if os.uname().release.startswith("6."):
        return

    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    try:
        mem = mmap.mmap(
            fd,
            0x1000,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=CCM_BASE_PAGE,
        )
        try:
            current = struct.unpack("<I", mem[CLKO2_OFFSET : CLKO2_OFFSET + 4])[0]
            if current != CLKO2_ENABLE_CKIL:
                # Gate off first (CLK_SET_PARENT_GATE), select MUX=7 (ckil), then enable
                mem[CLKO2_OFFSET : CLKO2_OFFSET + 4] = struct.pack("<I", CLKO2_MUX_CKIL)
                mem[CLKO2_OFFSET : CLKO2_OFFSET + 4] = struct.pack("<I", CLKO2_ENABLE_CKIL)
                time.sleep(0.05)
        finally:
            mem.close()
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
