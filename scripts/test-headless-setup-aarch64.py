#!/usr/bin/env python3
"""Run the image's real AArch64 importer and networking hooks in a temp chroot.

Uses static QEMU user mode and native exec dispatchers, without registering
host binfmt handlers. Docker supplies chroot only; no ports or network access.
Only the ip/udhcpc/WPA network endpoints are mocked for the ifup chain check.
This is not a Pi boot, radio association, or DHCP exchange test.
"""
from pathlib import Path, PurePosixPath
import argparse, bz2, hashlib, json, os, posixpath, shlex, shutil, subprocess, tarfile, tempfile

PROJECT=Path(__file__).resolve().parent.parent
SOURCE_IMPORTER=PROJECT/'meta-rpi4-debug/recipes-core/rpi4-headless-setup/files/rpi4-headless-setup'

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def extract(source, dest):
 links=[]; hard=[]
 def safe(name):
  p=PurePosixPath(name)
  assert not p.is_absolute() and '..' not in p.parts,name
  return p
 # Yocto's parallel compressor emits concatenated bzip2 streams.
 with bz2.open(source,'rb') as decoded,tarfile.open(fileobj=decoded,mode='r|') as archive:
  for m in archive:
   name=m.name.removeprefix('./').rstrip('/')
   if name in ('','.'):continue
   p=dest.joinpath(*safe(name).parts)
   if m.isdir():p.mkdir(parents=True,exist_ok=True)
   elif m.issym():links.append((p,m.linkname))
   elif m.islnk():hard.append((p,m.linkname.removeprefix('./')))
   elif m.isfile():
    p.parent.mkdir(parents=True,exist_ok=True)
    with archive.extractfile(m) as src,p.open('xb') as out:shutil.copyfileobj(src,out)
    p.chmod(m.mode&0o777)
 for p,name in hard:
  target=dest.joinpath(*safe(name).parts);p.parent.mkdir(parents=True,exist_ok=True);os.link(target,p)
 for p,name in links:
  if name.startswith('/'):
   target=dest.joinpath(*safe(posixpath.normpath(name).lstrip('/')).parts)
   name=os.path.relpath(target,p.parent)
  else:safe(posixpath.normpath(posixpath.join(p.parent.relative_to(dest).as_posix(),name)))
  p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(name)

