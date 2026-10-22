# 从 Windows 填写 Wi-Fi 名称和密码后直接 SSH 登录

推荐目标为 `rpi4-boot-rcu-wifi-image`，构建入口是 `bash scripts/build-wifi-ssh.sh`。
本轮完整构建/验收入口已原生退出 0，4366 项任务全部成功。
以下是该目标的配置流程；原有线和纯串口目标继续保留为可选目标。

## 烧录后只改两行

1. 解压镜像 ZIP，使用 Raspberry Pi Imager 写入 `image/rpi4-wifi-ready-6.12.93-v8-v2.img.xz`。
   跳过 Raspberry Pi OS 专用定制，完成写入后重新插入 SD 卡。
2. Windows 可见的 FAT 分区中已有 `network-config` 和 `README-SETUP.txt`。
   打开 `network-config`，只把两行占位内容换成自己的 Wi-Fi 信息，不额外加引号：

   ```text
   SSID=你的WiFi名称
   PASSWORD=你的WiFi密码
   ```

   空格、中文和标点按原样填写。保存为 UTF-8；Windows CRLF 和 UTF-8 BOM 均支持。
   SSID 最多 32 个 UTF-8 字节，密码为 8～63 个字节或 64 位十六进制 PSK。
3. 安全弹出卡，插入 Pi 并上电，等待启动完成后，在同一局域网的 PowerShell 执行：

   ```powershell
   ssh root@rpi4-debug.local
   ```

   初始用户名为 `root`，SSH 密码为 **`Rpi4GPIO-2026!`**。
   这个流程只需要 Wi-Fi 信息；首次登录后可执行 `passwd` 修改开发用初始密码。

Wi-Fi `wlan0` 与有线 `eth0` 默认使用 DHCP。电脑无法解析 `.local` 时，
在路由器 DHCP 客户端列表查找 `rpi4-debug` 的 IPv4，使用 `ssh root@实际IP`。
插网线到 DHCP 路由器也可以使用相同账号密码连接。

当前 Wi-Fi 是连接现有 AP 的客户端，默认国家代码 CN。
面向 WPA2-PSK 和支持 WPA2 兼容模式的 WPA2/WPA3 混合网络，不承诺 WPA3-only AP；
镜像不提供 AP 热点。

## 模板格式和导入结果

