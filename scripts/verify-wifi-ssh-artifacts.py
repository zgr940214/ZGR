#!/usr/bin/env python3
"""Validate the built RPi4 Wi-Fi/SSH/GPIO image and its full-symbol kernel.

The original module-free image checks remain unchanged. This target includes
only Wi-Fi's module dependency set, with every installed module checked against
the retained kernel build. Artifact checks do not establish physical boot,
radio association, network login, or GPIO electrical behavior.
"""

from __future__ import annotations

import argparse
import bz2
import ctypes
import ctypes.util
import fnmatch
import hashlib
import hmac
import importlib.util
import io
import lzma
import re
import struct
import sys
import tarfile
from pathlib import Path, PurePosixPath


PROJECT = Path(__file__).resolve().parent.parent
MACHINE = "raspberrypi4-64"
IMAGE = "rpi4-boot-rcu-wifi-image"
SETUP = "rpi4-headless-setup"
BOOT_FILES = ("network-config", "README-SETUP.txt")
ROOTFS_TEMPLATES = BOOT_FILES + ("authorized_keys.example", "userconf.txt.example")
KERNEL_BUILD = PROJECT / "build/tmp/work/raspberrypi4_64-poky-linux/linux-raspberrypi/6.12.93+git/linux-raspberrypi4_64-standard-build"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_support():
    spec = importlib.util.spec_from_file_location("headless_ssh_verifier", PROJECT / "scripts/verify-headless-ssh-artifacts.py")
    require(spec is not None and spec.loader is not None, "Missing SSH/kernel artifact verifier")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


SUPPORT = load_support()


class WiFiRootfs(SUPPORT.Rootfs):
    def __init__(self, path, release, full, kernel_build):
        self.entries = {}
        self.text = {}
        self.modules = {}
        self.module_info = {}
        wanted = {
            "etc/passwd", "etc/shadow", "etc/inittab", "etc/fstab", "etc/ssh/sshd_config",
            "etc/ssh/sshd_config.d/00-local.conf", "etc/network/interfaces", "etc/hostname",
            "etc/avahi/avahi-daemon.conf", f"etc/init.d/{SETUP}", f"usr/sbin/{SETUP}",
            "etc/init.d/sshd", "etc/init.d/networking", "etc/init.d/avahi-daemon",
            "etc/init.d/dbus-1", "etc/init.d/modutils.sh", "etc/modules-load.d/rpi4-wifi.conf",
        }
        wanted.update(f"usr/share/rpi4-setup/{name}" for name in ROOTFS_TEMPLATES)
        wanted.update(f"{prefix}/modules/{release}/{name}" for prefix in ("lib", "usr/lib")
                      for name in ("modules.dep", "modules.alias"))
        with bz2.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
            for member in archive:
                name = SUPPORT.clean_name(member.name)
                if not name or name == ".":
                    continue
                require(name not in self.entries, f"Duplicate rootfs path: {name}")
                require(PurePosixPath(name).name not in {"hostapd", "gdbserver", "dropbear"},
                        f"Unexpected AP/debug service: {name}")
                prefix = b""
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        if name.endswith((".ko", ".ko.gz", ".ko.xz", ".ko.zst")):
                            require(name.endswith(".ko"), f"Unexpected compressed kernel module: {name}")
                            data = stream.read()
                            prefix = data[:64]
                            self.check_module(name, data, release, full, kernel_build)
                        else:
                            prefix = stream.read(64)
                            firmware_text = "/firmware/" in name and "43455" in name and name.endswith(".txt")
                            if name in wanted or firmware_text:
                                require(member.size <= 1024 * 1024, f"Unexpectedly large configuration/script: {name}")
                                self.text[name] = prefix + stream.read()
                self.entries[name] = (member, prefix)
            while decoded.read(1024 * 1024):
                pass

    def check_module(self, name, data, release, full, kernel_build):
        match = re.fullmatch(r"(?:usr/)?lib/modules/([^/]+)/kernel/(.+\.ko)", name)
        require(match is not None and match[1] == release, f"Module location/release differs from vmlinux: {name}")
        relative = match[2]
        source = kernel_build / relative
        require(source.is_file() and source.resolve().is_relative_to(kernel_build.resolve()),
                f"Matching original kernel-build module is absent: {relative}")
        sections, _ = full.elf_sections(io.BytesIO(data), name, 1)
        require(".modinfo" in sections, f"Missing kernel module metadata: {name}")
        info = sections[".modinfo"]
        metadata = data[info[4]:info[4] + info[5]].split(b"\0")
        vermagic = next((entry.removeprefix(b"vermagic=") for entry in metadata
                         if entry.startswith(b"vermagic=")), b"")
        require(vermagic.split(b" ", 1)[0] == release.encode(), f"Module vermagic differs from vmlinux: {name}")
        with source.open("rb") as original:
            expected = hashlib.file_digest(original, "sha256").hexdigest()
        actual = hashlib.sha256(data).hexdigest()
        require(actual == expected, f"Rootfs module differs from the original full-DWARF kernel build: {relative}")
        self.modules[relative] = actual
        # Linux treats '-' and '_' identically in module names; this kernel's
        # WCC filename is brcmfmac-wcc.ko while its module name is brcmfmac_wcc.
        canonical = PurePosixPath(relative).stem.replace("-", "_")
        dependencies = next((entry.removeprefix(b"depends=").decode("ascii") for entry in metadata
                             if entry.startswith(b"depends=")), "")
        aliases = [entry.removeprefix(b"alias=").decode("ascii") for entry in metadata if entry.startswith(b"alias=")]
        self.module_info[relative] = {"name": canonical,
                                      "depends": {name.replace("-", "_") for name in dependencies.split(",") if name},
                                      "aliases": aliases}

    def firmware(self, name, text=False):
        candidate = next((path for path in (f"lib/firmware/{name}", f"usr/lib/firmware/{name}")
                          if path in self.entries), None)
        require(candidate is not None, f"Missing RPi4 wireless firmware: {name}")
        resolved = self.resolve(candidate)
        member, _ = self.entries[resolved]
        require(member.isfile() and member.size > 0, f"Empty/non-file wireless firmware target: {name}")
        return self.read(candidate) if text else resolved


