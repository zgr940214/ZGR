# Raspberry Pi 4: wait before Linux for TRACE32 attach

这是给现有 Pi 4 / Cortex-A72 / E50 SMP 调试连接使用的启动等待程序。它让 CPU0 在进入 Linux 之前等待，方便连接调试器。内核镜像与 `vmlinux` 无需重新构建。

适用：本项目的 `raspberrypi4-64` 普通低外设地址配置；不适用于设置了 `arm_peri_high=1` 或使用其他自定义安全固件的启动方式。

## 文件

- `armstub8-debug.bin`：768 字节，复制到 SD 卡启动分区。
- `armstub8-debug.elf`：这个等待程序的 ELF，留在电脑上供 TRACE32 加载符号。
- `armstub8-debug.S` / `armstub8-upstream.S`：修改版与固定版本的官方源码，包含许可证。
- `armstub8-debug.disassembly.txt`：完整反汇编。
- `build.py`、`verify_gate.py`：构建检查及 AArch64 模拟执行检查。
- `BUILD-VERIFICATION.txt`、`EMULATION-VERIFICATION.txt`：验证结果与范围。

源码基于 `raspberrypi/tools@439b6198a9b340de5998dd14a26a0d9d38a6bcac`，按官方 Pi 4 目标启用 `GIC=1 BCM2711=1`。

## SD 卡准备

1. 正常关机，把 SD 卡接到电脑，备份 `config.txt` 和 `cmdline.txt`。
2. 把 `armstub8-debug.bin` 复制到能看到 `config.txt` 的启动分区根目录。
3. 在 `config.txt` 末尾添加以下内容。如果已有自定义 `armstub=`，先保留其备份，再用下面的设置替换。

```ini
[all]
arm_64bit=1
enable_jtag_gpio=1
armstub=armstub8-debug.bin
```

`enable_jtag_gpio=1` 由固件配置 GPIO22–27 及 SoC 内部 JTAG 连接，因此在 Linux 尚未启动时也能连接。

4. 在 `cmdline.txt` 原有那一行的末尾增加一个空格和 `nokaslr`。保留原有 root、console 等全部参数，整个文件仍是一行。
5. 将卡放回 Pi 4，接好调试器并上电。此时故意不会启动到 SSH：CPU0 正在等待调试器放行。

## 第一站：确认等待点

运行已经验证能连接的 `pi4_e50_attach_smp.cmm`，然后在 TRACE32 命令栏执行：

```text
Break.direct
CORE.select 0
Data.LOAD.Elf "D:\rpi4-boot-debug\armstub8-debug.elf" /NoCODE /NoRegister
CORE.List
Register.view
List.Mix
```

把 ELF 路径改为电脑上的实际位置。这次先加载等待程序的符号；加载 ELF 会替换之前的符号，不能继续沿用上一次启动的 KASLR 偏移。

预期结果：CPU0 的 PC 为 `0x200`，指令为 `b 0x200`，符号为 `debug_gate`，处于 EL2，MMU 未开启。CPU1–3 留在原来的 WFE 等待流程，暂停位置通常在 `0x78` 至 `0x80`。

如果 CPU0 不在 `0x200`，先检查这个等待点是否实际生效，不要直接把 PC 改成 `0x204`。

## 第二站：亲眼看到 Linux 入口与启动参数

确认第一站后，保持选中 CPU0：

```text
Register.Set PC 0x204
```

之后每次点击一次汇编单步 `Step`，观察变化：

| 已执行的单步次数 | 下一条指令的 PC | 已发生的事情 |
| --- | --- | --- |
| 1 | `0x8c` | 回到官方 `primary_cpu` |
| 2 | `0x90` | X4 从固件槽读取实际 Linux Image 入口 |
| 3 | `0x94` | X0 从固件槽读取设备树 DTB 地址 |
| 4 | `0x98` | X1 清零 |
| 5 | `0x9c` | X2 清零 |
| 6 | `0xa0` | X3 清零，下一条为 `br x4` |
| 7 | 等于 X4 | 真正进入 `kernel8.img` / Linux Image |

实际入口以 X4 为准，不预设一定是 `0x80000`。本项目的原始 Image 入口有两条指令：EFI 签名兼容指令，然后分支到 `primary_entry`。再单步两次，即到 Linux 的 `primary_entry`。

后续观察顺序：`primary_entry` → `init_kernel_el` → `__cpu_setup` → `__primary_switch` / `__enable_mmu` → `__primary_switched` → `start_kernel` → `rcu_init` → `rest_init` → `kernel_init` / `smp_init` → 各从核的 `secondary_start_kernel`。

早期 PC 使用低地址；开启 MMU 后仍会经过恒等映射，随后显式跳转到高位内核虚拟地址。物理阶段和虚拟阶段的断点地址需要分别处理。在内核源码阶段重新加载匹配的 `vmlinux`；`nokaslr` 生效后，其正常虚拟地址符号无需添加上一次启动的随机偏移。不要对正在运行的内核直接修改 PC 来“重新执行”这些初始化函数。

## 恢复普通启动

关机后移除新增的 `armstub=armstub8-debug.bin` 行；若原先有自定义 armstub，则恢复原配置。下次启动会使用正常启动流程。`nokaslr` 可保留用于调试，也可移除以恢复地址随机化。

## 验证与复现

已完成交叉汇编、链接、反汇编和二进制布局检查。与官方 stock armstub 的前 512 字节相比，仅 `0x70` 的分支目标改变；固件 magic/version、DTB/内核入口槽和其他三核的 mailbox/等待代码保持不变。追加在 `0x200` 的循环和 `0x204` 的返回分支构成等待点。

Unicorn 2.1.4 的 AArch64 执行检查覆盖四种内核入口/DTB 组合、三个从核的等待及 mailbox 放行，以及实际 6.12.93-v8 Image 的入口分支。模拟从已有初始化之后的分支开始，不覆盖 VideoCore 固件、GIC/时钟初始化或完整 Linux 启动。

尚未在 Pi 4 / E50 实机上执行此等待程序，也未在本环境实际运行 TRACE32。ELF 是调试元数据，目标执行的文件是 `.bin`。

```sh
python3 build.py --gcc aarch64-linux-gnu-gcc --binutils-prefix aarch64-linux-gnu-
# 在已安装 unicorn==2.1.4 的 Python 环境中：
python3 verify_gate.py --kernel-image /path/to/this-project/Image
```

`verify_gate.py` 最后的 Image 入口地址断言针对本项目固定的 6.12.93-v8 构建。

参考：[官方 armstub 源码](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S)、[官方 boot 配置说明](https://github.com/raspberrypi/documentation/blob/ddea98e98dafe9419feb4fd82710c2fbdef7dc44/documentation/asciidoc/computers/config_txt/boot.adoc)、[官方 JTAG GPIO 配置说明](https://github.com/raspberrypi/documentation/blob/ddea98e98dafe9419feb4fd82710c2fbdef7dc44/documentation/asciidoc/computers/config_txt/gpio.adoc)。
