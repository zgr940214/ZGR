# RPi4 网线 SSH 与 GPIO 启动调试镜像

新目标 `rpi4-boot-rcu-ssh-image` 提供 OpenSSH、eth0 有线网络和 libgpiod **2.1.3** 工具。
沿用 Linux **6.12.93-v8** 的完整 DWARF4 内核，不安装任何 `.ko`，不加入 Wi-Fi/AP 栈。
Windows 上准备好启动分区后即可通过网线 SSH 登录，无需串口完成首次配置。

已有上一个启动/RCU 包的完整符号时，优先下载 `*-image.zip`，不必重复下载符号和源码。
`*-full.zip` 在相同镜像上增加无损压缩的完整内核符号、GDB 辅助文件和精选启动/RCU 源码。
原 `vmlinux` 的 SHA-256 保持不变；已有符号可继续使用。

## Windows 首次配置

1. 解压所选 ZIP。在 Raspberry Pi Imager 中选择“使用自定义镜像”，打开
   `image/rpi4-headless-ssh-gpio-6.12.93-v8.img.xz`，烧录 SD 卡；无需先解压 XZ。
   跳过 Raspberry Pi OS 的系统定制设置。
2. 重新插入 SD 卡，打开 Windows 可见的 FAT 启动分区。
   分区已有 `network-config`，默认 `INTERFACE=eth0`、`MODE=dhcp`，接普通 DHCP 路由器时无需修改。
3. 在 PowerShell 中生成自己的 SSH 密钥（已有合适密钥则直接使用，避免覆盖）：

   ```powershell
   ssh-keygen -t ed25519
   Copy-Item "$env:USERPROFILE\.ssh\id_ed25519.pub" 'E:\authorized_keys'
   ```

   将 `E:` 换成 SD 卡启动分区盘符。只复制 `.pub` 公钥，不复制 `id_ed25519` 私钥；
   目标文件名必须是 `authorized_keys`，不要附加 `.txt`。
4. 安全弹出卡，插入 RPi4，将 Pi 的网口用网线接路由器后上电。
   在路由器 DHCP 客户端列表查找 Pi 的 IPv4 地址，然后登录：

   ```powershell
   ssh root@192.168.1.50
   ```

   用实际 IP 替换示例地址；若设置了密钥口令，输入的是自己的密钥口令。
   没有预置共享密码或公钥，SSH 不允许空密码登录。
   若使用非默认密钥文件，可指定 `ssh -i "$env:USERPROFILE\.ssh\YOUR_KEY" root@实际IP`。

`templates/` 是启动分区四个配置/说明文件的副本；首次导入结果在 FAT 分区的
`setup-result.txt` 中查看。未改变的导入文件不会在后续启动覆盖板上的相应配置。
`network-config` 使用自定义 **KEY=VALUE** 格式，不是 cloud-init YAML；支持 Windows CRLF 和 UTF-8 BOM。

固定 IPv4 时，可将启动分区 `network-config` 改为下例，数值按实际网络调整，不加引号：

```text
INTERFACE=eth0
MODE=static
ADDRESS=192.168.1.50
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
DNS=192.168.1.1 1.1.1.1
```

可选密码方式见 `templates/userconf.txt.example` 和 `templates/README-SETUP.txt`：
在可信电脑用 `openssl passwd -6` 生成自己的 SHA-512 crypt 密码哈希，
以一行 `root:生成的哈希` 保存为启动分区 `userconf.txt`，不要填写明文密码或示例占位符。
有效密码文件导入后会删除。Windows 用户通常直接使用 SSH 公钥更方便。

## GPIO

内核 `CONFIG_GPIO_CDEV=y` 已内建，用户态已带 `gpiodetect`、`gpioinfo`、`gpioget`、`gpioset` 等 2.1.3 工具；
无需为了这些工具下载全部 `.ko`。GPIO 复用和设备树 overlay 仍在启动分区 `config.txt` 中配置。
登录后可先运行 `gpiodetect`、`gpioinfo` 查看实际 gpiochip/line 映射，再按工具 `--help` 请求正确线路。
GPIO line 编号不等于排针物理编号；实际电气行为需在自己的板和接线条件下确认。

## 校验、符号与源码

解压后在最外层目录执行 `sha256sum -c SHA256SUMS`。
`verification/` 包含新目标本轮构建/产物验收日志、启动分区导入 fixture 测试及 QEMU-user 下真实
AArch64 工具的 smoke 记录。这些检查不等于 RPi4 实机启动、NIC/SSH 实际联网、真实 GPIO 或 KGDB 接线测试；
这些硬件操作尚未实测。

完整包中 `kernel-debug/vmlinux.xz` 解压后仍是完整符号 ELF：

```bash
xz -dk kernel-debug/vmlinux.xz
mkdir -p kernel-source kernel-build
tar -xJf sources/boot-rcu-sources.tar.xz -C kernel-source
tar -xJf sources/boot-rcu-generated.tar.xz -C kernel-build
tar -xzf kernel-debug/gdb-scripts.tar.gz -C kernel-debug
```

在支持 AArch64 和 Python 的主机 GDB 中设置实际绝对路径：

```gdb
file /绝对路径/kernel-debug/vmlinux
set substitute-path /usr/src/kernel /绝对路径/kernel-source
set substitute-path /usr/src/debug/linux-raspberrypi/6.12.93+git /绝对路径/kernel-build
source /绝对路径/kernel-debug/vmlinux-gdb.py
```

镜像升级包不含上述符号/源码文件，请直接使用已有完整包的对应目录。
精选源码覆盖启动与 RCU，并非独立可编译的完整内核树；多数其他驱动、文件系统和网络实现已省略。
可关注真实符号 `primary_entry`、`start_kernel`、`rcu_init`、`rcu_gp_kthread`、`call_rcu`、`synchronize_rcu`。
内核仍为 PREEMPT/TREE_RCU，KGDB/FTRACE/RCU_TRACE 已启用，但启动参数没有配置 KGDB；
调试时可按原说明添加 `nokaslr`。串口 KGDB 不能保证在最早 `head.S` 处断下。
`project/rpi4-yocto-project.tar.gz` 保存新目标和导入脚本的构建配置。