DISPATCH=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc,char **argv){
 const char *name=strrchr(argv[0],'/');name=name?name+1:argv[0];
 if(access("/mock-network",F_OK)==0 && (!strcmp(name,"udhcpc")||!strcmp(name,"ip")||!strcmp(name,"ifconfig")||!strcmp(name,"route")||!strcmp(name,"wpa_supplicant"))){
   FILE *out=fopen("/network-calls.log","a");fprintf(out,"%s",name);
   for(int n=1;n<argc;n++)fprintf(out," [%s]",argv[n]);
   const char *vars[]={"IFACE","MODE","PHASE","IF_WPA_DRIVER","IF_WPA_CONF",NULL};
   for(int n=0;vars[n];n++)fprintf(out," %s=%s",vars[n],getenv(vars[n])?getenv(vars[n]):"(unset)");
   fputc('\n',out);fclose(out);return 0;
 }
 char **args=calloc(argc+5,sizeof(char*));args[0]="/qemu-aarch64";int offset;
 if(!strcmp(name,"wpa_passphrase")){args[1]="/usr/sbin/wpa_passphrase.aarch64";offset=2;}
 else if(!strcmp(name,"wpa_supplicant")){args[1]="/usr/sbin/wpa_supplicant.aarch64";offset=2;}
 else{args[1]="/bin/busybox.aarch64";args[2]=(char*)name;offset=3;if(!strcmp(name,"busybox"))offset=2;}
 for(int n=1;n<argc;n++)args[offset+n-1]=argv[n];execv(args[0],args);perror("exec qemu");return 127;
}
'''

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('rootfs',type=Path)
 ap.add_argument('--qemu',type=Path,required=True)
 ap.add_argument('--importer-override',type=Path,help='Prebuild check only; final verification must omit this')
 ap.add_argument('--legacy-importer',type=Path,help='Optional original importer, reproduces empty-SSID bug')
 ap.add_argument('--report',type=Path,default=PROJECT/'verification/wifi-aarch64-importer-regression.json')
 args=ap.parse_args()
 source=args.rootfs.resolve(strict=True);qemu=args.qemu.resolve(strict=True)
 work=Path(tempfile.mkdtemp(prefix='rpi4-arm-importer-regression-',dir='/tmp'));root=work/'root';root.mkdir()
 extract(source,root)
 original_importer_sha=sha(root/'usr/sbin/rpi4-headless-setup')
 if args.importer_override:shutil.copyfile(args.importer_override,root/'usr/sbin/rpi4-headless-setup')
 actual_importer_sha=sha(root/'usr/sbin/rpi4-headless-setup')
 assert actual_importer_sha==sha(SOURCE_IMPORTER),'Image importer does not match project source'
 if args.legacy_importer:shutil.copyfile(args.legacy_importer,root/'legacy-importer')
 (work/'dispatch.c').write_text(DISPATCH)
 subprocess.run(['gcc','-static','-O2','-o',str(work/'dispatch'),str(work/'dispatch.c')],check=True,capture_output=True)
 busybox=(root/'bin/busybox').resolve(strict=True)
 busybox.rename(root/'bin/busybox.aarch64');shutil.copyfile(work/'dispatch',busybox)
 for name in ['wpa_passphrase','wpa_supplicant']:
  p=root/'usr/sbin'/name;p.rename(p.with_name(name+'.aarch64'));shutil.copyfile(work/'dispatch',p)
 shutil.copyfile(qemu,root/'qemu-aarch64')
 for name in ['dev','proc/sys/vm','run/wpa_supplicant','cases','helpers']: (root/name).mkdir(parents=True,exist_ok=True)
 (root/'dev/null').touch()
 (root/'dev/random').write_bytes(os.urandom(4096));(root/'dev/urandom').write_bytes(os.urandom(4096))
 (root/'proc/mounts').write_text('/dev/mmcblk0p2 / ext4 rw 0 0\n/dev/mmcblk0p1 /boot vfat rw 0 0\n')
 (root/'proc/sys/vm/min_free_kbytes').write_text('8192\n')
 cases=[('ascii','fixture-lab1234','fixturepass',False),('utf8',' 书房 Wi"Fi\\=#$; ','fixture pass! @2026',True),('repeated32','a'*32,'fixturepassword',False)]
 lines=['#!/bin/sh','set -eu','export PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin']
 checks=[]
 def ok(name):
  checks.append(name);lines.append('echo PASS:'+name)
 for name,ssid,password,windows in cases:
  case=root/'cases'/name
  for path in ['etc/network','boot','var/lib','run']: (case/path).mkdir(parents=True,exist_ok=True)
  (case/'.rpi4-setup-test-root').touch()
  text='SSID='+ssid+'\nPASSWORD='+password+'\n'
  (case/'boot/network-config').write_bytes((b'\xef\xbb\xbf'+text.replace('\n','\r\n').encode()) if windows else text.encode())
  expected_psk=hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex()
  prefix='/cases/'+name
  lines.extend([f'/usr/sbin/rpi4-headless-setup --root {prefix} --boot {prefix}/boot',f"grep -qx '    ssid={ssid.encode().hex()}' {prefix}/etc/wpa_supplicant.conf",f"grep -qx '    psk={expected_psk}' {prefix}/etc/wpa_supplicant.conf",f"test \"$(stat -c %a {prefix}/etc/wpa_supplicant.conf)\" = 600",f"grep -q '^Result: configuration applied;' {prefix}/boot/setup-result.txt"])
  ok('actual_aarch64_importer_'+name+'_ssid_psk_and_permissions')
 # Simulate exactly the prior successful remembered-input state, then update
 # only the importer. Original importer reproduction is optional but explicit.
 case=root/'cases/legacy'
 for path in ['etc/network','boot','var/lib/rpi4-setup','run']: (case/path).mkdir(parents=True,exist_ok=True)
 (case/'.rpi4-setup-test-root').touch()
 text='SSID=fixture-lab1234\nPASSWORD=fixturepass\n';(case/'boot/network-config').write_text(text)
 (case/'var/lib/rpi4-setup/network.sha256').write_text(hashlib.sha256(text.encode()).hexdigest()+'\n')
 (case/'etc/wpa_supplicant.conf').write_text('ctrl_interface=/var/run/wpa_supplicant\nnetwork={\n    ssid=\n    psk='+hashlib.pbkdf2_hmac('sha1',b'fixturepass',b'fixture-lab1234',4096,32).hex()+'\n}\n')
 if args.legacy_importer:
  lines.extend(['rm /cases/legacy/var/lib/rpi4-setup/network.sha256','/bin/sh /legacy-importer --root /cases/legacy --boot /cases/legacy/boot > /legacy-import.log 2>&1',"grep -q \"od: invalid option\" /legacy-import.log","grep -qx '    ssid=' /cases/legacy/etc/wpa_supplicant.conf","grep -q '^Result: success' /cases/legacy/boot/setup-result.txt"])
  ok('original_aarch64_importer_reproduces_empty_ssid_despite_success')
 lines.extend(['/qemu-aarch64 /usr/sbin/wpa_supplicant.aarch64 -D nl80211 -i wlan0 -c /cases/legacy/etc/wpa_supplicant.conf -d > /legacy-wpa.log 2>&1 || :',"grep -q \"id=0 ssid=''\" /legacy-wpa.log",'/usr/sbin/rpi4-headless-setup --root /cases/legacy --boot /cases/legacy/boot',"grep -qx '    ssid=666978747572652d6c616231323334' /cases/legacy/etc/wpa_supplicant.conf","test \"$(cat /cases/legacy/var/lib/rpi4-setup/network-format)\" = 2",'/usr/sbin/rpi4-headless-setup --root /cases/legacy --boot /cases/legacy/boot',"grep -q 'Network: unchanged; local edits preserved' /cases/legacy/boot/setup-result.txt"])
 ok('actual_aarch64_migration_repairs_unchanged_input_once')
 lines.extend(['/qemu-aarch64 /usr/sbin/wpa_supplicant.aarch64 -D nl80211 -i wlan0 -c /cases/legacy/etc/wpa_supplicant.conf -d > /fixed-wpa.log 2>&1 || :',"grep -q \"id=0 ssid='fixture-lab1234'\" /fixed-wpa.log","! grep -q 'Failed to read or parse' /fixed-wpa.log"])
 ok('actual_aarch64_wpa_parser_reads_fixed_ssid')
 # Fail converter on fresh input; require previous config and hash to survive.
 lines.extend(['cp /cases/legacy/etc/wpa_supplicant.conf /before-wpa','cp /cases/legacy/var/lib/rpi4-setup/network.sha256 /before-hash',"printf '%s\\n' 'SSID=converter-failure' 'PASSWORD=fixturepass' > /cases/legacy/boot/network-config"])
 for name,body in [('failed','exit 1'),('truncated',"printf '00'"),('invalidhex',"printf 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz'")]:
  lines.extend(["printf '%s\\n' '#!/bin/sh' "+shlex.quote(body)+" > /helpers/hexdump",'chmod 755 /helpers/hexdump','if PATH=/helpers:$PATH /usr/sbin/rpi4-headless-setup --root /cases/legacy --boot /cases/legacy/boot; then exit 1; fi','cmp /before-wpa /cases/legacy/etc/wpa_supplicant.conf','cmp /before-hash /cases/legacy/var/lib/rpi4-setup/network.sha256'])
  ok('actual_aarch64_'+name+'_encoding_preserves_previous_settings')
 lines.extend(['cp /cases/ascii/etc/network/interfaces /etc/network/interfaces','cp /cases/ascii/etc/wpa_supplicant.conf /etc/wpa_supplicant.conf','touch /mock-network','rm -f /run/ifstate','/etc/init.d/networking start > /networking-start.log 2>&1',"grep -q 'wpa_supplicant .*\\[-i\\] \\[wlan0\\].*\\[-c\\] \\[/etc/wpa_supplicant.conf\\].*\\[-D\\] \\[nl80211\\].*IFACE=wlan0 MODE=start PHASE=pre-up IF_WPA_DRIVER=nl80211 IF_WPA_CONF=/etc/wpa_supplicant.conf' /network-calls.log","grep -q 'udhcpc .*\\[-i\\] \\[wlan0\\]' /network-calls.log"])
 ok('actual_aarch64_networking_init_ifup_runparts_wpa_hook_and_dhcp_dispatch')
 (root/'run-regression.sh').write_text('\n'.join(lines)+'\n')
 # Docker's root is mapped separately in this environment. Only this disposable
 # fixture is made writable; production files and credentials remain untouched.
 work.chmod(0o777)
 for p in root.rglob('*'):
  if not p.is_symlink():p.chmod(0o777 if p.is_dir() or p.stat().st_mode&0o111 or p.name in ['busybox.nosuid','wpa_supplicant','wpa_passphrase','qemu-aarch64'] else 0o666)
 root.chmod(0o777)
 before=sha(source)
 command=['docker','run','--rm','--network','none','--cap-drop','ALL','--cap-add','SYS_CHROOT','--mount','type=bind,src='+str(work)+',dst=/audit','ubuntu:24.04','chroot','/audit/root','/bin/sh','/run-regression.sh']
 result=subprocess.run(command,text=True,capture_output=True,timeout=180)
 assert sha(source)==before,'Production rootfs changed'
 log=work/'regression.log';log.write_text(result.stdout+result.stderr)
 passed=[line.removeprefix('PASS:') for line in result.stdout.splitlines() if line.startswith('PASS:')]
 report={'passed':result.returncode==0 and passed==checks,'source_rootfs':str(source),'source_rootfs_sha256':before,'image_importer_sha256':original_importer_sha,'importer_sha256':actual_importer_sha,'importer_overridden_for_prebuild_test':bool(args.importer_override),'execution':'Actual image AArch64 BusyBox and WPA executables under QEMU user mode, isolated Docker chroot, no network','hardware_boot_tested':False,'wifi_radio_association_tested':False,'dhcp_exchange_tested':False,'network_endpoints_mocked':['ip','ifconfig','route','udhcpc','wpa_supplicant only during init-chain check'],'sysctl_proc_file_is_fixture':True,'checks':passed,'expected_checks':checks,'production_archive_unchanged':True,'fixture':str(work),'log':str(log)}
 args.report.parent.mkdir(exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 if not report['passed']:print(result.stdout+result.stderr);raise SystemExit(result.returncode or 1)

if __name__=='__main__':main()
