#!/usr/bin/env python3
"""Build and statically check the stock and debugger-gated Pi 4 armstubs."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess


def run(argv):
    subprocess.run(argv, check=True)


parser = argparse.ArgumentParser()
parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
parser.add_argument("--binutils-prefix", default="aarch64-linux-gnu-")
args = parser.parse_args()
base = Path(__file__).resolve().parent
for name in ("armstub8-upstream", "armstub8-debug"):
    src = base / (name + ".S")
    assembly = base / (name + ".s")
    obj = base / (name + ".o")
    elf = base / (name + ".elf")
    binary = base / (name + ".bin")
    run([args.gcc, "-E", "-x", "assembler-with-cpp", "-DGIC=1",
         "-DBCM2711=1", str(src), "-o", str(assembly)])
    run([args.binutils_prefix + "as", "-EL", str(assembly), "-o", str(obj)])
    run([args.binutils_prefix + "ld", "--section-start=.text=0", str(obj),
         "-o", str(elf)])
    run([args.binutils_prefix + "objcopy", "-O", "binary", str(elf), str(binary)])
    raw = binary.read_bytes()
    binary.write_bytes(raw + bytes((-len(raw)) % 256))
    disassembly = subprocess.check_output(
        [args.binutils_prefix + "objdump", "-d", str(elf)], text=True)
    (base / (name + ".disassembly.txt")).write_text(disassembly)

stock = (base / "armstub8-upstream.bin").read_bytes()
debug = (base / "armstub8-debug.bin").read_bytes()
assert len(stock) == 512 and len(debug) == 768
assert stock[0xd8:0x100] == debug[0xd8:0x100]
assert struct.unpack_from("<I", debug, 0xf0)[0] == 0x5afe570b
assert debug[0xf4:0x100] == bytes(12)
assert debug[0x200:0x204] == bytes.fromhex("00000014")

changed_words = [i for i in range(0, len(stock), 4)
                 if stock[i:i+4] != debug[i:i+4]]
assert len(changed_words) == 1, changed_words
branch_at = changed_words[0]
branch = struct.unpack_from("<I", debug, branch_at)[0]
assert branch & 0xff00001f == 0xb4000006  # CBZ X6, <debug_gate>
assert branch_at + ((branch >> 5) & 0x7ffff) * 4 == 0x200
release = struct.unpack_from("<I", debug, 0x204)[0]
assert release & 0xfc000000 == 0x14000000
imm26 = release & 0x03ffffff
if imm26 & 0x02000000:
    imm26 -= 0x04000000
primary_at = 0x204 + imm26 * 4
assert stock[primary_at:primary_at+4] == debug[primary_at:primary_at+4]

report = (
    "Source: raspberrypi/tools commit 439b6198a9b340de5998dd14a26a0d9d38a6bcac\n"
    "Variant: GIC=1 BCM2711=1 HIGH_PERI unset (ordinary Pi 4 configuration)\n"
    f"Stock size: {len(stock)} bytes; debug size: {len(debug)} bytes\n"
    f"Only changed word within stock binary: {branch_at:#x}\n"
    "CPU0 wait address: 0x200; release PC: 0x204\n"
    f"Release branches back to stock primary_cpu at {primary_at:#x}\n"
    "Firmware magic, version, DTB/kernel slots and secondary mailboxes preserved.\n"
    "All original code other than the primary-core CBZ destination preserved.\n"
    f"SHA256 armstub8-debug.bin: {hashlib.sha256(debug).hexdigest()}\n"
    "Checks: cross-assembled, linked, disassembled, binary layout assertions passed.\n"
    "No Raspberry Pi / E50 hardware execution was performed.\n"
)
(base / "BUILD-VERIFICATION.txt").write_text(report)
print(report, end="")
