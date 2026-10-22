#!/usr/bin/env python3
"""Free redundant kernel link inputs after successful BitBake kernel install.

Run only between BitBake invocations. Complete linked kernel/module debug
outputs are validated first. Only generated .o inputs in the explicit build
directory allowlist are removed; subsequent kernel recompilation may recreate
them. Full vmlinux, .ko files, source, generated headers, and GDB helpers stay.
"""

from __future__ import annotations

import errno
import fcntl
import importlib.util
import os
import shutil
import stat
import struct
import sys
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


PROJECT = Path(__file__).absolute().parent.parent
BUILD = PROJECT / "build"
KERNEL_BUILD = BUILD / "tmp/work/raspberrypi4_64-poky-linux/linux-raspberrypi/6.12.93+git/linux-raspberrypi4_64-standard-build"
MINIMUM_FREE = 16 * 1024**3
OBJECT_DIRECTORIES = (
    "crypto", "drivers", "fs", "ipc", "kernel", "lib", "mm", "net",
    "security", "sound", "virt", "init", "io_uring", "block", "certs", "usr",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strict_path(path: Path, directory: bool = False) -> os.stat_result:
    require(path.is_absolute() and ".." not in path.parts, f"Unsafe path: {path}")
    path.relative_to(PROJECT)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode), f"Symlink is forbidden in this path: {current}")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    require(expected(info.st_mode), f"Wrong file type: {path}")
    return info


@contextmanager
def bitbake_lock():
    lock = BUILD / "bitbake.lock"
    strict_path(BUILD, directory=True)
    deadline = time.monotonic() + 30.0
    descriptor = None
    while descriptor is None:
        candidate = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        try:
            fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            opened = os.fstat(candidate)
            current = lock.lstat()
            require(stat.S_ISREG(current.st_mode), "BitBake lock is not a regular file")
            if (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino):
                descriptor = candidate
                continue
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.ENOENT):
                os.close(candidate)
                raise
        except Exception:
            os.close(candidate)
            raise
        os.close(candidate)
        remaining = deadline - time.monotonic()
        require(remaining > 0, "BitBake lock remained held or changed for 30 seconds; no objects were removed")
        time.sleep(min(0.25, remaining))
    try:
        yield
    finally:
        # Keep the pathname: unlinking an unlocked lock can create races with
        # another BitBake process opening it. BitBake itself handles old locks.
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def load_verifier():
    path = PROJECT / "scripts/verify-artifacts.py"
    strict_path(path)
    spec = importlib.util.spec_from_file_location("rpi4_artifact_verifier", path)
    require(spec is not None and spec.loader is not None, "Cannot import artifact verifier")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def verify_complete_outputs() -> int:
    verifier = load_verifier()
    for name in ("vmlinux", "Module.symvers", "System.map", ".config", "modules.order", "include/config/kernel.release"):
        info = strict_path(KERNEL_BUILD / name)
        require(info.st_size > 0, f"Incomplete kernel output: {name}")
    config = set((KERNEL_BUILD / ".config").read_text().splitlines())
    for option in ("DEBUG_KERNEL", "DEBUG_INFO", "DEBUG_INFO_DWARF4", "DEBUG_INFO_COMPRESSED_NONE", "MODULES"):
        require(f"CONFIG_{option}=y" in config, f"Missing full-debug configuration: {option}")
    for option in ("DEBUG_INFO_NONE", "DEBUG_INFO_REDUCED", "DEBUG_INFO_SPLIT", "MODULE_COMPRESS"):
        require(f"# CONFIG_{option} is not set" in config, f"Incompatible debug configuration: {option}")
    release = (KERNEL_BUILD / "include/config/kernel.release").read_text().strip()
    require(release == verifier.VERSION or release.startswith(verifier.VERSION + "-"), "Wrong linked kernel release")
    verifier.verify_vmlinux(KERNEL_BUILD / "vmlinux", release, "CONFIG_RELOCATABLE=y" in config)
    expected = set()
    for entry in (KERNEL_BUILD / "modules.order").read_text().splitlines():
        relative = PurePosixPath(entry)
        require(entry and entry == entry.strip() and not relative.is_absolute() and
                ".." not in relative.parts and relative.suffix in (".o", ".ko"),
                f"Unsafe or unknown modules.order entry: {entry!r}")
        # Linux 6.12 modules.order lists link inputs ending in .o.
        module = KERNEL_BUILD.joinpath(*relative.with_suffix(".ko").parts)
        require(module not in expected, f"Duplicate module entry: {entry}")
        expected.add(module)
        strict_path(module)
        with module.open("rb") as stream:
            sections, _ = verifier.elf_sections(stream, entry, 1)
            require(".modinfo" in sections, f"Missing module metadata: {entry}")
            section = sections[".modinfo"]
            metadata = verifier.read_at(stream, section[4], section[5])
            require(b"vermagic=" + release.encode() + b" " in metadata,
                    f"Module does not match linked kernel release: {entry}")
    require(bool(expected), "No linked kernel modules were verified")
    actual = set(KERNEL_BUILD.rglob("*.ko"))
    require(actual == expected, "Linked module set differs from modules.order; no objects may be removed")
    return len(expected)


