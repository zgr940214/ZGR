# Raspberry Pi 4：启动与 RCU 调试

RPi4 / BCM2711 的 64 位 Yocto 镜像，固定 Yocto Scarthgap LTS **5.0.21**、
Raspberry Pi Linux **6.12.93-v8**。上游源码、BSP 和内核 metadata 均固定到完整
Git SHA，见 [sources.lock.json](sources.lock.json)，不使用 AUTOREV。

## 下载已构建产物

[镜像 + 完整内核符号 ZIP（约 118 MiB）](https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-boot-rcu-6.12.93-v8-minimal-v1.zip)

此包使用独立产物标签分发，解压后可校验 SHA256SUMS。源码克隆请使用下方
`--single-branch --no-tags`，避免同时下载产物标签里的二进制文件。

## 构建启动 / RCU 精简镜像

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

精简下载包只包含启动 / RCU 相关源码和生成头文件，并非完整内核源码树；
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

## 产物验收

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

需要研究模块、Wi-Fi 或其他设备时，可另外运行：

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
本环境用 32 GB 磁盘、32 GiB RAM 实际完成了构建；配置同时调度 2 个配方任务，
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
