# RPi4：Wi-Fi 镜像 + 完整内核调试符号 + 启动/RCU 源码

本 ZIP 同时包含预配 SSH 的新 Wi-Fi 镜像，以及与其匹配的完整 `vmlinux`、`System.map`、内核配置、GDB 辅助文件和精选启动/RCU 源码。
Linux **6.12.93-v8**，完整 DWARF4，未剥离或裁剪 ELF 调试信息。

## Windows 使用步骤

1. 解压 ZIP。在 Raspberry Pi Imager 中选择“使用自定义镜像”，
   选择 `image/rpi4-wifi-ready-6.12.93-v8.img.xz`，烧录一次。
   无需先解压 XZ；跳过 Raspberry Pi OS 专用定制设置。
2. 重插 SD 卡，打开 Windows 可见的 FAT 启动分区中的 `network-config`。
   只修改这两行，等号后直接填写自己的内容，不要额外加引号：

   ```text
   SSID=你的WiFi名称
   PASSWORD=你的WiFi密码
   ```

   空格、中文和标点按原样填写；保存为 UTF-8 即可，支持 Windows CRLF 和 UTF-8 BOM。
   SSID 最多 32 个 UTF-8 字节；密码为 8～63 个字节，或 64 位十六进制 PSK。
3. 安全弹出卡，插入 Pi 并上电，等待启动完成。在同一局域网的 PowerShell 中执行：

   ```powershell
   ssh root@rpi4-debug.local
   ```

   初始用户名为 `root`，初始 SSH 密码为 **`Rpi4GPIO-2026!`**。
   不需要密钥、userconf.txt、串口或自行生成密码哈希。
   登录后可用 `passwd` 修改这个开发用初始密码。

如果电脑不能解析 `.local`，在路由器 DHCP 客户端列表查找 `rpi4-debug` 的 IPv4 地址，
改用 `ssh root@实际IP`。网线连接 DHCP 路由器也可作为备用入口，账号密码相同。
导入结果可在启动分区 `setup-result.txt` 中查看；其中不写入 Wi-Fi 密码或 PSK。

Wi-Fi 是连接现有 AP 的客户端模式，不提供 AP 热点。
默认国家代码为 **CN**；面向 WPA2-PSK 和提供 WPA2 兼容模式的 WPA2/WPA3 混合网络，
不承诺连接 WPA3-only AP。`network-config` 是自定义 KEY=VALUE 格式，不是 cloud-init YAML。

## GPIO 与已有调试符号

镜像已带 `gpiodetect`、`gpioinfo`、`gpioget`、`gpioset` 等 libgpiod 2.1.3 工具，
`CONFIG_GPIO_CDEV` 内建。可先运行 `gpiodetect` 和 `gpioinfo` 查看实际芯片与线路映射；
引脚复用及设备树 overlay 仍可在启动分区 `config.txt` 中修改。
GPIO line 编号不等于排针物理编号，应按自己的接线确认。

此镜像只加入 Wi-Fi 所需的一小组完整 DWARF 模块、RPi4 固件和签名监管数据库，
没有加入全部内核模块。实际安装的模块及其逐字节核对结果记录在产物验收日志中。
底层内核 ELF 与原完整符号文件的 SHA-256 相同，原来的 GDB 符号和路径映射不变。
`verification/vmlinux-compression.json` 保留无损压缩的原文件/压缩文件哈希证明。

## 校验与验证范围

解压后进入最外层目录执行 `sha256sum -c SHA256SUMS`。
`image/` 含新镜像及校验文件、匹配的 WIC bmap；`templates/` 是 FAT 上两份配置说明的副本。
`project/rpi4-yocto-project.tar.gz` 保存当前新目标、导入脚本及构建配置。

`verification/` 保留本轮真实构建/产物验收日志、19 项 Wi-Fi 配置 fixture 检查和新目标
QEMU-user AArch64 工具/SSH 检查记录。软件验证包括使用新镜像预置密码完成真实 SSH 密码握手，
并验证错误密码被拒绝；它不等于在 RPi4 硬件上测试无线网络。
实际硬件启动、Wi-Fi 关联、mDNS/NIC 连通性、真实 GPIO 电气行为和 KGDB 接线尚未实测。

## 完整内核符号与 GDB

`kernel-debug/vmlinux.xz` 是完整 AArch64 内核 ELF 的无损压缩，解压后为 404,542,840 字节。
`kernel-debug/System.map` 是文本符号地址表；GDB 加载 `vmlinux`，保留函数、类型、变量和源码行信息。
Windows 可用 7-Zip 解压 XZ；WSL/Linux 可执行：

```bash
xz -dk kernel-debug/vmlinux.xz
mkdir -p kernel-source kernel-build
tar -xJf sources/boot-rcu-sources.tar.xz -C kernel-source
tar -xJf sources/boot-rcu-generated.tar.xz -C kernel-build
tar -xzf kernel-debug/gdb-scripts.tar.gz -C kernel-debug
```

在支持 AArch64 和 Python 的 GDB 中，替换为本机实际绝对路径：

```gdb
file /绝对路径/kernel-debug/vmlinux
set substitute-path /usr/src/kernel /绝对路径/kernel-source
set substitute-path /usr/src/debug/linux-raspberrypi/6.12.93+git /绝对路径/kernel-build
source /绝对路径/kernel-debug/vmlinux-gdb.py
```

可关注 `primary_entry`、`start_kernel`、`rcu_init`、`rcu_gp_kthread`、`call_rcu`、`synchronize_rcu`。
源码归档精选启动/RCU；完整 ELF 调试信息未裁剪。完整内核树可按 `project/` 的固定配置获取。
内核启用 KGDB/FTRACE/RCU_TRACE，启动参数未预设 KGDB；按实际调试方式配置连接和 `nokaslr`。
`verification/wifi-full-symbols-verification.json` 记录本包 ELF 解压后与当前镜像内核的精确哈希匹配。
