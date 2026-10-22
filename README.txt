RPi4 Wi-Fi v2 修复（不用重刷，不用修改 SSID/PASSWORD）

1. 关闭树莓派，将 SD 卡插回电脑。
2. 把本 ZIP 的 config.txt 和 rpi4-wifi-fix.cpio.gz 复制到 SD 卡可见启动分区根目录；覆盖 config.txt。
   config.txt 基于你提供的原文件，只增加一条 initramfs 启动指令。
3. 保留现有 network-config，弹出 SD 卡，再启动树莓派，等待约 2 分钟。
4. 若仍未联网，关机后将启动分区 repair-result.txt 和 network-status.txt 发回。
   日志不会包含 Wi-Fi 密码。network-status.txt 会记录接口、关联状态、IP 和 SSH 状态。
5. 联网确认后，可删除 config.txt 最后两行修复说明/指令，再删除 rpi4-wifi-fix.cpio.gz。
   保留修复指令重复启动也安全；修复脚本只接受指定镜像和已知导入器版本。

修复内容：SSID 编码改用目标 BusyBox 支持的 hexdump，修复旧导入缓存，并安装网络状态报告服务。
内核、调试符号、SSH 用户名密码、现有 network-config 均不改变。原导入器备份保存在
/var/lib/rpi4-setup/rpi4-headless-setup.before-wifi-v2。

此包已做归档完整性和脚本验证；云环境没有树莓派射频硬件，未声明实机启动或无线关联已验证。
