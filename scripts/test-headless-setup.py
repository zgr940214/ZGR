#!/usr/bin/env python3
"""Exercise the FAT setup importer using isolated fixture files and a PBKDF2 helper mock."""
from pathlib import Path
import base64, hashlib, json, os, shutil, stat, struct, subprocess, tempfile
PROJECT=Path(__file__).resolve().parent.parent
SCRIPT=PROJECT/'meta-rpi4-debug/recipes-core/rpi4-headless-setup/files/rpi4-headless-setup'
environment=os.environ.copy()
root=Path(tempfile.mkdtemp(prefix='headless-setup-fixture-',dir='/tmp'))
fixture=root/'root'; boot=root/'boot'
(fixture/'etc/network').mkdir(parents=True); (fixture/'home/root').mkdir(parents=True); boot.mkdir()
(fixture/'.rpi4-setup-test-root').touch()
(fixture/'etc/passwd').write_text('root::0:0:root:/home/root:/bin/sh\nnobody:x:65534:65534:nobody:/:/bin/false\n')
(fixture/'etc/network/interfaces').write_text('existing\n')
key_blob=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
key='ssh-ed25519 '+base64.b64encode(key_blob).decode()+' fixture-public-key-only\n'
results=[]
def run(expected=0):
 p=subprocess.run(['sh',str(SCRIPT),'--root',str(fixture),'--boot',str(boot)],capture_output=True,text=True,env=environment)
 assert p.returncode==expected,(p.returncode,p.stdout,p.stderr,(boot/'setup-result.txt').read_text())
 return (boot/'setup-result.txt').read_text()
def result(name): results.append({'name':name,'passed':True})
(boot/'network-config').write_bytes(b'\xef\xbb\xbfINTERFACE=eth0\r\nMODE=dhcp\r\n')
(boot/'authorized_keys').write_bytes(b'\xef\xbb\xbf'+key.replace('\n','\r\n').encode())
s=run(); assert 'Network: applied (dhcp)' in s and 'SSH public keys: imported for root' in s
assert (fixture/'etc/network/interfaces').read_text()=='auto lo\niface lo inet loopback\n\nauto eth0\niface eth0 inet dhcp\n'
assert (fixture/'home/root/.ssh/authorized_keys').read_text()==key
assert stat.S_IMODE((fixture/'home/root/.ssh').stat().st_mode)==0o700
assert stat.S_IMODE((fixture/'home/root/.ssh/authorized_keys').stat().st_mode)==0o600
result('Windows UTF8 BOM + CRLF, DHCP, valid OpenSSH public key and permissions')
(fixture/'etc/network/interfaces').write_text('local-network-edit\n')
(fixture/'home/root/.ssh/authorized_keys').write_text('local-key-edit\n')
s=run(); assert 'local edits preserved' in s
assert (fixture/'etc/network/interfaces').read_text()=='local-network-edit\n'
assert (fixture/'home/root/.ssh/authorized_keys').read_text()=='local-key-edit\n'
result('Unchanged FAT files preserve subsequent on-board edits')
(boot/'network-config').write_text('INTERFACE=eth0\nMODE=static\nADDRESS=192.168.1.50\nNETMASK=255.255.255.0\nGATEWAY=192.168.1.1\nDNS=192.168.1.1 1.1.1.1\n')
s=run(); assert 'Network: applied (static)' in s
assert 'address 192.168.1.50' in (fixture/'etc/network/interfaces').read_text()
assert (fixture/'etc/resolv.conf').read_text()=='nameserver 192.168.1.1\nnameserver 1.1.1.1\n'
result('Static IPv4 and DNS')
previous=(fixture/'etc/network/interfaces').read_bytes()
injection=root/'MUST_NOT_EXIST'
(boot/'network-config').write_text(f'INTERFACE=eth0\nMODE=dhcp\nADDRESS=$(touch {injection})\n')
s=run(1); assert not injection.exists(); assert (fixture/'etc/network/interfaces').read_bytes()==previous
result('Shell injection rejected without execution or valid network replacement')
for bad in ['INTERFACE=eth0\nMODE=dhcp\nUNKNOWN=value\n','INTERFACE=eth0\nMODE=dhcp\nMODE=static\n','INTERFACE=eth0\nMODE=static\nADDRESS=999.1.1.1\nNETMASK=255.255.255.0\n']:
 (boot/'network-config').write_text(bad); run(1); assert (fixture/'etc/network/interfaces').read_bytes()==previous