def check_preset_password(root):
    database = "etc/shadow" if "etc/shadow" in root.entries else "etc/passwd"
    fields = next((line.split(":") for line in root.read(database).splitlines() if line.startswith("root:")), None)
    require(fields is not None and len(fields) >= 2 and fields[1].startswith("$6$"),
            "Root account does not have the preset SHA-512 crypt password")
    stored = fields[1].encode("ascii")
    library = ctypes.util.find_library("crypt")
    require(library is not None, "Host libcrypt is required to verify the preset password")
    crypt = ctypes.CDLL(library).crypt
    crypt.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
    crypt.restype = ctypes.c_char_p
    actual = crypt(b"Rpi4GPIO-2026!", stored)
    require(actual is not None and hmac.compare_digest(actual, stored), "Root preset password verification failed")


def check_loading_metadata(root, release):
    """Verify depmod's load graph and SDIO aliases for the actual small set."""
    def metadata_text(name):
        candidate = next((path for path in (f"lib/modules/{release}/{name}", f"usr/lib/modules/{release}/{name}")
                          if path in root.entries), None)
        require(candidate is not None, f"Missing module-loading metadata: {name}")
        return root.read(candidate)

    installed = {f"kernel/{relative}": info for relative, info in root.module_info.items()}
    by_name = {info["name"]: path for path, info in installed.items()}
    require(len(by_name) == len(installed), "Installed modules have colliding canonical module names")
    graph = {}
    for line in metadata_text("modules.dep").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        require(":" in line, "Malformed modules.dep entry")
        name, values = line.split(":", 1)
        name = name.strip()
        require(name in installed and name not in graph, f"modules.dep references a missing or duplicate module: {name}")
        dependencies = values.split()
        require(all(path in installed for path in dependencies), f"modules.dep dependency is absent from rootfs: {name}")
        require(name not in dependencies, f"Module depends on itself: {name}")
        graph[name] = set(dependencies)
    require(set(graph) == set(installed), "modules.dep does not cover every installed module")
    for path, info in installed.items():
        listed = {installed[dependency]["name"] for dependency in graph[path]}
        require(info["depends"] <= listed, f"modules.dep omits a dependency from the module ELF: {path}")

    # Check both known Broadcom device IDs rather than relying on depmod's
    # spacing or hexadecimal capitalization. 43455 is SDIO device ID 0xA9BF.
    aliases = []
    for line in metadata_text("modules.alias").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        require(len(fields) == 3 and fields[0] == "alias", "Malformed modules.alias entry")
        target = fields[2].replace("-", "_")
        require(target in by_name, f"modules.alias references an uninstalled module: {target}")
        aliases.append((fields[1].lower(), target))
    require("brcmfmac" in by_name and "brcmfmac_wcc" in by_name, "Broadcom SDIO/WCC load graph is incomplete")
    brcmfmac = installed[by_name["brcmfmac"]]
    for device in ("4345", "a9bf"):
        modalias = f"sdio:c00v02d0d{device}"
        require(any(target == "brcmfmac" and fnmatch.fnmatchcase(modalias, pattern) for pattern, target in aliases),
                f"SDIO device {device} does not resolve to brcmfmac in modules.alias")
        require(any(fnmatch.fnmatchcase(modalias, pattern.lower()) for pattern in brcmfmac["aliases"]),
                f"Installed brcmfmac ELF does not support SDIO device {device}")
    require("brcmfmac" in installed[by_name["brcmfmac_wcc"]]["depends"], "WCC's brcmfmac dependency is missing")
    require({"brcmutil", "cfg80211"} <= brcmfmac["depends"], "Broadcom wireless driver dependencies are missing")


