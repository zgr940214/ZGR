#!/usr/bin/env python3
"""Build a small, auditable FAT-only repair for the known Wi-Fi image."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import stat
import struct
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT / "meta-rpi4-debug/recipes-core/rpi4-headless-setup/files"
OLD_HASH = "e21711d54fb66ce264fb38e3e6ae12d00b95a80a1558eed6af6d07a820261956"
DEFAULT_ROOT = Path("/tmp/rpi4-aarch64-smoke-lheeftmu/final-wifi-rootfs-20261022T061415Z")
DEFAULT_CONFIG = Path("/workspace/attachments/1bc49e6e-1571-439a-bca0-d71ad94978ac/config.txt")
INITRAMFS = "rpi4-wifi-fix.cpio.gz"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def newc(entries):
    archive = bytearray()
    for ino, (name, mode, data, major, minor) in enumerate(entries + [("TRAILER!!!", 0, b"", 0, 0)], 1):
        encoded = name.encode() + b"\0"
        fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0)
        archive.extend(b"070701" + b"".join(f"{value:08x}".encode() for value in fields))
        archive.extend(encoded)
        archive.extend(b"\0" * (-len(archive) % 4))
        archive.extend(data)
        archive.extend(b"\0" * (-len(archive) % 4))
    archive.extend(b"\0" * (-len(archive) % 512))
    return bytes(archive)


def build(root, config, output):
    original = (root / "usr/sbin/rpi4-headless-setup").read_bytes()
    if digest(original) != OLD_HASH:
        raise ValueError("Reference rootfs is not the original published Wi-Fi image")
    fixed = (SOURCE / "rpi4-headless-setup").read_bytes()
    if b"hexdump -v -e" not in fixed or b"network-format" not in fixed or digest(fixed) == OLD_HASH:
        raise ValueError("The validated v2 importer fix is not ready")
    initial_config = config.read_bytes()
    active = [line.strip() for line in initial_config.decode("utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if any(line.startswith(("initramfs ", "ramfsfile=", "ramfsaddr=", "auto_initramfs=")) for line in active):
        raise ValueError("The supplied boot config already has an initramfs configuration")
    fixed_config = initial_config + (b"" if initial_config.endswith(b"\n") else b"\n") + b"\n# Temporary Wi-Fi importer repair; remove this line after successful startup.\ninitramfs " + INITRAMFS.encode() + b" followkernel\n"
    init = (SOURCE / "rpi4-wifi-repair-init").read_bytes().replace(b"@OLD_HASH@", OLD_HASH.encode()).replace(b"@NEW_HASH@", digest(fixed).encode())
    entries = []
    dirs = ["bin", "sbin", "usr", "usr/bin", "usr/sbin", "lib", "proc", "sys", "dev", "newroot", "boot", "repair", "repair/usr", "repair/usr/sbin", "repair/etc", "repair/etc/init.d"]
    for name in dirs:
        entries.append((name, stat.S_IFDIR | 0o755, b"", 0, 0))
    entries.append(("dev/console", stat.S_IFCHR | 0o600, b"", 5, 1))
    elf_hashes = {}
    for name in ["bin/busybox.nosuid", "lib/ld-linux-aarch64.so.1", "lib/libc.so.6", "lib/libm.so.6"]:
        data = (root / name).read_bytes()
        if data[:5] != b"\x7fELF\x02" or struct.unpack_from("<H", data, 18)[0] != 183:
            raise ValueError(f"Expected AArch64 ELF: {name}")
        entries.append((name, stat.S_IFREG | 0o755, data, 0, 0))
        elf_hashes[name] = digest(data)
    for applet in ["sh", "mkdir", "mount", "umount", "cat", "sleep", "cp", "mv", "chmod", "chown", "sha256sum", "awk", "readlink", "ln", "sync", "switch_root"]:
        entries.append(("bin/" + applet, stat.S_IFLNK | 0o777, b"busybox.nosuid", 0, 0))
    entries.append(("init", stat.S_IFREG | 0o755, init, 0, 0))
    # Install the status service first and replace the importer last.
    payloads = {
        "usr/sbin/rpi4-network-status": (SOURCE / "rpi4-network-status").read_bytes(),
        "etc/init.d/rpi4-network-status": (SOURCE / "rpi4-network-status.init").read_bytes(),
        "usr/sbin/rpi4-headless-setup": fixed,
    }
    manifest = "".join(f"{digest(data)} 0755 {name}\n" for name, data in payloads.items()).encode()
    entries.append(("repair/manifest", stat.S_IFREG | 0o600, manifest, 0, 0))
    for name, data in payloads.items():
        entries.append(("repair/" + name, stat.S_IFREG | 0o755, data, 0, 0))
    packed = gzip.compress(newc(entries), compresslevel=9, mtime=0)
    readme = """RPi4 Wi-Fi v2 修复（不用重刷，不用修改 SSID/PASSWORD）

1. 关闭树莓派，将 SD 卡插回电脑。
2. 把本 ZIP 的 config.txt 和 rpi4-wifi-fix.cpio.gz 复制到 SD 卡可见启动分区根目录；覆盖 config.txt。
   config.txt 基于你提供的原文件，只增加一条 initramfs 启动指令。
3. 保留现有 network-config，弹出 SD 卡，再启动树莓派，等待约 2 分钟。
4. 若仍未联网，关机后将启动分区 repair-result.txt 和 network-status.txt 发回。
   日志不会包含 Wi-Fi 密码。network-status.txt 会记录接口、关联状态、IP 和 SSH 状态。
5. 联网确认后，可删除 config.txt 最后两行修复说明/指令，再删除 rpi4-wifi-fix.cpio.gz。
   保留修复指令重复启动也安全；修复脚本只接受指定镜像和已知导入器版本。

修复内容：SSID 编码改用目标 BusyBox 支持的 hexdump，修复旧导入缓存，并安装网络状态报告服务。
内核、调试符号、SSH 用户名密码、现有 network-config 均不改变。原导入器备份保存在
/var/lib/rpi4-setup/rpi4-headless-setup.before-wifi-v2。

此包已做归档完整性和脚本验证；云环境没有树莓派射频硬件，未声明实机启动或无线关联已验证。
""".encode()
    metadata = {
        "kernel_release": "6.12.93-v8", "old_importer_sha256": OLD_HASH,
        "new_importer_sha256": digest(fixed), "original_config_sha256": digest(initial_config),
        "initramfs_sha256": digest(packed), "aarch64_runtime_sha256": elf_hashes,
        "payload_sha256": {name: digest(data) for name, data in payloads.items()},
        "hardware_boot_verified": False,
    }
    files = {"config.txt": fixed_config, INITRAMFS: packed, "README.txt": readme,
             "repair-manifest.json": (json.dumps(metadata, indent=2) + "\n").encode()}
    files["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in files.items()).encode()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "rpi4-wifi-repair-v2.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    (output / "rpi4-wifi-repair-v2.zip.sha256").write_text(f"{digest(destination.read_bytes())}  {destination.name}\n")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=Path("/workspace/rpi4-release"))
    args = parser.parse_args()
    print(build(args.rootfs, args.config, args.output))
