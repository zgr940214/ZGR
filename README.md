# Raspberry Pi 4：SSH / GPIO / 启动与 RCU 调试

RPi4 / BCM2711 的 64 位 Yocto 镜像，固定 Yocto Scarthgap LTS **5.0.21**、
Raspberry Pi Linux **6.12.93-v8**。上游源码、BSP 和内核 metadata 均固定到完整
Git SHA，见 [sources.lock.json](sources.lock.json)，不使用 AUTOREV。

## 推荐：只填 Wi-Fi 名称和密码的 SSH / GPIO 镜像

推荐目标为 `rpi4-boot-rcu-wifi-image`：预配 Wi-Fi、OpenSSH、GPIO 工具和
`rpi4-debug.local` 主机名，Wi-Fi `wlan0` 与有线 `eth0` 默认使用 DHCP。
只安装 Wi-Fi 所需的少量完整 DWARF 模块、RPi4 固件和签名监管数据库；
同一完整符号内核保持不变，已有 vmlinux 和启动 / RCU 源码可以继续使用。

[镜像 + 完整内核符号 + 启动/RCU 源码 ZIP](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-wifi-ready-6.12.93-v8-full-v2.zip)

[Wi-Fi 镜像升级 ZIP](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-wifi-ready-6.12.93-v8-image-v2.zip)
升级包只下载新镜像与使用说明，不重复携带完整符号。

v2 修复了 v1 的联网缺陷：精简 BusyBox 不支持导入脚本的 `od -An -tx1` 参数，
导致 SSID 转换为空值，配置导入却报告成功。现使用镜像支持的 `hexdump` 并检查
退出码、长度和十六进制字符；升级后会重新导入一次旧版缓存配置。
回归验证使用镜像实际 AArch64 程序，结果见 `verification/wifi-aarch64-importer-regression.json`。