def check_rootfs(path, release, full, kernel_build):
    root = WiFiRootfs(path, release, full, kernel_build)
    for name in ("sbin/init", "bin/sh", "usr/sbin/sshd", "usr/bin/ssh-keygen",
                 "usr/bin/gpiodetect", "usr/bin/gpioinfo", "usr/bin/gpioset",
                 "usr/sbin/wpa_supplicant", "usr/sbin/wpa_passphrase", "usr/sbin/wpa_cli", "usr/sbin/avahi-daemon",
                 "sbin/modprobe", "usr/sbin/rfkill"):
        root.executable(name)
    for name in ("etc/init.d/sshd", "etc/init.d/networking", f"etc/init.d/{SETUP}",
                 f"usr/sbin/{SETUP}", "etc/init.d/avahi-daemon"):
        root.executable(name, elf=False)
    users = {line.split(":", 1)[0]: line.split(":") for line in root.read("etc/passwd").splitlines()}
    require("root" in users and "sshd" in users, "Root or SSH privilege-separation account is absent")
    require(len(users["root"]) == 7 and users["root"][2] == "0" and users["root"][6] not in ("/bin/false", "/sbin/nologin"),
            "Root does not have a usable login account")
    check_preset_password(root)

    main = root.read("etc/ssh/sshd_config")
    require(any(line.split("#", 1)[0].strip() == "Include /etc/ssh/sshd_config.d/*.conf"
                for line in main.splitlines()), "sshd does not include the local configuration")
    local = SUPPORT.active_options(root.read("etc/ssh/sshd_config.d/00-local.conf"))
    for key, value in {"port": "22", "addressfamily": "inet", "permitrootlogin": "yes",
                       "passwordauthentication": "yes", "permitemptypasswords": "no", "pubkeyauthentication": "yes"}.items():
        require(local.get(key) == value, f"Unexpected SSH setting: {key}")
    require(SUPPORT.active_options(main).get("permitemptypasswords", "no") != "yes", "Empty-password SSH was enabled")

    interface_lines = [line.split("#", 1)[0].strip() for line in root.read("etc/network/interfaces").splitlines()]
    for line in ("auto lo", "iface lo inet loopback", "auto eth0", "iface eth0 inet dhcp"):
        require(line in interface_lines, f"Missing wired DHCP fallback: {line}")
    require(any(name in root.entries for name in ("usr/share/udhcpc/default.script", "etc/udhcpc.d/50default")),
            "BusyBox DHCP configuration script is missing")
    require("etc/network/if-pre-up.d/wpa-supplicant" in root.entries and
            "etc/network/if-post-down.d/wpa-supplicant" in root.entries,
            "Wi-Fi ifup/ifdown integration scripts are missing")
    for name in ROOTFS_TEMPLATES:
        require(root.read(f"usr/share/rpi4-setup/{name}").strip(), f"Missing headless template: {name}")
    importer = root.read(f"usr/sbin/{SETUP}")
    for token in ("network-config", "SSID", "PASSWORD", "wpa_passphrase", "wlan0", "setup-result.txt"):
        require(token in importer, f"Wi-Fi importer lacks expected support: {token}")

    require(any(level == "S" and number == 39 for level, number, _ in root.starts(SETUP)),
            "Headless importer is not enabled at rcS priority 39")
    for service in ("networking", "sshd", "avahi-daemon"):
        starts = root.starts(service)
        require(starts and any(level in "2345" for level, _, _ in starts), f"Service is not enabled in normal runlevels: {service}")
        require(all(level != "S" or number > 39 for level, number, _ in starts),
                f"Service starts before headless import: {service}")
    require(any(line and not line.startswith("#") and ":sysinit:" in line and "/etc/init.d/rcS" in line
                for line in root.read("etc/inittab").splitlines()), "SysVinit does not run rcS before normal startup")
    require(root.read("etc/hostname").strip() == "rpi4-debug", "Unexpected configured hostname")
    avahi_config = root.read("etc/avahi/avahi-daemon.conf")
    require(re.search(r"(?m)^\s*use-ipv6\s*=\s*no\s*$", avahi_config),
            "Avahi is not configured for IPv4-only mDNS")
    if re.search(r"(?m)^\s*enable-dbus\s*=\s*yes\s*$", avahi_config):
        root.executable("usr/bin/dbus-daemon")
        root.executable("etc/init.d/dbus-1", elf=False)
        dbus_starts = root.starts("dbus-1")
        require(any(level in "235" for level, _, _ in dbus_starts), "Avahi requires D-Bus but its service is not enabled")
        for level, priority, _ in root.starts("avahi-daemon"):
            if level in "235":
                require(any(dbus_level == level and dbus_priority < priority
                            for dbus_level, dbus_priority, _ in dbus_starts), "D-Bus does not start before Avahi")

    require("brcmfmac" in [line.split("#", 1)[0].strip()
                          for line in root.read("etc/modules-load.d/rpi4-wifi.conf").splitlines()],
            "Broadcom Wi-Fi module is not configured for boot loading")
    root.executable("etc/init.d/modutils.sh", elf=False)
    require(any(level == "S" and priority == 6 for level, priority, _ in root.starts("modutils.sh")),
            "Kernel module loader is not enabled at rcS priority 06")

    required = {"brcmfmac", "brcmfmac_wcc", "brcmutil", "cfg80211", "rfkill"}
    found = {info["name"] for info in root.module_info.values()}
    require(required <= found, f"Missing required RPi4 wireless modules: {sorted(required - found)}")
    check_loading_metadata(root, release)
    # brcmfmac first requests the board-specific names supplied by the RPi
    # firmware package; generic .bin/.clm_blob fallbacks need not be installed.
    root.firmware("brcm/brcmfmac43455-sdio.raspberrypi,4-model-b.bin")
    root.firmware("brcm/brcmfmac43455-sdio.raspberrypi,4-model-b.clm_blob")
    nvram = root.firmware("brcm/brcmfmac43455-sdio.raspberrypi,4-model-b.txt", text=True)
    require(re.search(r"(?m)^boardtype=\S+", nvram) and re.search(r"(?m)^boardrev=\S+", nvram),
            "RPi4-specific Wi-Fi NVRAM lacks board calibration fields")
    root.firmware("regulatory.db")
    root.firmware("regulatory.db.p7s")
    return len(root.entries), sorted(found)