def candidates() -> list[tuple[Path, os.stat_result]]:
    objects = []

    def add(path: Path) -> None:
        info = strict_path(path)
        require(path.suffix == ".o", f"Refusing non-object input: {path}")
        with path.open("rb") as stream:
            header = stream.read(20)
        require(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01",
                f"Not a generated ELF object: {path}")
        kind, machine = struct.unpack("<HH", header[16:20])
        if (kind, machine) == (1, 62):
            # Some drivers build host tools, e.g. speakup/makemapdata.o.
            # Preserve those inputs along with the tools themselves.
            return
        require((kind, machine) == (1, 183),
                f"Not a generated AArch64 link-input object: {path}")
        objects.append((path, info))

    def failed(error):
        raise error

    for name in OBJECT_DIRECTORIES:
        directory = KERNEL_BUILD / name
        if not os.path.lexists(directory):
            continue
        strict_path(directory, directory=True)
        for root, directories, files in os.walk(directory, onerror=failed, followlinks=False):
            for child in directories:
                strict_path(Path(root) / child, directory=True)
            for filename in files:
                if filename.endswith(".o"):
                    add(Path(root) / filename)
    combined = KERNEL_BUILD / "vmlinux.o"
    if os.path.lexists(combined):
        add(combined)
    return objects


def command_candidates(objects: list[tuple[Path, os.stat_result]]) -> list[tuple[Path, os.stat_result]]:
    # Kbuild .foo.o.cmd files can be large because they repeat compiler flags
    # and header dependencies. They are regenerated with their missing .o.
    selected = set()
    for path, _ in objects:
        command = path.with_name("." + path.name + ".cmd")
        if os.path.lexists(command):
            selected.add(command)
    for name in OBJECT_DIRECTORIES:
        directory = KERNEL_BUILD / name
        if not directory.exists():
            continue
        for command in directory.rglob(".*.o.cmd"):
            obj = command.with_name(command.name[1:-4])
            if not os.path.lexists(obj):
                selected.add(command)
    command = KERNEL_BUILD / ".vmlinux.o.cmd"
    if not os.path.lexists(KERNEL_BUILD / "vmlinux.o") and os.path.lexists(command):
        selected.add(command)
    return [(path, strict_path(path)) for path in sorted(selected)]


def main() -> int:
    strict_path(PROJECT, directory=True)
    strict_path(KERNEL_BUILD, directory=True)
    if shutil.disk_usage(KERNEL_BUILD).free >= MINIMUM_FREE:
        print("At least 16 GiB free; all kernel link-input objects retained")
        return 0
    with bitbake_lock():
        free_before = shutil.disk_usage(KERNEL_BUILD).free
        if free_before >= MINIMUM_FREE:
            print("At least 16 GiB free after acquiring the lock; all objects retained")
            return 0
        modules = verify_complete_outputs()
        objects = candidates()
        commands = command_candidates(objects)
        # All validation and candidate discovery finish before any deletion.
        total = 0
        for path, original in objects + commands:
            current = strict_path(path)
            require((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) ==
                    (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns),
                    f"Object changed during preflight: {path}")
            path.unlink()
            total += original.st_size
        free_after = shutil.disk_usage(KERNEL_BUILD).free
        print(f"Verified complete unstripped vmlinux and {modules} full-DWARF modules")
        print(f"Removed {len(objects)} redundant .o files and {len(commands)} paired .o.cmd files ({total} logical bytes); "
              f"reclaimed {max(0, free_after - free_before)} bytes of free space")
        print("All .ko/vmlinux/maps/configs/sources/headers/GDB/scripts/tools/arch retained")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, struct.error, AttributeError) as exc:
        print(f"Kernel object cleanup FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
