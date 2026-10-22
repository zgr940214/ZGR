# RPi4 Wi-Fi v2：配置 SSID、密码后连接网络

适用 Raspberry Pi 4 / 400，64 位 Yocto Scarthgap，Linux **6.12.93-v8**。
已预配 SSH 密码登录、Wi-Fi、以太网 DHCP、mDNS 和 GPIO 命令。

## Windows 使用步骤

1. 解压 ZIP，在 Raspberry Pi Imager 选择“使用自定义镜像”，选择 `image/rpi4-wifi-ready-6.12.93-v8-v2.img.xz`。
2. 选择 SD 卡并写入，不用事先格式化。写入会覆盖卡上原有数据；跳过 Imager 的 Raspberry Pi OS 专用定制。
3. 重新插入 SD 卡，打开 Windows 能看到的启动分区内 `network-config`，只改这两行：

   ```ini
   SSID=你的WiFi名称
   PASSWORD=你的WiFi密码
   ```

   等号后直接填写，不加额外引号。保存为 UTF-8；支持 Windows 换行和 UTF-8 BOM。
4. 安全弹出 SD 卡，插回树莓派并上电。在同一局域网的电脑执行：

   ```powershell
   ssh root@rpi4-debug.local
   ```

   用户名：`root`；初始密码：`Rpi4GPIO-2026!`；SSH 端口：`22`。
   首次登录后可执行 `passwd` 修改密码。如果电脑不支持 `.local`，使用路由器分配给树莓派的 IPv4。

GPIO 可用 `gpiodetect`、`gpioinfo`、`gpioget`、`gpioset`。以太网保留 DHCP，可直接接路由器。
Wi-Fi 默认国家代码 CN，使用 WPA2-PSK，支持提供 WPA2 兼容模式的混合网络。

## v2 修复了什么

v1 的配置脚本调用 `od -An -tx1`，但精简 BusyBox 不支持这些参数。
结果是生成的 `wpa_supplicant.conf` 中 SSID 为空，配置脚本却报告成功，板子无法连接 AP。
v2 修复了字节转十六进制的兼容性、验证转换结果，并能重新导入旧版本遗留的配置。

启动分区的 `setup-result.txt` 只表示配置导入结果；`network-status.txt` 另行报告实际 Wi-Fi 认证、IPv4 和 SSH 监听状态。
它不会写出 Wi-Fi 密码或 PSK。启动后需要时间完成认证与 DHCP；最终状态最多等待约两分钟。

本次已重新构建镜像，在虚拟执行环境使用镜像自带的 ARM64 BusyBox 和 WPA 工具验证转换及启动链。
未在实体树莓派上验证无线连接；验证记录位于 `verification/`。

## 内核符号与项目

本次只修复用户空间配置，内核未改变。已有的 **6.12.93-v8 完整调试符号仍匹配**，不必重新下载。
镜像加完整符号包：
https://github.com/zgr940214/ZGR/archive/refs/tags/rpi4-wifi-ready-6.12.93-v8-full-v2.zip

可直接克隆固定版本的 Yocto 配置：

```bash
git clone --single-branch --no-tags --branch yocto-rpi4 https://github.com/zgr940214/ZGR.git rpi4-yocto
```

ZIP 的 `project/rpi4-yocto-project.tar.gz` 也包含本次构建配置。所有负载文件的 SHA-256 位于 `SHA256SUMS`。
