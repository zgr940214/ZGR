# Raspberry Pi 4 Yocto 调试镜像

目标是 RPi4 / BCM2711 的 64 位 Linux 镜像，使用 Yocto Scarthgap LTS
5.0.21 和 Raspberry Pi Linux **6.12.93**。源码、BSP、内核与内核 metadata
均固定到完整 Git SHA，见 [sources.lock.json](sources.lock.json)，不使用 AUTOREV。

## 编译

克隆项目的 `yocto-rpi4` 分支后编译：

```bash
git clone --branch yocto-rpi4 https://github.com/zgr940214/ZGR.git rpi4-yocto
cd rpi4-yocto
bash scripts/setup.sh
bash scripts/build.sh
```

仓库包含构建配置、脚本和已完成的构建验收记录。固定版本的上游源码由
`setup.sh` 获取；镜像、完整调试符号和下载缓存不提交到 Git，运行构建后生成。
当前云环境中已有项目时，直接进入 `/workspace/rpi4-yocto` 执行上述两个脚本。

`setup.sh` 准备固定版本的 Poky/BSP、build/conf 和 Ubuntu 24.04 构建容器。
容器基础镜像固定 digest；APT 校验签名，下载保留 TLS 和配方 checksum 校验。
主机需要 Docker、Git、Python 3.11 以上，并以普通非 root 用户运行。
Python 用于构建工具 BitBake。
容器以调用者的 UID/GID 运行，不使用 privileged，不修改宿主系统软件包。
构建配置与本地 layer 位于本目录，上游 checkout 保持不变。

`build.sh` 实际执行 `bitbake rpi4-debug-image`，保留退出状态与完整日志，
只有构建和产物检查都成功才返回 0。日志在 `logs/build-*.log` 与
`logs/artifacts-*.log`。脚本先完成内核及模块的编译、安装；空间不足 16 GiB 时，
在 BitBake 停止后验证已链接的完整符号，再删除可重新生成的 `.o` 链接输入及其 `.o.cmd` 依赖缓存。
`vmlinux`、全部 `.ko`、源码、生成的源码和头文件、GDB 工具均保留。
这一步及内核安装日志分别在 `logs/kernel-objects-*.log` 和
`logs/kernel-install-*.log`；重新编译内核时会按需重新生成中间对象。
随后在同一个容器内清理本镜像的旧任务状态并构建完整镜像，确保临时目录能安全重建。
镜像配方的任务日志会在容器退出时复制到 `logs/image-tasks-*/`。
检查配置可单独执行：

```bash
bash scripts/bitbake.sh -p
```

需要调整内核配置时，持久设置应放入
`meta-rpi4-debug/recipes-kernel/linux/files/full-kernel-debug.cfg`。

## 完整内核调试信息

- 内核使用完整 DWARF4；禁用 reduced、split、debug 信息压缩。
- 仅对内核禁用 package strip 和 debug split；镜像内的 `.ko` 保留完整符号。
- 启用 KALLSYMS_ALL、GDB_SCRIPTS、IKCONFIG、IKCONFIG_PROC。
- 普通 `Image` 用于树莓派启动；未 strip 的 `vmlinux` 单独部署用于主机 GDB。
- 镜像包含全部内核模块、OpenSSH、gdbserver；登录凭据需另行配置。

成功构建后的目录为 `build/tmp/deploy/images/raspberrypi4-64/`：

```text
rpi4-debug-image-raspberrypi4-64.rootfs.wic.bz2
rpi4-debug-image-raspberrypi4-64.rootfs.wic.bmap
rpi4-debug-image-raspberrypi4-64.rootfs.tar.bz2
rpi4-kernel-debug/                  # 指向当前内核版本的符号目录
  vmlinux
  System.map
  kernel.config
  Module.symvers
  modules-with-debug.tar.gz
  kernel-source.tar.gz
  gdb-scripts.tar.gz
  build-metadata.json
  SHA256SUMS
```

手动检查产物：

```bash
python3 scripts/verify-artifacts.py
```

检查覆盖 SHA-256、内核实际版本、源码版本、固定 SHA、AArch64 ELF、完整
DWARF4、关键内核符号、每个模块的调试节、rootfs 模块与调试归档的一致性，
以及 WIC 的分区范围。缺产物、符号被剥离或版本不符都会失败。
`--kernel-only` 仅用于明确的内核检查，不能作为镜像构建通过的依据。
这不等同于实机启动测试，本环境没有接入 RPi4 硬件。

