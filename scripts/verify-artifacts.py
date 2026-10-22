#!/usr/bin/env python3
"""Verify real RPi4 images and their complete, matching kernel debug bundle.

No third-party Python packages or target binaries are executed. Missing build
outputs, stripped ELF files, a wrong pin, and an incomplete image all fail.
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import io
import json
import lzma
import re
import struct
import sys
import tarfile
from pathlib import Path


VERSION = "6.12.93"
MACHINE = "raspberrypi4-64"
SOURCE_REVISION = "d8ab4e908235da7727f22dd36ad5af224671677d"
METADATA_REVISION = "e66f40994fc740818776a0f3af55e8b6d74bfbef"
BUNDLE_FILES = {
    "vmlinux", "System.map", "kernel.config", "Module.symvers",
    "modules-with-debug.tar.gz", "kernel-source.tar.gz", "gdb-scripts.tar.gz", "build-metadata.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_at(stream, offset: int, size: int) -> bytes:
    stream.seek(offset)
    data = stream.read(size)
    require(len(data) == size, "Truncated ELF section or header")
    return data


def elf_sections(stream, name: str, expected_type: int) -> tuple[dict, dict]:
    header = read_at(stream, 0, 64)
    require(header[:6] == b"\x7fELF\x02\x01", f"{name}: expected little-endian ELF64")
    fields = struct.unpack("<HHIQQQIHHHHHH", header[16:])
    require(fields[0] == expected_type and fields[1] == 183,
            f"{name}: expected AArch64 ELF type {expected_type}")
    offset, entry_size, count, string_index = fields[5], fields[10], fields[11], fields[12]
    require(entry_size == 64 and offset > 0, f"{name}: no valid section table")
    first = struct.unpack("<IIQQQQIIQQ", read_at(stream, offset, 64))
    count = count or first[5]
    string_index = first[6] if string_index == 0xFFFF else string_index
    require(0 < count < 100000 and string_index < count, f"{name}: invalid section count")
    sections = [struct.unpack("<IIQQQQIIQQ", read_at(stream, offset + i * 64, 64))
                for i in range(count)]
    names = sections[string_index]
    string_table = read_at(stream, names[4], names[5])
    by_name = {}
    for section in sections:
        end = string_table.find(b"\0", section[0])
        require(end >= section[0], f"{name}: invalid section name")
        section_name = string_table[section[0]:end].decode("ascii", "replace")
        by_name[section_name] = section
    for required in (".debug_info", ".debug_abbrev", ".debug_line", ".symtab"):
        require(required in by_name and by_name[required][5] > 0,
                f"{name}: missing {required}; debug data is incomplete or stripped")
    require(".gnu_debuglink" not in by_name and ".debug_info.dwo" not in by_name,
            f"{name}: external/split debug information is forbidden")
    for section_name, section in by_name.items():
        require(not section_name.startswith(".zdebug_") and not
                (section_name.startswith(".debug_") and section[2] & 0x800),
                f"{name}: expected uncompressed DWARF")
    info = by_name[".debug_info"]
    length = struct.unpack("<I", read_at(stream, info[4], 4))[0]
    version_offset = info[4] + (12 if length == 0xFFFFFFFF else 4)
    require(struct.unpack("<H", read_at(stream, version_offset, 2))[0] == 4,
            f"{name}: expected DWARF version 4")
    return by_name, {"sections": sections}


def verify_vmlinux(path: Path, release: str, relocatable: bool) -> None:
    with path.open("rb") as stream:
        # arm64 links relocatable kernels with -shared (ET_DYN); this is still
        # the complete kernel ELF, with its full DWARF and symbol table.
        names, extra = elf_sections(stream, "vmlinux", 3 if relocatable else 2)
        symtab = names[".symtab"]
        require(symtab[9] == 24, "vmlinux: invalid symbol entry size")
        strings = extra["sections"][symtab[6]]
        string_table = read_at(stream, strings[4], strings[5])
        symbols = {}
        for entry in struct.iter_unpack("<IBBHQQ", read_at(stream, symtab[4], symtab[5])):
            end = string_table.find(b"\0", entry[0])
            require(end >= entry[0], "vmlinux: invalid symbol name")
            symbol_name = string_table[entry[0]:end]
            if symbol_name in (b"linux_banner", b"start_kernel", b"init_task"):
                symbols[symbol_name] = entry
        require(len(symbols) == 3, "vmlinux: essential full kernel symbols are missing")
        banner_symbol = symbols[b"linux_banner"]
        section = extra["sections"][banner_symbol[3]]
        banner = read_at(stream, section[4] + banner_symbol[4] - section[3], 256)
        require(banner.startswith(f"Linux version {release} ".encode()),
                "vmlinux: actual linux_banner does not match the pinned release")


def verify_checksums(bundle: Path) -> None:
    seen = set()
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "Malformed SHA256SUMS entry")
        digest, name = match.groups()
        require(name in BUNDLE_FILES and name not in seen, f"Unexpected checksum entry: {name}")
        seen.add(name)
        with (bundle / name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        require(actual == digest, f"Checksum mismatch: {name}")
    require(seen == BUNDLE_FILES, "SHA256SUMS does not cover the complete debug bundle")


def verify_modules(archive: Path, expected: dict | None = None) -> dict:
    modules = {}
    # Yocto's parallel lbzip2 writer produces concatenated bzip2 streams.
    # tarfile's streaming decompressor only handles one BZ2 stream; BZ2File
    # handles the complete concatenation while tarfile reads the plain TAR.
    opener = {".bz2": bz2.open, ".gz": gzip.open, ".xz": lzma.open}.get(archive.suffix, open)
    with opener(archive, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as tar:
        for member in tar:
            require(".." not in Path(member.name).parts and not member.name.startswith("/"),
                    f"Unsafe archive path: {member.name}")
            if not member.isfile() or not member.name.endswith((".ko", ".ko.xz", ".ko.gz", ".ko.zst")):
                continue
            require(member.name.endswith(".ko"), f"Compressed module not expected: {member.name}")
            require("/modules/" in member.name, f"Invalid module location: {member.name}")
            key = member.name.split("/modules/", 1)[1]
            require(key not in modules, f"Duplicate module: {key}")
            with tar.extractfile(member) as stream:
                data = stream.read()
            elf_sections(io.BytesIO(data), key, 1)
            modules[key] = hashlib.sha256(data).hexdigest()
        # Consume the compression footer and any following compression streams
        # as well, so a truncated archive still fails its integrity check.
        while decoded.read(1024 * 1024):
            pass
    require(bool(modules), f"No kernel modules checked in {archive.name}")
    if expected is not None:
        require(modules == expected,
                "Rootfs modules differ from the complete debug archive (missing, modified or stripped)")
    return modules


def verify_source(archive: Path) -> None:
    makefile = None
    helpers = False
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            normalized = member.name.removeprefix("./")
            if normalized == "Makefile" and member.isfile():
                makefile = tar.extractfile(member).read().decode()
            if normalized == "scripts/gdb/vmlinux-gdb.py" and member.isfile():
                helpers = True
    require(makefile is not None and helpers, "Kernel source/GDB helpers are absent")
    version = ".".join(re.search(rf"^{key}\s*=\s*(\d+)\s*$", makefile, re.M).group(1)
                       for key in ("VERSION", "PATCHLEVEL", "SUBLEVEL"))
    require(version == VERSION, f"Kernel source version {version} does not match {VERSION}")


def verify_wic(image: Path) -> None:
    opener = {".bz2": bz2.open, ".gz": gzip.open, ".xz": lzma.open}.get(image.suffix, open)
    with opener(image, "rb") as stream:
        header = stream.read(512)
        require(len(header) == 512 and header[510:512] == b"\x55\xaa", "Invalid WIC partition table")
        partitions = [struct.unpack_from("<B3sB3sII", header, 446 + i * 16) for i in range(4)]
        active = [entry for entry in partitions if entry[2] and entry[5]]
        require(len(active) >= 2, "Expected separate Raspberry Pi boot and rootfs partitions")
        size = 512
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
    require(all((entry[4] + entry[5]) * 512 <= size for entry in active),
            "A WIC partition extends beyond the image data")


def verify_gdb_helpers(archive: Path) -> None:
    required = {"vmlinux-gdb.py", "scripts/gdb/linux/constants.py", "scripts/gdb/linux/symbols.py"}
    found = set()
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            normalized = member.name.removeprefix("./")
            require(not member.issym() and not member.islnk(), "Nonportable GDB helper symlink")
            if normalized in required and member.isfile():
                found.add(normalized)
                require(member.size > 0, f"Empty GDB helper: {normalized}")
    require(found == required, "Incomplete portable GDB helper archive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deploy_dir", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent.parent / "build/tmp/deploy/images" / MACHINE)
    parser.add_argument("--kernel-only", action="store_true", help="verify kernel artifacts without claiming image readiness")
    args = parser.parse_args()
    bundle = args.deploy_dir / "rpi4-kernel-debug"
    require(bundle.is_dir(), f"Missing real kernel build outputs: {bundle}")
    verify_checksums(bundle)
    metadata = json.loads((bundle / "build-metadata.json").read_text())
    for key, value in {"machine": MACHINE, "linux_version": VERSION,
                       "srcrev_machine": SOURCE_REVISION, "srcrev_meta": METADATA_REVISION,
                       "dwarf_version": 4, "modules_stripped": False}.items():
        require(metadata.get(key) == value, f"Wrong build metadata pin: {key}")
    release = metadata["kernel_release"]
    require(release == VERSION or release.startswith(VERSION + "-"), "Wrong kernel release")
    config = set((bundle / "kernel.config").read_text().splitlines())
    for key in ("DEBUG_KERNEL", "DEBUG_INFO", "DEBUG_INFO_DWARF4", "DEBUG_INFO_COMPRESSED_NONE",
                "GDB_SCRIPTS", "KALLSYMS", "KALLSYMS_ALL", "IKCONFIG", "IKCONFIG_PROC",
                "MODULES"):
        require(f"CONFIG_{key}=y" in config, f"Kernel config missing CONFIG_{key}=y")
    for key in ("DEBUG_INFO_NONE", "DEBUG_INFO_REDUCED", "DEBUG_INFO_SPLIT", "MODULE_COMPRESS"):
        require(f"# CONFIG_{key} is not set" in config, f"Incomplete debug configuration: {key}")
    verify_vmlinux(bundle / "vmlinux", release, "CONFIG_RELOCATABLE=y" in config)
    require((bundle / "System.map").stat().st_size > 0 and
            " start_kernel" in (bundle / "System.map").read_text(), "Invalid kernel System.map")
    require((bundle / "Module.symvers").stat().st_size > 0, "Empty Module.symvers")
    modules = verify_modules(bundle / "modules-with-debug.tar.gz")
    require(all(name.startswith(release + "/") for name in modules), "Module release does not match vmlinux")
    verify_source(bundle / "kernel-source.tar.gz")
    verify_gdb_helpers(bundle / "gdb-scripts.tar.gz")
    print(f"Kernel verified: Linux {release}, AArch64, full DWARF4, {len(modules)} unstripped modules, exact pins and SHA-256 checksums")
    if not args.kernel_only:
        prefix = args.deploy_dir / f"rpi4-debug-image-{MACHINE}.rootfs"
        images = [Path(str(prefix) + suffix) for suffix in (".wic.bz2", ".wic", ".wic.gz", ".wic.xz")]
        image = next((path for path in images if path.is_file()), None)
        require(image is not None, "No flashable WIC image produced")
        verify_wic(image)
        rootfs = Path(str(prefix) + ".tar.bz2")
        require(rootfs.is_file(), "Missing rootfs.tar.bz2 required to verify image module symbols")
        verify_modules(rootfs, expected=modules)
        print(f"Image verified: {image.name}; all rootfs modules match the complete debug archive")
    else:
        print("Kernel-only validation; image readiness was not checked")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, EOFError, ValueError, KeyError, TypeError, tarfile.TarError, struct.error, AttributeError) as exc:
        print(f"Artifact verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
