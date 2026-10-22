# RPi4：只填 Wi-Fi 名称和密码即可 SSH 登录

这是新目标 `rpi4-boot-rcu-wifi-image` 的镜像升级包。
Linux **6.12.93-v8** 完整符号内核保持不变；已有启动/RCU 调试包的符号和精选源码可继续使用，
不需要再次下载 87 MB 的 `vmlinux.xz`。本 ZIP 不重复包含符号或源码归档。

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