调试时解压 `kernel-source.tar.gz` 到独立源码目录，把 `gdb-scripts.tar.gz`
解压到 `vmlinux` 旁边；在 AArch64 GDB 中使用 `file vmlinux`、
`set substitute-path /usr/src/kernel /实际源码目录`，再加载 `vmlinux-gdb.py`。
归档包含当前配置生成的 `linux/constants.py`，不依赖原构建机的绝对符号链接。
编译器生成的 `.mod.c`、`include/generated` 等文件位于保留的内核构建目录，
不在源码归档中；调试这些文件时，还应将
`/usr/src/debug/linux-raspberrypi/6.12.93+git` 映射到
`build/tmp/work/raspberrypi4_64-poky-linux/linux-raspberrypi/6.12.93+git/linux-raspberrypi4_64-standard-build`
的绝对路径。

## 资源和网络

默认同时调度 2 个配方任务，每个编译任务使用 `-j4`，以降低磁盘峰值。
启用 rm_work 清理非内核中间产物；内核工作目录保留，
低空间时由上述分阶段构建回收已完成链接的 `.o` 中间对象。
完整 DWARF 和所有模块使临时空间明显增大，建议提供至少 **100 GB 可用空间**。
本次在 32 GB 文件系统、32 GiB RAM 的云环境中完成了实际完整构建；
最终保留镜像、完整调试包及构建缓存后，约有 5.5 GiB 磁盘可用。
当前构建入口默认使用 **12 GiB 容器内存盘**承载镜像配方的临时工作目录，
包括 rootfs、分区临时文件和未压缩 WIC；建议主机至少有 **24 GiB RAM**。
12 GiB 是内存盘的容量上限，并非预先占满。当前 Docker 使用 vfs 驱动，
每个运行中的构建容器还会临时占用约 1.1 GiB 磁盘；该开销会在容器退出后释放。
最终压缩镜像、调试产物、日志及源码仍保存在项目磁盘。
磁盘充足且内存较少的机器可使用 `RPI4_IMAGE_TMPFS_GB=0 bash scripts/build.sh`
改用磁盘临时目录。请通过 `build.sh` 构建完整镜像，保证内存盘模式下的任务顺序与重试正确。
仅请求压缩 WIC 时，发布前会删除已完成转换的 raw WIC 中间文件；完整压缩镜像保留。
关闭重复的默认模块 tarball 和 deploy/image-complete sstate 压缩副本，
完整模块已在调试包中，并且仍对全部最终产物进行验收。
磁盘降至 2 GB 时配置会停止调度，降至 1 GB 时中止。
`setup.sh` 会从树莓派官方 GitHub 仓库获取固定提交，生成标准 BitBake 浅缓存，
并验证完整 Git 对象、引用和归档往返，避免首次构建下载全部内核历史。
浅包位于独立 `kernel-source-cache/` 目录，通过内核 recipe 专用的本地
`file://` 镜像交给 BitBake 使用。本次生成的浅包为 258 MiB；复用现有缓存
也会重新验证。下载目录里的链接和完成标记由 BitBake 自行管理。
其余 Git 源仍使用 `BB_GIT_SHALLOW=1`，缺少浅镜像时可能完整克隆上游。

已配置官方源码镜像与 sstate 镜像，核心目标域名包括
`downloads.yoctoproject.org`、`sstate.yoctoproject.org`、
`git.yoctoproject.org`、`github.com`、`api.github.com`。
网络策略变更需在环境设置保存后对当前实例生效，写入草稿本身不会开放网络。
不要通过禁用 TLS、checksum 或 sanity 检查规避下载失败。

## 当前验证状态

2026-10-21，已在本云执行环境的 Ubuntu 24.04 容器中实际编译完整镜像。
内核与全部模块已实际交叉编译；修正产物读取器后，重新运行整个
`bash scripts/build.sh`，最终退出码为 **0**。
最终一轮 BitBake 的 3755 项任务全部成功，已完成的编译结果正常复用。

- 实际内核 release：`6.12.93-v8`，AArch64，完整 DWARF4。
- 未 strip 的 `vmlinux` 和全部 **1890** 个内核模块通过检查。
- rootfs 中全部模块与调试归档逐字节一致；源码版本、固定 SHA、
  调试包 SHA-256、WIC 分区范围与压缩流完整性均通过检查。
- Ubuntu 构建容器、重复 setup 和完整 BitBake 解析也已通过。

本次云环境验证的构建与验收日志随仓库保存：

- [完整镜像构建](verification/build-20261021T111820Z.log)
- [完整产物验收](verification/artifacts-20261021T111820Z.log)

其他任务日志仅保留在原云环境的 `logs/kernel-install-20261021T111820Z.log`、
`logs/kernel-objects-20261021T111820Z.log` 和
`logs/image-tasks-20261021T111820Z/1.0/temp/`，不随 Git 仓库发布。
这些记录来自已经完成的云环境构建；新克隆的项目需运行上述构建命令。

本次验证涵盖实际编译与产物检查；尚未进行 RPi4 实机启动测试。
