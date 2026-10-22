#!/usr/bin/env python3
"""Check the built, module-free RPi4 image with headless SSH and GPIO tools.

These are file, ELF, boot-image and configuration checks. They do not prove
physical Raspberry Pi boot, Ethernet, GPIO electrical behavior, or SSH login.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import importlib.util
import lzma
import re
import struct
import sys
import tarfile
from pathlib import Path, PurePosixPath


PROJECT = Path(__file__).resolve().parent.parent
MACHINE = "raspberrypi4-64"
IMAGE = "rpi4-boot-rcu-ssh-image"
SETUP = "rpi4-headless-setup"
BOOT_FILES = ("network-config", "README-SETUP.txt", "authorized_keys.example", "userconf.txt.example")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def focused_verifier():
    spec = importlib.util.spec_from_file_location("focused_image_verifier", PROJECT / "scripts/verify-boot-rcu-artifacts.py")
    require(spec is not None and spec.loader is not None, "Missing full-DWARF/boot verifier")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def clean_name(name):
    while name.startswith("./"):
        name = name[2:]
    name = name.rstrip("/")
    require(not name.startswith("/") and ".." not in PurePosixPath(name).parts, f"Unsafe rootfs path: {name}")
    return name


class Rootfs:
    def __init__(self, path):
        self.entries = {}
        self.text = {}
        wanted = {
            "etc/passwd", "etc/shadow", "etc/inittab", "etc/fstab", "etc/ssh/sshd_config",
            "etc/ssh/sshd_config.d/00-local.conf", "etc/network/interfaces",
            f"etc/init.d/{SETUP}", f"usr/sbin/{SETUP}", "etc/init.d/sshd", "etc/init.d/networking",
        }
        wanted.update(f"usr/share/rpi4-setup/{name}" for name in BOOT_FILES)
        # Yocto's parallel bzip2 compressor writes concatenated streams.
        with bz2.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
            for member in archive:
                name = clean_name(member.name)
                if not name or name == ".":
                    continue
                require(name not in self.entries, f"Duplicate rootfs path: {name}")
                require(not name.endswith((".ko", ".ko.gz", ".ko.xz", ".ko.zst")), f"Unexpected runtime module: {name}")
                require(PurePosixPath(name).name not in {"wpa_supplicant", "hostapd", "gdbserver", "dropbear"},
                        f"Unexpected wireless/AP/debug service: {name}")
                prefix = b""
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        prefix = stream.read(64)
                        if name in wanted:
                            require(member.size <= 1024 * 1024, f"Unexpectedly large configuration/script: {name}")
                            self.text[name] = prefix + stream.read()
                self.entries[name] = (member, prefix)
            # Finish all compressed streams, including trailing tar padding.
            while decoded.read(1024 * 1024):
                pass

    def resolve(self, name):
        """Resolve directory symlinks, file symlinks and tar-root hard links."""
        pending = name.lstrip("/").split("/")
        resolved = []
        hops = 0
        while pending:
            part = pending.pop(0)
            if part in ("", "."):
                continue
            if part == "..":
                require(resolved, f"Link escapes rootfs: {name}")
                resolved.pop()
                continue
            current = "/".join(resolved + [part])
            require(current in self.entries, f"Missing rootfs entry: {current}")
            member, prefix = self.entries[current]
            if member.issym() or member.islnk():
                hops += 1
                require(hops <= 64, f"Cyclic rootfs links: {name}")
                target = member.linkname
                if member.islnk() or target.startswith("/"):
                    resolved = []
                pending = target.split("/") + pending
            else:
                resolved.append(part)
        require(resolved, f"Invalid rootfs entry: {name}")
        return "/".join(resolved)

    def executable(self, name, elf=True):
        resolved = self.resolve(name)
        member, prefix = self.entries[resolved]
        require(member.isfile() and member.mode & 0o111, f"Not an executable file: {name}")
        if elf:
            require(len(prefix) >= 20 and prefix[:6] == b"\x7fELF\x02\x01" and
                    struct.unpack_from("<H", prefix, 18)[0] == 183,
                    f"Executable is not AArch64 ELF: {name}")
        else:
            require(re.match(rb"#![ \t]*/bin/sh(?:[ \t\r\n]|$)", prefix), f"Expected POSIX shell script: {name}")
        return resolved

    def read(self, name):
        resolved = self.resolve(name)
        require(resolved in self.text, f"Missing captured configuration: {name}")
        return self.text[resolved].decode("utf-8")

    def starts(self, service):
        links = []
        for name, (member, _) in self.entries.items():
            match = re.fullmatch(r"etc/rc([S0-6])\.d/S([0-9]{2})(.+)", name)
            if match and match[3] == service:
                require(member.issym() or member.islnk(), f"Startup entry is not a link: {name}")
                require(self.resolve(name) == f"etc/init.d/{service}", f"Startup link points to another service: {name}")
                links.append((match[1], int(match[2]), name))
        return links


def active_options(text):
    result = {}
    for line in text.splitlines():
        words = line.split("#", 1)[0].split()
        if words:
            result.setdefault(words[0].lower(), " ".join(words[1:]).lower())
    return result


def check_rootfs(path):
    root = Rootfs(path)
    for name in ("sbin/init", "bin/sh", "usr/sbin/sshd", "usr/bin/ssh-keygen",
                 "usr/bin/gpiodetect", "usr/bin/gpioinfo", "usr/bin/gpioset"):
        root.executable(name)
    for name in ("etc/init.d/sshd", "etc/init.d/networking", f"etc/init.d/{SETUP}", f"usr/sbin/{SETUP}"):
        root.executable(name, elf=False)
    for name in ("etc/inittab", "etc/fstab", "etc/passwd"):
        root.read(name)

    users = {line.split(":", 1)[0]: line.split(":") for line in root.read("etc/passwd").splitlines()}
    require("root" in users and "sshd" in users, "Root or SSH privilege-separation account is absent")
    require(len(users["root"]) == 7 and users["root"][2] == "0" and users["root"][6] not in ("/bin/false", "/sbin/nologin"),
            "Root does not have a usable login account")

    main = root.read("etc/ssh/sshd_config")
    require(any(line.split("#", 1)[0].strip() == "Include /etc/ssh/sshd_config.d/*.conf"
                for line in main.splitlines()), "sshd does not include the local configuration")
    local = active_options(root.read("etc/ssh/sshd_config.d/00-local.conf"))
    for key, value in {"port": "22", "addressfamily": "inet", "permitrootlogin": "yes",
                       "passwordauthentication": "yes", "permitemptypasswords": "no", "pubkeyauthentication": "yes"}.items():
        require(local.get(key) == value, f"Unexpected SSH setting: {key}")
    require(active_options(main).get("permitemptypasswords", "no") != "yes", "Yocto enabled empty-password SSH in the main config")
    # No later include may weaken the explicitly checked local policy.
    for name in root.entries:
        if name.startswith("etc/ssh/sshd_config.d/") and name.endswith(".conf"):
            require(name == "etc/ssh/sshd_config.d/00-local.conf", f"Unexpected additional SSH policy file: {name}")

    interface_lines = [line.split("#", 1)[0].strip() for line in root.read("etc/network/interfaces").splitlines()]
    for line in ("auto lo", "iface lo inet loopback", "auto eth0", "iface eth0 inet dhcp"):
        require(line in interface_lines, f"Missing default wired DHCP setting: {line}")
    require(any(name in root.entries for name in ("usr/share/udhcpc/default.script", "etc/udhcpc.d/50default")),
            "BusyBox DHCP client configuration script is missing")
    for file in BOOT_FILES:
        require(root.read(f"usr/share/rpi4-setup/{file}").strip(), f"Missing headless setup template: {file}")
    importer = root.read(f"usr/sbin/{SETUP}")
    for token in ("network-config", "authorized_keys", "userconf.txt", "setup-result.txt"):
        require(token in importer, f"Headless importer does not handle expected file: {token}")

    setup_starts = root.starts(SETUP)
    require(any(level == "S" and number == 39 for level, number, _ in setup_starts), "Setup importer is not enabled at rcS priority 39")
    for service in ("networking", "sshd"):
        starts = root.starts(service)
        require(starts and any(level in "2345" for level, _, _ in starts), f"Service is not enabled in normal runlevels: {service}")
        for level, number, name in starts:
            require(level != "S" or number > 39, f"Service starts before headless configuration import: {name}")
    # rcS must run before the normal runlevel startup scripts.
    inittab = root.read("etc/inittab")
    require(any(line and not line.startswith("#") and ":sysinit:" in line and "/etc/init.d/rcS" in line
                for line in inittab.splitlines()), "SysVinit does not execute the rcS startup phase")
    return len(root.entries)


def check_boot_templates(path, deploy, focused):
    with lzma.open(path, "rb") as stream:
        header = stream.read(512)
        require(len(header) == 512 and header[510:512] == b"\x55\xaa", "Missing WIC partition table")
        boot_part = struct.unpack_from("<B3sB3sII", header, 446)
        offset, size = boot_part[4] * 512, boot_part[5] * 512
        require(512 <= offset and 0 < size <= 512 * 1024**2, "Invalid boot partition bounds")
        stream.seek(offset)
        data = stream.read(size)
        require(len(data) == size, "Incomplete boot partition")
        read = focused.fat_files(data)
        for name in BOOT_FILES:
            expected = deploy / "rpi4-headless-bootfiles" / name
            require(expected.is_file(), f"Missing deployed boot template: {expected}")
            require(hashlib.sha256(read(name.lower())).digest() == hashlib.sha256(expected.read_bytes()).digest(),
                    f"Boot template differs from deployment: {name}")
        config = read("config.txt").decode("utf-8")
        require(any(line.strip() == "enable_uart=1" for line in config.splitlines()), "Serial UART is not enabled in boot config")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deploy_dir", nargs="?", type=Path, default=PROJECT / "build/tmp/deploy/images" / MACHINE)
    args = parser.parse_args()
    deploy = args.deploy_dir
    focused = focused_verifier()
    release = focused.check_kernel(deploy / "rpi4-kernel-debug")
    config = set((deploy / "rpi4-kernel-debug/kernel.config").read_text().splitlines())
    for option in ("GPIO_CDEV", "PINCTRL_BCM2835"):
        require(f"CONFIG_{option}=y" in config, f"Built-in GPIO support absent: {option}")
    prefix = deploy / f"{IMAGE}-{MACHINE}.rootfs"
    outputs = {suffix: Path(str(prefix) + suffix) for suffix in (".tar.bz2", ".wic.xz", ".wic.bmap")}
    for suffix, path in outputs.items():
        require(path.is_file() and path.stat().st_size > 0, f"Missing SSH image output: {path}")
    cohorts = {path.resolve(strict=True).name.removesuffix(suffix) for suffix, path in outputs.items()}
    require(len(cohorts) == 1, "Rootfs, WIC and bmap are from different build timestamps")
    count = check_rootfs(outputs[".tar.bz2"])
    check_boot_templates(outputs[".wic.xz"], deploy, focused)
    focused.check_wic(outputs[".wic.xz"], deploy)
    print(f"Headless SSH image verified: {outputs['.wic.xz'].name}; {count} rootfs entries, zero .ko files, real AArch64 SSH/GPIO tools")
    print("Boot setup verified: FAT network-config/authorized_keys example/userconf example/instructions, rcS39 import before networking/sshd, IPv4 DHCP and no empty-password SSH")
    print(f"Kernel verified: Linux {release}, exact pins, complete DWARF4, boot/RCU symbols, built-in SD/ext4/Ethernet/GPIO; FAT kernel/DTB hashes and ext4 bounds")
    print("Artifact checks only; physical Raspberry Pi boot, Ethernet/SSH login, GPIO electrical behavior and KGDB/JTAG were not tested")


if __name__ == "__main__":
    try:
        main()
    except (OSError, EOFError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, lzma.LZMAError) as exc:
        print(f"Headless SSH artifact verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