result('Unknown/duplicate fields and invalid IPv4 rejected')
(boot/'network-config').unlink()
(boot/'authorized_keys').write_text(key+'not-a-valid-key\n')
previous_keys=(fixture/'home/root/.ssh/authorized_keys').read_bytes()
run(1); assert (fixture/'home/root/.ssh/authorized_keys').read_bytes()==previous_keys
result('Mixed valid/invalid keys rejected atomically')
(boot/'authorized_keys').unlink()
# This synthetic format-valid hash is test data, not a generated credential.
h='$6$fixturesalt$'+'A'*86
(boot/'userconf.txt').write_bytes(('\ufeffroot:'+h+'\r\n').encode())
s=run(); assert not (boot/'userconf.txt').exists()
assert (fixture/'etc/passwd').read_text().splitlines()[0].split(':')[1]==h
assert h not in s and h not in (fixture/'var/lib/rpi4-setup/headless-setup.done').read_text()
result('SHA512 crypt import without chpasswd, CRLF/BOM handling, secret file removal/no hash logs')
(boot/'userconf.txt').write_text('root:plaintext-password\n')
previous_password=(fixture/'etc/passwd').read_bytes()
run(1); assert (fixture/'etc/passwd').read_bytes()==previous_password and (boot/'userconf.txt').exists()
result('Plaintext/placeholder password rejected, previous credential retained')
(boot/'userconf.txt').write_text('root:'+h+'\n')
(fixture/'etc/shadow').write_text('root:!:20000:0:99999:7:::\nnobody:*:20000:0:99999:7:::\n')
run(); assert (fixture/'etc/shadow').read_text().splitlines()[0].split(':')[1]==h
assert stat.S_IMODE((fixture/'etc/shadow').stat().st_mode)==0o600
result('Shadow database preferred when present')
for args in [[],['--root','/','--boot',str(boot)],['--root',str(root),'--boot',str(boot)]]:
 if not args: continue
 p=subprocess.run(['sh',str(SCRIPT),*args],capture_output=True)
 assert p.returncode==2
result('Fixture mode refuses host root and unmarked roots')
recipe=SCRIPT.parent.parent/'rpi4-headless-setup_1.0.bb'
assert 'INITSCRIPT_PARAMS = "start 39 S ."' in recipe.read_text()
assert 'update-rc.d -r ${D} populate-volatile.sh start 37 S .' in (PROJECT/'sources/poky/meta/recipes-core/initscripts/initscripts_1.0.bb').read_text()
result('S39 import ordering after S37 volatile setup and before runlevel networking/SSHD')

# Test the fixture guard against absolute symlinks before any potential writes.
symlink_root=root/'symlink-root'; symlink_root.mkdir()
(symlink_root/'.rpi4-setup-test-root').touch()
(symlink_root/'escape').symlink_to('/run/resolv.conf')
p=subprocess.run(['sh',str(SCRIPT),'--root',str(symlink_root),'--boot',str(boot)],capture_output=True)
assert p.returncode==2
result('Fixture absolute symlink refused before any writes')

# The build host need not install WPA tools. This helper implements the exact
# WPA2 PBKDF2 primitive; the real target wpa_passphrase is tested separately.
bin_dir=root/'helper-bin'; bin_dir.mkdir()
# Some build hosts lack hexdump. The actual shipped BusyBox applet is exercised
# separately under AArch64 QEMU; this helper only keeps these host fixtures portable.
hexdump_mock=shutil.which('hexdump') is None
if hexdump_mock:
 hex_helper=bin_dir/'hexdump'
 hex_helper.write_text('''#!/usr/bin/env python3
from pathlib import Path
import sys
assert sys.argv[1:4]==['-v','-e','1/1 "%02x"']
print(Path(sys.argv[4]).read_bytes().hex(),end='')
''')
 hex_helper.chmod(0o755)