def check_boot_templates(path, deploy, focused):
    with lzma.open(path, "rb") as stream:
        header = stream.read(512)
        require(len(header) == 512 and header[510:512] == b"\x55\xaa", "Missing WIC partition table")
        partition = struct.unpack_from("<B3sB3sII", header, 446)
        offset, size = partition[4] * 512, partition[5] * 512
        require(512 <= offset and 0 < size <= 512 * 1024**2, "Invalid boot partition bounds")
        stream.seek(offset)
        data = stream.read(size)
        require(len(data) == size, "Truncated FAT boot partition")
        read = focused.fat_files(data)
        for name in BOOT_FILES:
            original = deploy / "rpi4-headless-bootfiles" / name
            require(original.is_file(), f"Missing deployed Wi-Fi boot template: {name}")
            require(hashlib.sha256(read(name.lower())).digest() == hashlib.sha256(original.read_bytes()).digest(),
                    f"Wi-Fi boot template differs from deployment: {name}")
        network = read("network-config").decode("utf-8-sig")
        for key in ("SSID", "PASSWORD"):
            require(re.search(rf"(?m)^{key}=.*$", network), f"Windows-editable Wi-Fi key absent: {key}")
        require(any(line.strip() == "enable_uart=1" for line in read("config.txt").decode().splitlines()),
                "Serial UART is not enabled in firmware config")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deploy_dir", nargs="?", type=Path, default=PROJECT / "build/tmp/deploy/images" / MACHINE)
    parser.add_argument("--kernel-build-dir", type=Path, default=KERNEL_BUILD,
                        help="retained original full-DWARF kernel build used for module SHA-256 checks")
    args = parser.parse_args()
    deploy = args.deploy_dir
    focused = SUPPORT.focused_verifier()
    full = focused.original_verifier()
    release = focused.check_kernel(deploy / "rpi4-kernel-debug")
    config = set((deploy / "rpi4-kernel-debug/kernel.config").read_text().splitlines())
    for option in ("GPIO_CDEV", "PINCTRL_BCM2835", "BRCMFMAC_SDIO"):
        require(f"CONFIG_{option}=y" in config, f"Required GPIO/SDIO kernel support is absent: {option}")
    prefix = deploy / f"{IMAGE}-{MACHINE}.rootfs"
    outputs = {suffix: Path(str(prefix) + suffix) for suffix in (".tar.bz2", ".wic.xz", ".wic.bmap")}
    for path in outputs.values():
        require(path.is_file() and path.stat().st_size > 0, f"Missing Wi-Fi image output: {path}")
    require(len({path.resolve(strict=True).name.removesuffix(suffix) for suffix, path in outputs.items()}) == 1,
            "Wi-Fi rootfs, WIC and bmap are from different build timestamps")
    count, modules = check_rootfs(outputs[".tar.bz2"], release, full, args.kernel_build_dir)
    check_boot_templates(outputs[".wic.xz"], deploy, focused)
    focused.check_wic(outputs[".wic.xz"], deploy)
    print(f"Wi-Fi SSH image verified: {outputs['.wic.xz'].name}; {count} rootfs entries; real AArch64 SSH/WPA/GPIO/mDNS tools")
    print(f"Wireless modules verified: {len(modules)} ({', '.join(modules)}); each ET_REL AArch64, complete DWARF4, correct vermagic and byte-identical to original kernel build")
    print("Module loading verified: installed-only modules.dep closure, ELF dependency coverage, 4345/43455 SDIO aliases to brcmfmac and WCC dependency chain")
    if len(modules) > 20:
        print("NOTE: Wireless image has more than 20 modules; inspect the installed dependency scope")
    print("Access verified: preset root password, IPv4 SSH policy, rpi4-debug mDNS, boot SSID/PASSWORD template, rcS39 import before networking/sshd, wired DHCP fallback")
    print(f"Kernel verified: Linux {release}, exact pins, complete DWARF4; RPi4 Wi-Fi firmware/NVRAM/regdb, FAT kernel/DTB hashes, ext4 and partition bounds")
    print("Artifact checks only; physical Raspberry Pi boot, Wi-Fi association, SSH/mDNS reachability, GPIO electrical behavior and KGDB/JTAG were not tested")


if __name__ == "__main__":
    try:
        main()
    except (OSError, EOFError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, lzma.LZMAError) as exc:
        print(f"Wi-Fi SSH artifact verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