已烧录 v1 时可使用[免重刷修复包](https://raw.githubusercontent.com/zgr940214/ZGR/rpi4-wifi-repair-v2/rpi4-wifi-repair-v2.zip)。
关机，将其中的 `config.txt` 和 `rpi4-wifi-fix.cpio.gz` 复制到启动分区根目录，
保留已填写的 `network-config`，再上电。使用自定义 config 时仅追加包内的 initramfs 指令。
修复包保留现有账户、密码和内核；新增 `repair-result.txt` 与 `network-status.txt`。

`network-config` 是自定义 **KEY=VALUE**，不是 cloud-init YAML。
普通连接只填写 `SSID`、`PASSWORD`，无需补齐其他字段。
开机时先导入，再启动 networking、SSH 和 mDNS；导入结果写入 FAT 的 `setup-result.txt`。
该文件不代表联网成功。`network-status.txt` 另外报告实际 Wi-Fi 关联状态、
IPv4 地址及 SSH 的 TCP/22 监听状态，最多观察启动后的 120 秒。
错误不会覆盖已有有效配置或阻止启动。

FAT 文件内容改变时会重新导入，未变模板保留后续板上修改。
v1 升级至 v2 时会额外导入一次，修复旧脚本因 BusyBox `od` 参数不兼容写入的空 SSID。
启动分区保留原始 Wi-Fi 配置以便在 Windows 继续修改；结果文件不包含 Wi-Fi 密码、PSK 或口令哈希。
根文件系统使用推导后的 WPA PSK，相关配置权限为 0600。

## GPIO 和调试符号

GPIO 设备树及引脚复用参数仍在 FAT 的 `config.txt` 中修改，重启后生效。
内核 GPIO_CDEV 与 BCM2835 pinctrl 已内建，系统包含 libgpiod 2.1.3 工具：

```sh
gpiodetect
gpioinfo
gpioget --help
gpioset --help
```

先查看真实 gpiochip/line 映射，GPIO line 编号不等于排针物理编号。
2.x 的 `gpioset` 使用 `-c` 指定芯片，并在进程运行时保持线路请求，退出后的电平不作保证。
实际电气行为和外设所需的 overlay 应在自己的板及接线条件下验证。

Wi-Fi 目标只安装无线所需的一小组完整 DWARF 模块、RPi4 固件和签名监管数据库，
不安装全部 1890 个模块。底层 Linux 6.12.93-v8 完整符号 ELF 没有变化；
已有 vmlinux、GDB 辅助文件和启动/RCU 精选源码继续兼容。
镜像升级包不重复下载这些符号，GDB 路径映射见[项目内核调试说明](../README.md#内核调试)。

## 从源码构建与验收

```bash
git clone --single-branch --no-tags --branch yocto-rpi4 https://github.com/zgr940214/ZGR.git rpi4-yocto
cd rpi4-yocto
bash scripts/setup.sh
bash scripts/build-wifi-ssh.sh
```

该入口实际运行新镜像构建及 `scripts/verify-wifi-ssh-artifacts.py`，任一步失败均返回非零。
输出 `rpi4-boot-rcu-wifi-image-raspberrypi4-64.rootfs.wic.xz`，改名 `.img.xz` 后可用于 Imager。
本轮标识在 `logs/wifi-ssh-current-run.txt`，构建和验收日志使用相同的 `<run>` 标识。
本轮运行标识 `20261022T090523Z`；4385 项构建任务成功。
交付包保留构建/产物日志、22 项导入检查、10 项实际 AArch64 导入/网络启动链回归和
15 项 AArch64 软件验证报告。网络端点在启动链回归中模拟；没有模拟射频连接。
真实 OpenSSH 使用镜像预置且未修改的账号库完成密码鉴权，错误密码被拒绝；WPA nl80211 和 PSK 推导验证通过。
5 个无线模块逐一验收完整 DWARF4、vermagic 和原内核构建哈希，模块依赖/SDIO alias 完整。
监管数据库签名已由实际 cfg80211 模块内置公钥对应证书验证通过。

本环境没有 RPi4 硬件，未进行实机启动、无线关联、SSH/mDNS 实际联网、GPIO 电气行为或 KGDB/JTAG 测试。

## 可选的旧目标和高级入口

旧有线目标 `rpi4-boot-rcu-ssh-image` 使用 `bash scripts/build-headless-ssh.sh` 构建，
默认 eth0 DHCP、没有 Wi-Fi、零 `.ko`。该旧目标需要自己的 SSH 公钥或自行设置密码，
不使用 Wi-Fi 目标的预置口令。Windows 复制公钥的示例：

```powershell
# 将 E: 换成启动分区盘符，只复制自己的 .pub 公钥。
Copy-Item "$env:USERPROFILE\.ssh\id_ed25519.pub" 'E:\authorized_keys'
```

旧有线目标可选静态网络仍使用 KEY=VALUE，例如：

```text
INTERFACE=eth0
MODE=static
ADDRESS=192.168.1.50
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
DNS=192.168.1.1 1.1.1.1
```

高级公钥导入 `authorized_keys`、哈希密码导入 `userconf.txt` 继续保留，
但不是推荐 Wi-Fi 连接流程的准备步骤。
纯串口目标 `rpi4-boot-rcu-image` 使用 `build-boot-rcu.sh`，原全模块目标 `rpi4-debug-image`
使用 `build.sh`；区别、资源要求与固定源码版本见[项目 README](../README.md)。
