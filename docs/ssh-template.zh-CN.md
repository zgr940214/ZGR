# 可选的有线 SSH 模板

已发布的 17 MiB 精简镜像没有 sshd，也没有 DHCP 初始化脚本；复制配置文件或在
FAT 启动分区放置空的 ssh 文件不能安装这些组件。这里提供新的可选镜像配方，
需要在构建机上重新生成镜像。现有下载包不包含此可选 SSH 配置。

模板位于 `meta-rpi4-debug/recipes-core/images/rpi4-boot-rcu-ssh-image.bb`。
它继承固定版本内核和零模块镜像，只增加 OpenSSH、init-ifupdown 和
busybox-udhcpc；有线 eth0 使用 DHCP，AP / Wi-Fi 暂不加入。

在工程目录执行：

```bash
bash scripts/bitbake.sh rpi4-boot-rcu-ssh-image
```

不要使用原来的 `build-boot-rcu.sh` 构建此目标：那个入口构建原始无 SSH 镜像，
其验收器也明确要求没有 sshd。

新输出是 `build/tmp/deploy/images/raspberrypi4-64/rpi4-boot-rcu-ssh-image-raspberrypi4-64.rootfs.wic.xz`。
复制或改名为 `.img.xz` 后通过 Imager 烧录。

首次在板子上通过串口以 root 空密码登录，设置密码并确认配置：

```sh
passwd
/usr/sbin/sshd -t
/etc/init.d/sshd restart
ifconfig -a
```

插网线到提供 DHCP 的路由器。首次启动会自动生成 SSH host keys；此过程可能需要等待。
OpenSSH 与 networking 已由 SysVinit 管理，不使用 systemctl。
确认实际接口名和获得的 IPv4 地址；如果不是 eth0，修改
`/etc/network/interfaces` 的两处 eth0，然后从串口运行
`/etc/init.d/networking restart`。从电脑连接：

```sh
ssh root@树莓派的IPv4地址
```

修改 SSH 选项的位置是 `/etc/ssh/sshd_config.d/00-local.conf`。当前上游配置
支持这个 Include 目录。该模板允许 root 的密码/公钥登录，但不允许 SSH 空密码；
移除了原镜像的 allow-empty-password 特性，避免 Yocto 改写主配置允许 SSH 空密码。
串口初始空密码由保留的 empty-root-password 特性控制，设置密码后串口也需要该密码。

可选静态 IPv4 模板（地址、网关和 DNS 按自己的局域网修改）：

```conf
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.50
    netmask 255.255.255.0
    gateway 192.168.1.1
```

静态地址时还需在 `/etc/resolv.conf` 中配置合适的 `nameserver`。
网络参数修改请从串口操作，避免中断正在使用的 SSH 连接。

此模板已通过 `bash scripts/bitbake.sh -e rpi4-boot-rcu-ssh-image` 的元数据解析，
解析结果包含 SSH packagegroup、有线 DHCP 包，且不含 allow-empty-password。
新的 SSH 镜像尚未构建、烧录或实机验证。
