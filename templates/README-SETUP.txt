RPi4 Yocto：只填写 WiFi 名称和 WiFi 密码
=====================================
1. 使用 Raspberry Pi Imager 烧录镜像，跳过 Raspberry Pi OS 专用定制。
2. 重新插入 SD 卡，在 Windows 可见的启动分区打开 network-config。
3. 只改这两行，等号后直接填内容，不加额外引号：

   SSID=你的WiFi名称
   PASSWORD=你的WiFi密码

   其余保持不动，保存为 UTF-8。Windows CRLF 换行和 UTF-8 BOM 都支持。
   SSID 最多 32 个 UTF-8 字节，密码 8..63 个字节或 64 位十六进制 PSK。
   名称和密码中的空格、中文及常见符号会按原样读取，不作为命令执行。
4. 安全弹出 SD 卡，插入树莓派并上电。WiFi 默认 DHCP、国家代码 CN。
   等待启动完成，在同一局域网电脑的 PowerShell 执行：

   ssh root@rpi4-debug.local

   用户名：root
   初始 SSH 密码：Rpi4GPIO-2026!

   不需要生成密钥、不需要 userconf.txt、不需要串口线。
   登录后可用 passwd 修改 SSH 密码；未改变 network-config 不会覆盖板上网络修改。

如果电脑不支持 .local 名称解析，在路由器 DHCP 列表中找到 rpi4-debug 的 IPv4，
再用 ssh root@该地址。以太网备用：插网线到 DHCP 路由器，同样账号密码可用。
当前 WiFi 是客户端连接现有 AP；默认 country=CN，WPA2-PSK/PMF optional，
可以连接提供 WPA2 兼容模式的 WPA2/WPA3 混合网络，不承诺 WPA3-only AP。

启动后的 setup-result.txt 会报告配置成功/错误，不包含 WiFi 密码、PSK 或口令哈希。
network-config 保留原始 WiFi 配置以便以后在 Windows 修改；请妥善保管 SD 卡。
根文件系统只保存推导后的 WPA PSK，/etc/wpa_supplicant.conf 权限为 0600。

GPIO：固件/引脚 overlay 参数仍在 config.txt。SSH 登录后可运行 gpioinfo、
gpioget、gpioset，使用前确认实际 gpiochip/line 映射。完整内核调试符号不变。

可选高级入口：authorized_keys 可导入 root SSH 公钥；userconf.txt 可导入
root:$6$... 格式的 SHA-512 crypt 密码哈希。这些都不是普通连接所必需的步骤。