helper=bin_dir/'wpa_passphrase'
helper.write_text("""#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys
assert len(sys.argv)==2, 'The PSK must be passed on stdin, not argv'
ssid=sys.argv[1]
pw=sys.stdin.readline().removesuffix('\\n')
psk=hashlib.pbkdf2_hmac('sha1',pw.encode(),ssid.encode(),4096,32).hex()
record=Path(__file__).with_name('helper-calls.json')
data=json.loads(record.read_text()) if record.exists() else {'calls':0}
data['calls']+=1;data['only_ssid_in_argv']=True;data['password_received_on_stdin']=True
record.write_text(json.dumps(data))
print('network={')
print('    ssid=\\"'+ssid+'\\"')
print('    #psk=\\"'+pw+'\\"')
print('    psk='+psk)
print('}')
""")
helper.chmod(0o755)
environment['PATH']=str(bin_dir)+os.pathsep+environment['PATH']
(fixture/'etc/network/interfaces').write_text('auto lo\niface lo inet loopback\n\nauto eth0\niface eth0 inet dhcp\n')
(boot/'network-config').write_bytes((SCRIPT.parent/'network-config').read_bytes())
previous=(fixture/'etc/network/interfaces').read_bytes()
run(1);assert (fixture/'etc/network/interfaces').read_bytes()==previous
assert not (fixture/'etc/wpa_supplicant.conf').exists()
result('Only-two-field shipped placeholders are rejected while Ethernet remains usable')

ssid=' 书房 Wi"Fi\\=#$; '
password=' $;"\\= Wi-Fi #2026! '
text='SSID='+ssid+'\nPASSWORD='+password+'\n'
(boot/'network-config').write_bytes(b'\xef\xbb\xbf'+text.replace('\n','\r\n').encode())
status=run()
config=(fixture/'etc/wpa_supplicant.conf').read_text()
expected=hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex()
assert 'ssid='+ssid.encode().hex() in config and 'psk='+expected in config
assert 'country=CN' in config and 'key_mgmt=WPA-PSK' in config and 'ieee80211w=1' in config
assert password not in config and ssid not in config and '#psk=' not in config
assert stat.S_IMODE((fixture/'etc/wpa_supplicant.conf').stat().st_mode)==0o600
interfaces=(fixture/'etc/network/interfaces').read_text()
assert 'auto eth0\niface eth0 inet dhcp' in interfaces
assert 'auto wlan0\niface wlan0 inet dhcp' in interfaces
assert 'wpa-driver nl80211' in interfaces and 'wpa-conf /etc/wpa_supplicant.conf' in interfaces
calls=json.loads((bin_dir/'helper-calls.json').read_text())
assert calls['only_ssid_in_argv'] and calls['password_received_on_stdin']
assert password not in status and expected not in status and ssid not in status
for candidate in fixture.rglob('*'):
 if candidate.is_file():assert password.encode() not in candidate.read_bytes(),str(candidate)
result('Two fields default wlan0 DHCP/CN; UTF8/quotes/slashes/spaces retained; PSK stdin+hex SSID+hashed config only')

(fixture/'etc/network/interfaces').write_text('on-board network edit\n')
(fixture/'etc/wpa_supplicant.conf').write_text('on-board WPA edit\n')
run()
assert (fixture/'etc/network/interfaces').read_text()=='on-board network edit\n'
assert (fixture/'etc/wpa_supplicant.conf').read_text()=='on-board WPA edit\n'
assert json.loads((bin_dir/'helper-calls.json').read_text())['calls']==calls['calls']
result('Unchanged WiFi FAT configuration preserves on-board networking and WPA edits')

# Cards using the previous importer can have a remembered input hash but an
# invalid empty SSID. Updating the script must fix those without editing FAT.
(fixture/'var/lib/rpi4-setup/network-format').unlink()
(fixture/'etc/wpa_supplicant.conf').write_text('network={\n    ssid=\n}\n')
status=run()
assert 'Network: applied (dhcp)' in status
assert 'ssid='+ssid.encode().hex() in (fixture/'etc/wpa_supplicant.conf').read_text()
assert (fixture/'var/lib/rpi4-setup/network-format').read_text()=='2\n'
assert 'Result: configuration applied; see network-status.txt for connection status' in status
after_migration=json.loads((bin_dir/'helper-calls.json').read_text())['calls']
run()
assert json.loads((bin_dir/'helper-calls.json').read_text())['calls']==after_migration
result('Old cached empty-SSID configuration migrates once without changing FAT; status distinguishes import from association')

(boot/'network-config').write_text('SSID='+('a'*32)+'\nPASSWORD=fixture-password\n')
run()
assert 'ssid='+('61'*32) in (fixture/'etc/wpa_supplicant.conf').read_text()
result('32-byte repeated SSID encodes every byte without hexdump duplicate suppression')

