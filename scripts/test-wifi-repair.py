#!/usr/bin/env python3
"""Validate repair cpio and execute patch/idempotence/refusal cases on fixtures."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("builder", PROJECT / "scripts/build-wifi-repair.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def parse_cpio(data):
    result = {}
    pos = 0
    while True:
        assert data[pos:pos + 6] == b"070701", "Invalid newc magic"
        fields = [int(data[pos + 6 + index * 8:pos + 14 + index * 8], 16) for index in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        name = data[pos + 110:pos + 110 + namesize - 1].decode()
        assert fields[2:4] == [0, 0] and fields[12] == 0
        assert data[pos + 109 + namesize] == 0
        pos = (pos + 110 + namesize + 3) & ~3
        payload = data[pos:pos + size]
        assert len(payload) == size
        pos = (pos + size + 3) & ~3
        if name == "TRAILER!!!":
            assert not any(data[pos:])
            return result
        assert name not in result and not name.startswith("/") and ".." not in Path(name).parts
        result[name] = (mode, payload, fields)


def main(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for line in archive.read("SHA256SUMS").decode().splitlines():
            expected, name = line.split("  ", 1)
            assert builder.digest(archive.read(name)) == expected
        metadata = json.loads(archive.read("repair-manifest.json"))
        entries = parse_cpio(gzip.decompress(archive.read(builder.INITRAMFS)))
        assert archive.read("config.txt").count(b"initramfs rpi4-wifi-fix.cpio.gz followkernel") == 1
        assert archive.read("config.txt").startswith(builder.DEFAULT_CONFIG.read_bytes())
    assert stat.S_ISCHR(entries["dev/console"][0]) and entries["dev/console"][2][9:11] == [5, 1]
    for name, expected in metadata["aarch64_runtime_sha256"].items():
        assert builder.digest(entries[name][1]) == expected
    for name, expected in metadata["payload_sha256"].items():
        assert builder.digest(entries["repair/" + name][1]) == expected
    with tempfile.TemporaryDirectory(prefix="rpi4-repair-test-") as temporary:
        base = Path(temporary)
        root, boot, payload = base / "root", base / "boot", base / "payload"
        for folder in root, boot, payload:
            folder.mkdir()
        init = base / "init"
        init.write_bytes(entries["init"][1])
        subprocess.run(["sh", "-n", str(init)], check=True)
        for name, (mode, data, _) in entries.items():
            if name.startswith("repair/") and stat.S_ISREG(mode):
                target = payload / name.removeprefix("repair/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(mode & 0o777)
        (root / ".rpi4-repair-test-root").touch()
        (root / "etc").mkdir()
        (root / "etc/hostname").write_text("rpi4-debug\n")
        (root / "lib/modules/6.12.93-v8").mkdir(parents=True)
        (root / "usr/sbin").mkdir(parents=True)
        target = root / "usr/sbin/rpi4-headless-setup"
        original = (builder.DEFAULT_ROOT / "usr/sbin/rpi4-headless-setup").read_bytes()
        target.write_bytes(original)
        network = b"SSID=fixture-only\nPASSWORD=fixture-secret\n"
        (boot / "network-config").write_bytes(network)
        command = ["sh", str(init), "--test", str(root), str(boot), str(payload)]
        subprocess.run(command, check=True, capture_output=True)
        assert builder.digest(target.read_bytes()) == metadata["new_importer_sha256"]
        assert (root / "var/lib/rpi4-setup/rpi4-headless-setup.before-wifi-v2").read_bytes() == original
        assert (boot / "network-config").read_bytes() == network
        assert b"fixture-secret" not in (boot / "repair-result.txt").read_bytes()
        for level in (2, 3, 4, 5):
            assert os.readlink(root / f"etc/rc{level}.d/S22rpi4-network-status") == "../init.d/rpi4-network-status"
        mtime = target.stat().st_mtime_ns
        subprocess.run(command, check=True, capture_output=True)
        assert target.stat().st_mtime_ns == mtime
        target.write_bytes(b"custom importer\n")
        subprocess.run(command, check=True, capture_output=True)
        assert target.read_bytes() == b"custom importer\n"
        assert b"SKIPPED" in (boot / "repair-result.txt").read_bytes()
        target.write_bytes(original)
        (root / "etc/hostname").write_text("other-system\n")
        subprocess.run(command, check=True, capture_output=True)
        assert target.read_bytes() == original
        (root / "etc/hostname").write_text("rpi4-debug\n")
        (payload / "usr/sbin/rpi4-network-status").write_text("corrupted\n")
        subprocess.run(command, check=True, capture_output=True)
        assert target.read_bytes() == original
    print("PASS: ZIP/newc hashes, AArch64 runtime, console node, patch, idempotence, unknown-root/importer and corrupt-payload refusal; credentials retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=Path("/workspace/rpi4-release/rpi4-wifi-repair-v2.zip"))
    main(parser.parse_args().archive)