已经烧录 v1 的 SD 卡可使用[免重刷修复包（约 1.5 MiB）](https://raw.githubusercontent.com/zgr940214/ZGR/rpi4-wifi-repair-v2/rpi4-wifi-repair-v2.zip)：
关机后，将 ZIP 中的 `config.txt` 和 `rpi4-wifi-fix.cpio.gz` 复制到启动分区根目录，
覆盖 `config.txt`，保留现有 `network-config`，再上电。包内 config 基于本项目发布的默认
配置；若自行修改过 GPIO/显示配置，请仅在自己的 config 末尾追加
`initramfs rpi4-wifi-fix.cpio.gz followkernel`。
修复结果写入 `repair-result.txt`，实际连接状态见 `network-status.txt`。
修复包已验证实际 AArch64 脚本，内核到 initramfs 的实机启动衔接尚未验证。

1. 解压 ZIP，在 Raspberry Pi Imager 的“使用自定义镜像”中选择
   `image/rpi4-wifi-ready-6.12.93-v8-v2.img.xz`，烧录一次，跳过 Raspberry Pi OS 专用定制。
2. 重插 SD 卡，在 Windows 可见的 FAT 启动分区打开 `network-config`。
   **只改两行**，等号后直接填写自己的名称和密码，不额外加引号：

   ```text
   SSID=你的WiFi名称
   PASSWORD=你的WiFi密码
   ```

   空格、中文和标点按原样填写，保存为 UTF-8；支持 CRLF 和 UTF-8 BOM。
3. 安全弹出卡，插入 Pi 并上电，等待启动完成后连接：

   ```powershell
   ssh root@rpi4-debug.local
   ```

   初始 SSH 密码为 **`Rpi4GPIO-2026!`**。首次登录后可用 `passwd` 修改。

如果 `.local` 无法解析，在路由器 DHCP 列表查找 `rpi4-debug` 的 IPv4，
使用 `ssh root@实际IP`；插网线到 DHCP 路由器也可作为备用连接。
Wi-Fi 是连接现有 AP 的客户端，默认国家代码 CN；支持 WPA2-PSK 和提供 WPA2 兼容模式的
WPA2/WPA3 混合网络，不承诺 WPA3-only AP。配置导入结果写入 FAT 的 `setup-result.txt`；
实际连接状态、IPv4 和 SSH 监听状态写入 `network-status.txt`，启动后最多观察 120 秒。
详细说明见[启动分区配置说明](docs/ssh-template.zh-CN.md)。

GPIO 设备树参数仍在 FAT 的 `config.txt`；登录后先查看实际芯片与线路：

```sh
gpiodetect
gpioinfo
gpioset --help
```

libgpiod 版本为 2.1.3，GPIO_CDEV 内建。GPIO line 编号不等于排针物理编号，
实际映射和电气行为需在板上确认。

从源码构建推荐的 Wi-Fi 镜像：

```bash
git clone --single-branch --no-tags --branch yocto-rpi4 https://github.com/zgr940214/ZGR.git rpi4-yocto
cd rpi4-yocto
bash scripts/setup.sh
bash scripts/build-wifi-ssh.sh
```

`build-wifi-ssh.sh` 完成内核安装检查后，实际构建新目标并运行
`scripts/verify-wifi-ssh-artifacts.py`；只有所有步骤通过才返回 0。
输出位于 `build/tmp/deploy/images/raspberrypi4-64/`：

```text
rpi4-boot-rcu-wifi-image-raspberrypi4-64.rootfs.wic.xz
rpi4-boot-rcu-wifi-image-raspberrypi4-64.rootfs.wic.bmap
rpi4-boot-rcu-wifi-image-raspberrypi4-64.rootfs.tar.bz2
```

烧录自己构建的产物时，将 `.wic.xz` 复制或改名为 `.img.xz` 后选择即可，内容不变。
本轮标识在 `logs/wifi-ssh-current-run.txt`，对应日志为
`logs/wifi-ssh-build-<run>.log` 和 `logs/wifi-ssh-artifacts-<run>.log`。
完整构建/验收入口本轮原生退出码为 0，4385 项任务全部成功；当前运行标识 `20261022T090523Z`。
发布包保留对应日志、22 项配置导入检查、10 项实际 AArch64 导入/网络启动链回归，
以及 15 项 AArch64 软件检查报告。网络启动链测试模拟无线和 DHCP 端点。
真实 OpenSSH 使用镜像预置密码完成 SSH 鉴权，错误密码被拒绝；账号库未修改。
实际安装 5 个无线模块，逐一验证完整 DWARF4、vermagic、依赖和原内核构建哈希。
签名监管数据库还通过实际 cfg80211 模块内置证书的密码学验证。
此前目标的通过记录单列于后文，本轮状态以 Wi-Fi 日志为准。
本环境没有 RPi4 硬件；尚未验证实机启动、Wi-Fi 关联、mDNS/NIC 连通和 GPIO 电气行为。

## 可选：原有线 SSH / GPIO 镜像

[有线镜像升级包](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-headless-ssh-gpio-6.12.93-v8-image-v1.zip)
或[有线镜像 + 完整内核符号](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-headless-ssh-gpio-6.12.93-v8-full-v1.zip)。
原 `rpi4-boot-rcu-ssh-image` 继续保留，运行 `bash scripts/build-headless-ssh.sh` 构建。
此目标为有线 eth0 DHCP、零 `.ko`，首次登录使用自己的 SSH 公钥或自行配置的密码；
它不使用新 Wi-Fi 目标的预置口令。此前已实际构建并验收，3756 项任务成功、12 项导入检查通过：
[构建](verification/headless-ssh-build-20261022T033449Z.log)、
[产物验收](verification/headless-ssh-artifacts-20261022T033449Z.log)、
[导入测试](verification/headless-setup-tests.json)。

## 历史纯串口镜像（没有 SSH）

[镜像 + 完整内核符号 ZIP（约 118 MiB）](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-boot-rcu-6.12.93-v8-minimal-v1.zip)

此包使用独立产物标签分发，解压后可校验 SHA256SUMS。源码克隆请使用下方
`--single-branch --no-tags`，避免同时下载产物标签里的二进制文件。

## 可选：构建原纯串口精简镜像

```bash
git clone --single-branch --no-tags --branch yocto-rpi4 https://github.com/zgr940214/ZGR.git rpi4-yocto
cd rpi4-yocto
bash scripts/setup.sh
bash scripts/build-boot-rcu.sh
```

当前云环境已有项目时直接进入 `/workspace/rpi4-yocto` 执行构建脚本。
`setup.sh` 获取固定版本源码、准备 build/conf 与固定基础镜像 digest 的
Ubuntu 24.04 容器。主机需要 Docker、Git、Python 3.11 以上；Python 用于
BitBake 和产物校验。容器按调用者 UID/GID 运行，无 privileged，不安装宿主软件包。

精简目标为 `rpi4-boot-rcu-image`：

- 保留启动固件、内核、RPi4 DTB、ext4 根文件系统、init 和 shell。
- 不安装任何 `.ko`、Wi-Fi 固件、OpenSSH 或 gdbserver。
- SD/MMC、ext4、串口、BCMGENET 以太网驱动已在实际内核配置中确认内建。
  需要模块的 USB / Wi-Fi 等设备不属于此镜像的使用范围。
- 串口本地 `root` 可用空密码登录；没有 SSH 服务。跳过 Imager 的 Raspberry Pi OS
  系统定制。账号策略仅属于这个专用学习镜像。
- 使用相同的完整 DWARF4 内核，不删减内核符号，不改变内核配置和版本。

`build-boot-rcu.sh` 先完成内核编译和安装，低空间时回收已链接的对象输入，
再运行 `bitbake rpi4-boot-rcu-image` 和专用产物验收。所有步骤成功才返回 0。
日志保存在 `logs/boot-rcu-*.log`，本轮标识在 `logs/boot-rcu-current-run.txt`。
精简镜像临时工作区默认使用磁盘，不需要原完整镜像的 12 GiB 内存盘。

输出在 `build/tmp/deploy/images/raspberrypi4-64/`：

```text
rpi4-boot-rcu-image-raspberrypi4-64.rootfs.wic.xz
rpi4-boot-rcu-image-raspberrypi4-64.rootfs.wic.bmap
rpi4-boot-rcu-image-raspberrypi4-64.rootfs.tar.bz2
rpi4-kernel-debug/                 # 同一次完整符号内核构建的调试产物
```

烧录时把 `.wic.xz` 复制或改名为 `.img.xz`，在 Raspberry Pi Imager 的
“使用自定义镜像”中选择该文件，无需解压 XZ。发布 ZIP 则先解压 ZIP，再选其中
`image/*.img.xz`。改后缀不改变磁盘镜像内容。

## 内核调试

内核保留完整 DWARF4，禁用 reduced、split 和 debug 信息压缩，禁用内核包 strip。
启用 KALLSYMS_ALL、GDB_SCRIPTS、IKCONFIG、IKCONFIG_PROC。
`Image` 用于启动，未 strip 的 `vmlinux` 用于主机 GDB。下载包内的
`vmlinux.xz` 是对完整 ELF 的无损压缩，先用 `xz -dk vmlinux.xz` 还原。

启动和 RCU 都编入内核，观察它们不需要全量模块符号。实际配置为 4 核 SMP、
`CONFIG_PREEMPT=y`、Tree RCU、Preempt RCU；KGDB/KDB、RCU_TRACE、ftrace、
函数与函数图追踪均启用。启动可从 `primary_entry`、`start_kernel`、`setup_arch`、
`paging_init`、`rcu_init`、`rest_init` 看起；RCU 可关注 `rcu_gp_kthread`、
`rcu_gp_init`、`rcu_gp_cleanup`、`rcu_core`、`call_rcu`、`synchronize_rcu`。
这些符号已在实际 ELF 中检查存在。

配套完整符号包中的源码仅包含启动 / RCU 精选代码和生成头文件，并非完整内核源码树；
推荐的 Wi-Fi 镜像升级包不重复携带符号或源码归档。
缺少其他子系统源码时可从固定提交补齐。GDB 源码路径映射：

```gdb
file /绝对路径/kernel-debug/vmlinux
set substitute-path /usr/src/kernel /绝对路径/kernel-source
set substitute-path /usr/src/debug/linux-raspberrypi/6.12.93+git /绝对路径/kernel-build
source /绝对路径/kernel-debug/vmlinux-gdb.py
```

把 `gdb-scripts.tar.gz` 解压到 `vmlinux` 旁；源码和生成源码分别解压到上面的
kernel-source、kernel-build 目录。完整源码也保留在构建环境的
`build/tmp/work-shared/raspberrypi4-64/kernel-source`。

KASLR 默认启用；调试时可在启动分区 `cmdline.txt` 同一行末尾加 `nokaslr`。
目前没有配置 `kgdboc` / `kgdbwait`，实际 UART 与接线需在板上核对。
普通串口 KGDB 注册较晚，不能保证从 `head.S` 第一条指令单步；最早启动需要
JTAG 或适当的 QEMU 调试环境。没有进行实机启动或 KGDB / JTAG 连通测试。

## 各目标的产物验收

推荐 Wi-Fi 目标的构建入口会自动执行专用验收；也可单独检查已生成的产物：

```bash
python3 scripts/verify-wifi-ssh-artifacts.py
```

检查包括实际 Wi-Fi 依赖模块的 AArch64 ELF、完整 DWARF4、vermagic 及其与原内核构建的
逐字节一致性，RPi4 固件/NVRAM/签名 regdb、预置账户与 mDNS、FAT 上的 Wi-Fi 模板，
以及启动 kernel/DTB 哈希、ext4 和 WIC 分区范围。本轮检查结果以本轮日志为准。

原纯串口精简目标使用以下验收入口：

```bash
python3 scripts/verify-boot-rcu-artifacts.py
bash scripts/bitbake.sh -p
```

精简验收检查固定 SHA、AArch64 ELF、完整 DWARF4、17 个启动 / RCU 符号、
内建启动驱动；完整读取 rootfs 压缩归档，确认零 `.ko`、init/shell 可执行及登录策略；
完整解压 WIC，检查 FAT 固件、启动参数、内核和 DTB 与部署文件的 SHA-256，
以及 ext4 和分区范围。已完成的实际构建与验收记录放在 `verification/`。
这些检查不等同于 RPi4 实机启动测试。

## 可选的全模块镜像

需要研究全部内核模块或其他设备时，可另外运行：

```bash
bash scripts/build.sh
python3 scripts/verify-artifacts.py
```

原目标 `rpi4-debug-image` 包含全部 1890 个完整符号模块、OpenSSH 和 gdbserver，
登录凭据需要自行配置；其 `.wic.bz2`、`.tar.bz2` 和完整模块符号归档较大。
此目标仍保留，未纳入启动 / RCU 精简下载包。
原完整镜像已于 2026-10-21 实际编译，3755 项任务成功；全部模块 ELF、
rootfs / 调试归档模块逐字节一致性和 WIC 检查通过。原记录为
[构建日志](verification/build-20261021T111820Z.log) 和
[验收日志](verification/artifacts-20261021T111820Z.log)。

## 资源与网络

首次构建仍需编译完整调试内核，磁盘建议至少 **100 GB 可用空间**。
此前全模块、纯串口及有线目标已在 32 GB 磁盘、32 GiB RAM 的本环境完成构建；
配置同时调度 2 个配方任务，
每个使用 `-j4`，非内核配方启用 rm_work，低空间时由脚本回收内核 `.o` 和 `.o.cmd`。
保留 vmlinux、所有已链接 `.ko`、源码、生成头文件和 GDB 工具。
Docker vfs 驱动在每个容器运行时还使用约 1.1 GiB 磁盘，退出时释放。
原全模块镜像默认用 12 GiB 容器内存盘，建议至少 24 GiB RAM；
磁盘充足时可用 `RPI4_IMAGE_TMPFS_GB=0 bash scripts/build.sh`。
精简入口默认使用磁盘。

内核源码由 `setup.sh` 从官方仓库获取固定提交，生成并校验标准 BitBake 浅缓存，
避免获取全部内核历史；缓存约 258 MiB，在 `kernel-source-cache/`。
其他配方启用官方源码镜像与 sstate 镜像。主要网络域包括
`downloads.yoctoproject.org`、`sstate.yoctoproject.org`、`git.yoctoproject.org`、
`github.com`、`api.github.com`；发布 Release 还使用 `uploads.github.com`。
保留 TLS、签名、checksum 和 sanity 检查。

## 精简目标的实际验证记录

2026-10-22 已在本云执行环境实际构建新的精简 rootfs 与 WIC，
并完整运行 `bash scripts/build-boot-rcu.sh`，退出码 **0**。
镜像压缩后 **17,664,060 字节**，685 个 rootfs 条目，零 `.ko`。
完整内核 ELF、17 个启动/RCU 符号、内建驱动、启动 FAT、kernel/DTB 哈希、
init/shell、ext4 与分区范围均通过验收。

- [精简构建日志](verification/boot-rcu-build-20261022T023120Z.log)
- [精简验收日志](verification/boot-rcu-artifacts-20261022T023120Z.log)

编译复用了此前已实际交叉编译并验收的固定版本内核。
未进行 RPi4 实机启动或调试器连接测试。

## 早期有线镜像的 AArch64 用户态执行记录

原有线 SSH 镜像里的实际 AArch64 ssh-keygen、sshd 配置检查、BusyBox、passwd 和
GPIO 2.1.3 工具已在 QEMU 10.0.13 用户模式下运行，9 项检查通过。
[执行报告](verification/aarch64-smoke.json)、[执行日志](verification/aarch64-smoke.log)、
[模拟器来源验证](verification/aarch64-emulator-provenance.json)。
这不是 RPi4 实机启动或实际 SSH 联网测试，也不是本轮 Wi-Fi 目标的软件验证结果。