saved_hex=(bin_dir/'hexdump').read_bytes() if (bin_dir/'hexdump').exists() else None
previous_network=(fixture/'etc/network/interfaces').read_bytes()
previous_wpa=(fixture/'etc/wpa_supplicant.conf').read_bytes()
previous_hash=(fixture/'var/lib/rpi4-setup/network.sha256').read_bytes()
(boot/'network-config').write_text('SSID=encoding-failure\nPASSWORD=fixture-password\n')
for body in ['exit 1',"printf '00'", "printf 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz'"]:
 (bin_dir/'hexdump').write_text('#!/bin/sh\n'+body+'\n');(bin_dir/'hexdump').chmod(0o755)
 status=run(1)
 assert 'SSID encoding' in status
 assert (fixture/'etc/network/interfaces').read_bytes()==previous_network
 assert (fixture/'etc/wpa_supplicant.conf').read_bytes()==previous_wpa
 assert (fixture/'var/lib/rpi4-setup/network.sha256').read_bytes()==previous_hash
if saved_hex is None:(bin_dir/'hexdump').unlink()
else:(bin_dir/'hexdump').write_bytes(saved_hex)
result('Failed, truncated and non-hex encoding rejected without replacing config or remembering input')

marker=Path('/tmp')/('wifi-injection-'+str(os.getpid()))
assert not marker.exists()
ssid='$(x);"\\ #'
password='$(touch '+str(marker)+');#'
assert 8<=len(password.encode())<=63
(boot/'network-config').write_text('SSID='+ssid+'\nPASSWORD='+password+'\n')
status=run()
config=(fixture/'etc/wpa_supplicant.conf').read_text()
assert not marker.exists()
expected=hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex()
assert 'ssid='+ssid.encode().hex() in config and 'psk='+expected in config
assert password not in config and password not in status
result('Shell syntax in WiFi values is literal data and never executed')
previous_network=(fixture/'etc/network/interfaces').read_bytes()
previous_wpa=(fixture/'etc/wpa_supplicant.conf').read_bytes()
for bad in [
 'SSID='+('名'*11)+'\nPASSWORD=12345678\n',
 'SSID=router\nPASSWORD=short\n',
 'SSID=router\nPASSWORD='+('Z'*64)+'\n',
 'SSID=router\nPASSWORD=12345678\nSSID=other\n',
 'SSID=router\nPASSWORD=12345678\nUNKNOWN=bad\n',
 'SSID=YOUR_WIFI_SSID\nPASSWORD=validpassword\n',
 'SSID=router\nPASSWORD=YOUR_WIFI_PASSWORD\n',
 'SSID=router\nPASSWORD=12345678\nREGDOM=xx\n',
]:
 (boot/'network-config').write_text(bad)
 run(1)
 assert (fixture/'etc/network/interfaces').read_bytes()==previous_network
 assert (fixture/'etc/wpa_supplicant.conf').read_bytes()==previous_wpa
result('Invalid WiFi lengths, placeholders, duplicate/unknown fields, country rejected without replacing settings')

raw_psk='B'*64
calls_before=json.loads((bin_dir/'helper-calls.json').read_text())['calls']
(boot/'network-config').write_text('SSID=RawPSK\nPASSWORD='+raw_psk+'\nREGDOM=US\n')
run()
config=(fixture/'etc/wpa_supplicant.conf').read_text()
assert 'psk='+raw_psk in config and 'country=US' in config
assert json.loads((bin_dir/'helper-calls.json').read_text())['calls']==calls_before
result('64-hex raw PSK and optional country supported without passphrase helper invocation')

assert 'modprobe brcmfmac' in SCRIPT.read_text()
assert 'rfkill unblock wifi' in SCRIPT.read_text()
assert '"$wifi_wait" -lt 10' in SCRIPT.read_text()
assert SCRIPT.read_text().index('\nprepare_wifi_hardware\n')>SCRIPT.read_text().index('\napply_network\n')
wifi_image_text=(PROJECT/'meta-rpi4-debug/recipes-core/images/rpi4-boot-rcu-wifi-image.bb').read_text()
assert 'wpa-supplicant wpa-supplicant-passphrase' in wifi_image_text
assert 'RDEPENDS:${PN} = "busybox openssh-keygen"' in recipe.read_text()
result('Production module load/rfkill/10-second wait and explicit WPA package dependencies present')

report={'fixture':str(root),'script_sha256':hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
 'tests':results,'passed':True,'hardware_boot_tested':False,
 'wpa_passphrase_host_test':'PBKDF2 mock; real target helper tested separately',
 'hexdump_host_mock':hexdump_mock,
 'no_host_passwords_or_private_keys_used':True}
report_path=Path('/tmp/rpi4-headless-setup-tests-v2.json')
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
