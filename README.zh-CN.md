# RPi4 启动与 RCU 精简调试包

本包使用独立目标 `rpi4-boot-rcu-image` 构建小型 rootfs 和 WIC 磁盘镜像。
基础 init、shell 和串口本地登录保留；没有 `.ko` 文件、SSH 服务、gdbserver 或 Wi-Fi 配置/固件。
底层仍为原来实际构建并验收的 Linux **6.12.93-v8**、AArch64 完整 DWARF4 内核，
内核符号无删减；rootfs 和磁盘镜像由新目标实际重新构建。
尚未进行 Raspberry Pi 4 实机启动或 KGDB/JTAG 连通性测试。

## 烧录和登录

先解压 ZIP，在 Raspberry Pi Imager 中选择“使用自定义镜像”，
打开 `image/rpi4-boot-rcu-image-6.12.93-v8.img.xz`；Imager 可直接读取 XZ，无需先解压它。
跳过 Raspberry Pi OS 专用的系统定制。
本镜像提供串口本地 `root` 登录，密码为空，提示输入密码时直接回车；没有远程登录服务。
UART 接线、设备名、控制台和 KGDB 复用方式仍需在实际板上确认。

## 文件和校验

- `image/`：新目标磁盘镜像、对应 SHA-256 和 WIC bmap。
- `kernel-debug/`：无损压缩的完整 `vmlinux.xz`、System.map、实际内核配置、GDB 辅助脚本和构建元数据。
- `sources/`：启动/RCU 精选源码、匹配的生成源码及逐文件覆盖/哈希报告。
- `project/`：可复用的 Yocto 配置和构建脚本归档。
- `verification/`：新目标本轮真实 BitBake 构建日志、产物验收日志和 vmlinux 压缩校验报告。

解压 ZIP 后进入最外层目录执行：

```bash
sha256sum -c SHA256SUMS
```

ZIP 中没有独立 `.ko` 归档、完整内核源码树或旧的大镜像。
`verification/boot-rcu-build-*.log` 和 `boot-rcu-artifacts-*.log`
对应这次新 rootfs/WIC 的构建与检查；硬件启动不属于这些检查。
`vmlinux-compression.json` 记录原文件和压缩文件的 SHA-256，解压结果与完整符号原文件逐字节相同。

## 在 GDB 中加载完整符号

`vmlinux.xz` 是完整内核 ELF 的无损压缩文件；GDB 前先解压，保留压缩包：

```bash
xz -dk kernel-debug/vmlinux.xz
mkdir -p kernel-source kernel-build
tar -xJf sources/boot-rcu-sources.tar.xz -C kernel-source
tar -xJf sources/boot-rcu-generated.tar.xz -C kernel-build
tar -xzf kernel-debug/gdb-scripts.tar.gz -C kernel-debug
```

使用支持 AArch64 和 Python 的主机 GDB，并将下面路径替换为解压后的绝对路径：

```gdb
file /绝对路径/kernel-debug/vmlinux
set substitute-path /usr/src/kernel /绝对路径/kernel-source
set substitute-path /usr/src/debug/linux-raspberrypi/6.12.93+git /绝对路径/kernel-build
source /绝对路径/kernel-debug/vmlinux-gdb.py
```

这是启动/RCU 代码学习子集，不是能独立编译的完整源码树。
保留了 init、kernel 核心、mm、lib、完整 include、指定 Arm64 启动目录以及部分早期驱动；
多数其他驱动、文件系统和网络实现已省略。生成源码不含任何模块 `*.mod.c`。
单步进入未收录代码时，GDB 将无法显示对应源码；完整符号和 DWARF 仍保留在 vmlinux 中。

## 启动和 RCU 入口

实际符号表中已确认：启动可从 `primary_entry`、`start_kernel`、`setup_arch`、`paging_init` 看起；
RCU 可关注 `rcu_init`、`rcu_gp_kthread`、`call_rcu`、`synchronize_rcu`。
对应源码主要在 `arch/arm64/kernel/head.S`、`init/main.c`、`kernel/rcu/tree.c` 和
`include/linux/rcupdate.h`，均收录在精选源码包中。

本次实际配置是 `CONFIG_PREEMPT=y`、`CONFIG_TREE_RCU=y`、`CONFIG_PREEMPT_RCU=y`。
KGDB、串口 KGDB、FTRACE、函数/函数图跟踪、RCU_TRACE 和 DEBUG_FS 已编译开启。
当前启动参数没有配置 `kgdboc` 或 `kgdbwait`；编译支持并不表示板上的调试连接已经可用。
调试时建议在启动分区 `cmdline.txt` 原有同一行末尾追加 `nokaslr`，
避免 KASLR 带来的运行时地址偏移；修改后需重新启动。

普通串口 KGDB 注册较晚，不能保证在最早的 `head.S` 入口设置串口断点。
若需从最早指令开始调试，应单独准备并验证适合的 JTAG 或仿真调试环境；
UART 型号和 earlycon/轮询能力应在板上确认，不能固定假设 `ttyAMA0` 或 `ttyS0`。

## 板上查看 RCU 状态的通用示例

以下仅供实际启动后参考，未在本环境的 RPi4 硬件上执行。
先检查是否已经挂载；未挂载时，可按实际系统支持情况执行：

```sh
mkdir -p /sys/kernel/debug /sys/kernel/tracing
mount -t debugfs debugfs /sys/kernel/debug
mount -t tracefs tracefs /sys/kernel/tracing
ls /sys/kernel/debug/rcu
ls /sys/kernel/tracing/events/rcu
```

目录和事件以实机实际暴露的接口为准。先查看可用事件和当前状态，再选择跟踪范围；
启用大量跟踪会增加开销，不应把这些示例视作已验证的板上操作记录。
