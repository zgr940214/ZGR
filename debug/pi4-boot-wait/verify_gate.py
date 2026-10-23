#!/usr/bin/env python3
"""Execute the wait/release paths in Unicorn; this is not a Pi hardware test."""
import argparse
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X6,
)


parser = argparse.ArgumentParser()
parser.add_argument("--kernel-image", type=Path, required=True)
args = parser.parse_args()
base = Path(__file__).resolve().parent
stock = (base / "armstub8-upstream.bin").read_bytes()
debug = (base / "armstub8-debug.bin").read_bytes()
kernel = args.kernel_image.read_bytes()
report = []


def machine(binary, entry=0x80000, dtb=0x2eff0000):
    cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu.mem_map(0, 0x1000)
    cpu.mem_write(0, binary)
    # Firmware consumes and clears magic/version, then patches the boot slots.
    cpu.mem_write(0xf0, bytes(8))
    cpu.mem_write(0xf8, struct.pack("<II", dtb, entry))
    cpu.mem_map(entry, 0x1000)
    return cpu


for entry in (0x80000, 0x200000):
    for dtb in (0x2eff0000, 0x30000000):
        cpu = machine(debug, entry, dtb)
        cpu.reg_write(UC_ARM64_REG_X6, 0)
        cpu.emu_start(0x70, 0x1000, count=100)
        assert cpu.reg_read(UC_ARM64_REG_PC) == 0x200
        for reg in (UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3):
            cpu.reg_write(reg, 0xdeadbeef)
        cpu.emu_start(0x204, entry, count=100)
        assert cpu.reg_read(UC_ARM64_REG_PC) == entry
        assert cpu.reg_read(UC_ARM64_REG_X0) == dtb
        assert cpu.reg_read(UC_ARM64_REG_X4) == entry
        assert all(cpu.reg_read(reg) == 0 for reg in (
            UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3))
        report.append(f"PASS primary wait/release: entry={entry:#x} DTB={dtb:#x}")

for core in (1, 2, 3):
    states = []
    for binary in (stock, debug):
        cpu = machine(binary)
        cpu.reg_write(UC_ARM64_REG_X6, core)
        cpu.emu_start(0x70, 0x1000, count=100)
        assert cpu.reg_read(UC_ARM64_REG_PC) in (0x78, 0x7c, 0x80)
        states.append(cpu.reg_read(UC_ARM64_REG_PC))
        cpu.mem_write(0xd8 + core * 8, struct.pack("<Q", 0x80000))
        cpu.emu_start(cpu.reg_read(UC_ARM64_REG_PC), 0x80000, count=100)
        assert cpu.reg_read(UC_ARM64_REG_PC) == 0x80000
        assert all(cpu.reg_read(reg) == 0 for reg in (
            UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3))
    assert states[0] == states[1]
    report.append(f"PASS CPU{core}: stock/debug wait and mailbox-release behavior match")

cpu = machine(debug)
cpu.mem_unmap(0x80000, 0x1000)
cpu.mem_map(0x80000, (len(kernel) + 0xfff) & ~0xfff)
cpu.mem_write(0x80000, kernel)
cpu.emu_start(0x204, 0x149d068, count=100)
assert cpu.reg_read(UC_ARM64_REG_PC) == 0x149d068, hex(cpu.reg_read(UC_ARM64_REG_PC))
report.append("PASS actual 6.12.93-v8 Image: entry 0x80000, two instructions reach primary_entry 0x149d068")
report.append("Scope: emulates core selection, wait/release, Linux argument ABI, secondary mailboxes and Image entry branch.")
report.append("Does not emulate VideoCore firmware, GIC/clock setup, full Linux boot, JTAG or TRACE32.")
report.append("No Raspberry Pi / E50 hardware execution was performed.")
output = "\n".join(report) + "\n"
(base / "EMULATION-VERIFICATION.txt").write_text(output)
print(output, end="")
