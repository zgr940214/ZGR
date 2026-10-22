# 从 Windows 配置 SSH 和有线网络

当前推荐镜像是 `rpi4-boot-rcu-ssh-image`，包含已实际编译的 OpenSSH、
有线 DHCP、libgpiod-tools 和启动分区导入程序。无需串口即可完成首次公钥登录。

## 烧录后设置登录

1. 解压下载 ZIP，使用 Raspberry Pi Imager 写入 `image/*.img.xz`。
   跳过 Raspberry Pi OS 的系统定制，完成写入与校验后重新插卡。
2. Windows 可见的 FAT 启动分区已有 `network-config`、`README-SETUP.txt`、
   `authorized_keys.example` 和 `userconf.txt.example`。
3. 没有自己的 SSH 密钥时，在 Windows PowerShell 执行 `ssh-keygen -t ed25519`。
   已有密钥则直接使用，避免覆盖。只复制 `.pub` 公钥，私钥留在电脑：

```powershell
# 将 E: 换成 SD 卡启动分区的实际盘符。
Copy-Item "$env:USERPROFILE\.ssh\id_ed25519.pub" 'E:\authorized_keys'
```

文件名必须是 `authorized_keys`，无 `.txt` 后缀。UTF-8 BOM 和 CRLF 可识别。
公钥示例文件本身不含可登录的密钥，需要复制你自己的真实公钥。

4. 默认使用有线 eth0 DHCP。插网线到路由器，安全弹出卡后开机。
   首次开机会生成独立 SSH host keys。路由器的 DHCP 客户端列表可查到 IPv4：

```powershell
ssh root@树莓派的IPv4
```

若私钥使用其他文件名，使用 `ssh -i 私钥文件 root@IPv4`。
没有共享默认口令；root 的空密码 SSH 登录被禁止。串口仍可用于本地恢复。

## 网络模板

启动分区的 `network-config` 是自定义 KEY=VALUE，值不加引号，不使用 cloud-init YAML。
默认内容可直接使用：

```conf
INTERFACE=eth0
MODE=dhcp
```

静态 IPv4 示例，地址、网关和 DNS 按自己的网络修改：

```conf
INTERFACE=eth0
MODE=static
ADDRESS=192.168.1.50
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
DNS=192.168.1.1 1.1.1.1
```

开机时先导入，再由 SysVinit 启动 networking 和 sshd。
导入结果在 FAT 的 `setup-result.txt`；错误不会覆盖已有有效配置或阻止开机。
只在 FAT 文件内容发生变化时重新导入，板上后续手改的配置不会被未变的模板覆盖。

## 密码、GPIO 与后续修改

推荐使用公钥登录。若需要密码，可在有 openssl 的机器执行 `openssl passwd -6`，
将生成的 SHA-512 crypt 哈希以 `root:哈希` 的单行内容存为 FAT 的 `userconf.txt`。
这不是明文密码文件。成功导入后该文件会被删除；模板在 `userconf.txt.example`。
也可先通过公钥 SSH 登录后执行 `passwd` 设置自己的密码。

GPIO 设备树/复用参数修改 FAT 的 `config.txt`，重启后生效。
系统已包含 libgpiod 2.1.3 的 gpiodetect、gpioinfo、gpioget、gpioset、gpiomon、gpionotify，
内核 GPIO_CDEV 与 BCM2835 pinctrl 内建。先用 `gpiodetect` / `gpioinfo` 查看真实芯片和线路。
2.x 的 gpioset 需要 `-c` 指定芯片，并在进程运行时保持线路请求；退出后电平不作保证。
当前镜像未加入 Wi-Fi/AP；也没有额外安装 SPI/I2C 等模块，不把普通 GPIO 工具等同于所有外设支持。

内核、完整调试符号和 boot/RCU 配置不变，之前下载的 vmlinux 可继续使用。

## 重新构建与验收

```bash
bash scripts/setup.sh
bash scripts/build-headless-ssh.sh
```

该入口实际运行新镜像构建和 `scripts/verify-headless-ssh-artifacts.py`，任一步失败都会返回非零。
输出 `rpi4-boot-rcu-ssh-image-raspberrypi4-64.rootfs.wic.xz`，改名 `.img.xz` 后可用 Imager。
原来的 `build-boot-rcu.sh` 仍用于无 SSH 的旧纯串口镜像。

本轮实际构建与产物验收已退出 0，3756 项任务成功；12 项导入测试通过。
实际硬件启动、SSH 网线连通、GPIO 电气行为和 KGDB/JTAG 未测试。
