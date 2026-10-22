#!/usr/bin/env python3
"""Check sanitized network-status reports with isolated files and command mocks.

No real host interface, mount, credentials or service is changed. These tests
exercise report decisions, not wireless association or target execution.
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT / "meta-rpi4-debug/recipes-core/rpi4-headless-setup/files/rpi4-network-status"
checks = []

with tempfile.TemporaryDirectory(prefix="rpi4-network-status-", dir="/tmp") as temporary:
    base = Path(temporary)
    helper = base / "bin"
    helper.mkdir()
    program = '''#!/usr/bin/env python3
from pathlib import Path
import json, os, sys
data = json.loads(Path(os.environ["RPI4_STATUS_FIXTURE"]).read_text())
name = Path(sys.argv[0]).name
if name == "wpa_cli":
    assert sys.argv[1:] == ["-i", "wlan0", "status"]
    print(data.get("wpa", ""))
    sys.exit(data.get("wpa_exit", 0))
if name == "ip":
    assert sys.argv[1:5] == ["-4", "addr", "show", "dev"]
    print(data.get(sys.argv[5], ""))
    sys.exit(0)
raise SystemExit("Unexpected helper")
'''
    for name in ("ip", "wpa_cli"):
        (helper / name).write_text(program)
        (helper / name).chmod(0o755)
    environment = dict(os.environ, PATH=str(helper) + os.pathsep + os.environ["PATH"])

    def make_fixture(name, wpa="", wlan="", eth="", present=True, listener=False, configured=True, wpa_exit=0):
        directory = base / name
        root = directory / "root"
        boot = directory / "boot"
        for subpath in ("etc", "proc/net", "sys/class/net"):
            (root / subpath).mkdir(parents=True, exist_ok=True)
        boot.mkdir()
        (root / ".rpi4-network-status-test-root").touch()
        if configured:
            (root / "etc/wpa_supplicant.conf").write_text("fixture configuration, not real credentials\n")
        if present:
            (root / "sys/class/net/wlan0").mkdir()
        (root / "proc/net/tcp").write_text(
            "  sl  local_address rem_address   st\n" +
            ("   0: 00000000:0016 00000000:0000 0A\n" if listener else "")
        )
        data = directory / "commands.json"
        data.write_text(json.dumps({"wpa": wpa, "wpa_exit": wpa_exit, "wlan0": wlan, "eth0": eth}))
        return root, boot, data

    def run(fixture, expected=0):
        root, boot, data = fixture
        done = subprocess.run(
            ["sh", str(SCRIPT), "--root", str(root), "--boot", str(boot)],
            env=dict(environment, RPI4_STATUS_FIXTURE=str(data)),
            capture_output=True, text=True, timeout=12,
        )
        assert done.returncode == expected, (done.returncode, done.stdout, done.stderr)
        if expected:
            return ""
        status = (boot / "network-status.txt").read_text()
        assert status == (root / "var/lib/rpi4-setup/network-status.txt").read_text()
        assert not (root / "run/rpi4-network-status.lock").exists()
        assert not (boot / "network-status.txt.tmp").exists()
        assert "PRIVATE_SSID" not in status and "PRIVATE_PSK" not in status
        return status

    f = make_fixture("absent", present=False)
    status = run(f)
    assert "wlan0 is missing" in status and "readiness" in status
    checks.append("Missing wlan0 is not reported as connected")

    f = make_fixture("no-supplicant", wpa="Failed to connect to non-global ctrl_ifname: wlan0", wpa_exit=255)
    status = run(f)
    assert "state: UNAVAILABLE" in status and "control interface unavailable" in status
    checks.append("Present interface with absent supplicant is distinguished from association")

    f = make_fixture("scanning", wpa="wpa_state=SCANNING\nssid=PRIVATE_SSID\npsk=PRIVATE_PSK")
    status = run(f)
    assert "state: SCANNING" in status and "association/authentication not complete" in status
    checks.append("Scanning is pending and raw WPA data is not copied")

    f = make_fixture("dhcp", wpa="wpa_state=COMPLETED", listener=True)
    status = run(f)
    assert "associated, waiting for IPv4" in status and "Wi-Fi SSH:" not in status
    checks.append("Association without DHCP does not claim SSH access")

    address = "    inet 192.168.50.17/24 brd 192.168.50.255 scope global wlan0\n"
    f = make_fixture("ready", wpa="wpa_state=COMPLETED\nssid=PRIVATE_SSID\npsk=PRIVATE_PSK", wlan=address, listener=True)
    status = run(f)
    assert "ssh root@192.168.50.17 -p 22" in status and "network and SSH listener ready" in status
    assert "client reachability is not tested" in status
    first_stat = (f[1] / "network-status.txt").stat()
    assert run(f) == status
    assert (f[1] / "network-status.txt").stat().st_mtime_ns == first_stat.st_mtime_ns
    checks.append("Association plus IPv4 plus listener yields endpoint without overstating reachability")
    checks.append("Identical status does not rewrite FAT")

    f = make_fixture("ssh-not-listening", wpa="wpa_state=COMPLETED", wlan=address)
    status = run(f)
    assert "no TCP/22 listener" in status and "Wi-Fi SSH:" not in status
    checks.append("Assigned IP without sshd listener does not claim SSH readiness")

    f = make_fixture("ethernet-fallback", wpa="wpa_state=DISCONNECTED", eth="inet 10.0.0.7/24 scope global eth0", listener=True)
    status = run(f)
    assert "Ethernet SSH: ssh root@10.0.0.7 -p 22" in status
    assert "without confirming Wi-Fi" in status
    checks.append("Ethernet access is reported while Wi-Fi failure remains visible")

    f = make_fixture("malformed", wpa="wpa_state=PRIVATE_SSID\npsk=PRIVATE_PSK", wlan="inet 999.2.3.4/24\ninet 169.254.1.2/16\ninet 127.0.0.1/8")
    status = run(f)
    assert "state: UNAVAILABLE" in status and "wlan0 IPv4: none" in status
    checks.append("Unrecognized WPA states and invalid/link-local/loopback addresses are excluded")

    f = make_fixture("unsafe")
    (f[0] / "escape").symlink_to("/etc/passwd")
    run(f, 2)
    (f[0] / "escape").unlink()
    (f[0] / ".rpi4-network-status-test-root").unlink()
    run(f, 2)
    checks.append("Fixture mode rejects symlinks and unmarked roots before writes")

print(json.dumps({"passed": True, "hardware_tested": False, "checks": checks}, indent=2))
