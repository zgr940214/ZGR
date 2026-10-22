#!/usr/bin/env python3
"""Validate the focused, module-free RPi4 image and matching boot/RCU symbols.

This checks built artifacts; it does not claim a Raspberry Pi hardware boot or
a working physical KGDB/JTAG connection. Python 3.11 or newer is required.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import importlib.util
import json
import lzma
import posixpath
import struct
import sys
import tarfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent
MACHINE = "raspberrypi4-64"
IMAGE = "rpi4-boot-rcu-image"
SYMBOLS = {
    "primary_entry", "start_kernel", "setup_arch", "paging_init", "rest_init",
    "rcu_init", "rcu_scheduler_starting", "rcu_spawn_gp_kthread", "rcu_gp_kthread",
    "rcu_gp_init", "rcu_gp_cleanup", "rcu_core", "rcu_note_context_switch",
    "__rcu_read_lock", "__rcu_read_unlock", "call_rcu", "synchronize_rcu",
}
BUILTINS = (
    "MMC", "MMC_BLOCK", "MMC_BCM2835", "MMC_BCM2835_MMC", "MMC_SDHCI_IPROC",
    "MMC_SDHCI_BRCMSTB", "EXT4_FS", "JBD2", "CRC16", "DEVTMPFS", "DEVTMPFS_MOUNT",
    "PINCTRL_BCM2835", "BCM2835_MBOX", "BCM2835_POWER", "RASPBERRYPI_FIRMWARE",
    "SERIAL_8250_BCM2835AUX", "SERIAL_AMBA_PL011", "BCMGENET", "BCM7XXX_PHY",
    "MDIO_BCM_UNIMAC", "TREE_RCU", "PREEMPT_RCU", "SMP", "RCU_TRACE", "FTRACE",
    "KGDB", "KGDB_SERIAL_CONSOLE", "CONSOLE_POLL", "GDB_SCRIPTS", "KALLSYMS_ALL",
    "DEBUG_INFO", "DEBUG_INFO_DWARF4", "DEBUG_INFO_COMPRESSED_NONE",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def original_verifier():
    spec = importlib.util.spec_from_file_location("full_kernel_verifier", PROJECT / "scripts/verify-artifacts.py")
    require(spec is not None and spec.loader is not None, "Missing full kernel ELF verifier")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def check_kernel(bundle):
    full = original_verifier()
    selected = {"vmlinux", "System.map", "kernel.config", "Module.symvers", "build-metadata.json", "gdb-scripts.tar.gz"}
    checksums = {}
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "Malformed kernel SHA-256")
        require(name in full.BUNDLE_FILES and name not in checksums, "Invalid or duplicate kernel checksum name")
        checksums[name] = digest
    require(selected <= checksums.keys(), "Kernel checksum manifest is incomplete")
    for name in sorted(selected):
        with (bundle / name).open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == checksums[name], f"Kernel checksum mismatch: {name}")
    metadata = json.loads((bundle / "build-metadata.json").read_text())
    for key, value in {"machine": MACHINE, "linux_version": full.VERSION,
                       "srcrev_machine": full.SOURCE_REVISION, "srcrev_meta": full.METADATA_REVISION,
                       "dwarf_version": 4, "modules_stripped": False}.items():
        require(metadata.get(key) == value, f"Kernel pin mismatch: {key}")
    release = metadata["kernel_release"]
    require(release == full.VERSION or release.startswith(full.VERSION + "-"), "Unexpected kernel release")
    config = set((bundle / "kernel.config").read_text().splitlines())
    for option in BUILTINS:
        require(f"CONFIG_{option}=y" in config, f"Required built-in/debug feature absent: {option}")
    for option in ("DEBUG_INFO_NONE", "DEBUG_INFO_REDUCED", "DEBUG_INFO_SPLIT"):
        require(f"# CONFIG_{option} is not set" in config, f"Incomplete DWARF: {option}")
    full.verify_vmlinux(bundle / "vmlinux", release, "CONFIG_RELOCATABLE=y" in config)
    with (bundle / "vmlinux").open("rb") as stream:
        sections, extra = full.elf_sections(stream, "vmlinux", 3 if "CONFIG_RELOCATABLE=y" in config else 2)
        symbols = sections[".symtab"]
        names = extra["sections"][symbols[6]]
        strings = full.read_at(stream, names[4], names[5])
        found = set()
        for entry in struct.iter_unpack("<IBBHQQ", full.read_at(stream, symbols[4], symbols[5])):
            end = strings.find(b"\0", entry[0])
            require(end >= entry[0], "Invalid vmlinux symbol string")
            name = strings[entry[0]:end].decode("ascii", "replace")
            if name in SYMBOLS and entry[3] != 0:
                found.add(name)
        require(found == SYMBOLS, f"Missing boot/RCU symbols: {sorted(SYMBOLS - found)}")
    full.verify_gdb_helpers(bundle / "gdb-scripts.tar.gz")
    return release


def check_rootfs(path):
    members = {}
    password_databases = {}
    # BZ2File supports concatenated streams from Yocto's parallel compressor.
    with bz2.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as tar:
        for member in tar:
            name = member.name.removeprefix("./").rstrip("/")
            if not name or name == ".":
                continue
            require(not name.startswith("/") and ".." not in Path(name).parts, f"Unsafe rootfs path: {name}")
            require(not name.endswith((".ko", ".ko.gz", ".ko.xz", ".ko.zst")), f"Unexpected runtime module: {name}")
            require(name.rsplit("/", 1)[-1] not in {"gdbserver", "sshd", "dropbear", "wpa_supplicant"},
                    f"Unexpected service/tool in focused image: {name}")
            prefix = b""
            if member.isfile():
                with tar.extractfile(member) as stream:
                    prefix = stream.read(64)
                    if name in ("etc/shadow", "etc/passwd"):
                        password_databases[name] = prefix + stream.read()
            members[name] = (member, prefix)
        while decoded.read(1024 * 1024):
            pass

    def resolve(name):
        seen = set()
        while True:
            require(name not in seen and name in members, f"Missing/cyclic rootfs executable: {name}")
            seen.add(name)
            member, prefix = members[name]
            if member.issym():
                target = member.linkname
                name = posixpath.normpath(target if target.startswith("/") else "/" + posixpath.dirname(name) + "/" + target).lstrip("/")
            elif member.islnk():
                name = posixpath.normpath("/" + member.linkname).lstrip("/")
            else:
                require(member.isfile() and member.mode & 0o111, f"Rootfs entry is not executable: {name}")
                require(prefix[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", prefix, 18)[0] == 183,
                        f"Rootfs executable is not AArch64 ELF: {name}")
                return

    resolve("sbin/init")
    resolve("bin/sh")
    for name in ("etc/inittab", "etc/fstab", "etc/passwd"):
        require(name in members, f"Missing essential rootfs configuration: {name}")
    # A minimal BusyBox image can store the empty password directly in passwd
    # without installing shadow-utils. Honor shadow when that database exists.
    database = password_databases.get("etc/shadow", password_databases.get("etc/passwd"))
    require(database is not None, "Missing root password database")
    root = next((line.split(b":") for line in database.splitlines() if line.startswith(b"root:")), None)
    require(root is not None and root[1] == b"", "Focused serial-console root login does not have the requested empty password")
    return len(members)


def fat_files(boot):
    require(boot[510:512] == b"\x55\xaa", "Invalid FAT boot sector")
    sector = struct.unpack_from("<H", boot, 11)[0]
    cluster_sectors = boot[13]
    reserved = struct.unpack_from("<H", boot, 14)[0]
    fats = boot[16]
    root_entries = struct.unpack_from("<H", boot, 17)[0]
    fat16_sectors = struct.unpack_from("<H", boot, 22)[0]
    fat_sectors = fat16_sectors or struct.unpack_from("<I", boot, 36)[0]
    require(sector in (512, 1024, 2048, 4096) and cluster_sectors and fats and fat_sectors, "Invalid FAT layout")
    root_sectors = (root_entries * 32 + sector - 1) // sector
    data_offset = (reserved + fats * fat_sectors + root_sectors) * sector
    cluster_bytes = cluster_sectors * sector

    def chain(first):
        chunks, seen = [], set()
        current = first
        while current < (0xFFF8 if fat16_sectors else 0x0FFFFFF8):
            require(current >= 2 and current not in seen, "Invalid/cyclic FAT cluster chain")
            seen.add(current)
            offset = data_offset + (current - 2) * cluster_bytes
            require(offset + cluster_bytes <= len(boot), "FAT cluster exceeds boot partition")
            chunks.append(boot[offset:offset + cluster_bytes])
            entry_offset = reserved * sector + current * (2 if fat16_sectors else 4)
            current = struct.unpack_from("<H" if fat16_sectors else "<I", boot, entry_offset)[0]
            if not fat16_sectors:
                current &= 0x0FFFFFFF
        return b"".join(chunks)

    directory = boot[(reserved + fats * fat_sectors) * sector: data_offset] if root_entries else chain(struct.unpack_from("<I", boot, 44)[0])
    entries, long_name = {}, {}
    for offset in range(0, len(directory), 32):
        entry = directory[offset:offset + 32]
        if len(entry) < 32 or entry[0] == 0:
            break
        if entry[0] == 0xE5:
            long_name = {}
            continue
        if entry[11] == 0x0F:
            long_name[entry[0] & 0x1F] = (entry[1:11] + entry[14:26] + entry[28:32]).decode("utf-16-le")
            continue
        short_name = entry[:8].decode("ascii", "replace").rstrip() + ("." + entry[8:11].decode("ascii", "replace").rstrip() if entry[8:11].strip() else "")
        name = "".join(long_name[key] for key in sorted(long_name)).split("\0", 1)[0].rstrip("\uffff") if long_name else short_name
        long_name = {}
        if entry[11] & 0x18:
            continue
        first = struct.unpack_from("<H", entry, 26)[0]
        if not fat16_sectors:
            first |= struct.unpack_from("<H", entry, 20)[0] << 16
        size = struct.unpack_from("<I", entry, 28)[0]
        entries[name.lower()] = (first, size)

    def read(name):
        require(name in entries and entries[name][1] > 0, f"Missing boot file: {name}")
        first, size = entries[name]
        payload = chain(first)
        require(len(payload) >= size, f"Truncated boot file: {name}")
        return payload[:size]
    return read


def check_wic(path, deploy):
    with lzma.open(path, "rb") as stream:
        header = stream.read(512)
        require(len(header) == 512 and header[510:512] == b"\x55\xaa", "Invalid WIC MBR")
        parts = [struct.unpack_from("<B3sB3sII", header, 446 + index * 16) for index in range(4)]
        require(parts[0][2] in (0x06, 0x0B, 0x0C, 0x0E) and parts[1][2] == 0x83, "Expected FAT boot and Linux root partitions")
        boot_offset, boot_size = parts[0][4] * 512, parts[0][5] * 512
        root_offset, root_size = parts[1][4] * 512, parts[1][5] * 512
        require(512 <= boot_offset and 0 < boot_size <= 512 * 1024**2 and boot_offset + boot_size <= root_offset and root_size > 2048,
                "Invalid/overlapping WIC partition bounds")
        stream.seek(boot_offset)
        boot = stream.read(boot_size)
        require(len(boot) == boot_size, "Truncated boot partition")
        read_boot = fat_files(boot)
        for name in ("start4.elf", "fixup4.dat", "config.txt", "cmdline.txt"):
            read_boot(name)
        for boot_name, deployed_name in (("kernel8.img", "Image"), ("bcm2711-rpi-4-b.dtb", "bcm2711-rpi-4-b.dtb")):
            with (deploy / deployed_name).open("rb") as kernel_file:
                digest = hashlib.file_digest(kernel_file, "sha256").digest()
            require(hashlib.sha256(read_boot(boot_name)).digest() == digest, f"Boot file differs from pinned deployed kernel/BSP: {boot_name}")
        command_line = read_boot("cmdline.txt").decode()
        require("root=/dev/mmcblk0p2" in command_line and "rootfstype=ext4" in command_line, "Boot rootfs arguments do not match the image")
        stream.seek(root_offset + 1024)
        superblock = stream.read(1024)
        require(len(superblock) == 1024 and superblock[56:58] == b"\x53\xef", "Root partition is not an ext filesystem")
        features = struct.unpack_from("<I", superblock, 96)[0]
        require(features & 0x40, "Root filesystem lacks ext4 extents")
        log_block = struct.unpack_from("<I", superblock, 24)[0]
        require(log_block <= 6, "Invalid ext4 block size")
        blocks = struct.unpack_from("<I", superblock, 4)[0]
        if features & 0x80:
            blocks |= struct.unpack_from("<I", superblock, 336)[0] << 32
        require(0 < blocks * (1024 << log_block) <= root_size, "Ext4 filesystem extends beyond its partition")
        size = root_offset + 2048
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
        require(all((entry[4] + entry[5]) * 512 <= size for entry in parts if entry[2] and entry[5]), "A partition extends beyond the complete decompressed WIC")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deploy_dir", nargs="?", type=Path, default=PROJECT / "build/tmp/deploy/images" / MACHINE)
    args = parser.parse_args()
    release = check_kernel(args.deploy_dir / "rpi4-kernel-debug")
    prefix = args.deploy_dir / f"{IMAGE}-{MACHINE}.rootfs"
    rootfs = Path(str(prefix) + ".tar.bz2")
    wic = Path(str(prefix) + ".wic.xz")
    bmap = Path(str(prefix) + ".wic.bmap")
    require(rootfs.is_file() and wic.is_file() and bmap.is_file() and bmap.stat().st_size > 0, "Focused image outputs are incomplete")
    count = check_rootfs(rootfs)
    check_wic(wic, args.deploy_dir)
    print(f"Focused image verified: {wic.name}; FAT firmware/kernel/DTB, ext4 bounds, AArch64 init/shell, serial root login, {count} rootfs entries and zero .ko files")
    print(f"Kernel verified: Linux {release}, exact pins, complete DWARF4 and {len(SYMBOLS)} real boot/RCU symbols; SD/ext4/serial/Ethernet built in")
    print("Artifact checks only; physical Raspberry Pi boot and KGDB/JTAG connectivity were not tested")


if __name__ == "__main__":
    try:
        main()
    except (OSError, EOFError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, lzma.LZMAError) as exc:
        print(f"Focused artifact verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
