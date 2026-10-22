require recipes-core/images/rpi4-boot-rcu-ssh-image.bb

SUMMARY = "Ready-to-login Raspberry Pi 4 Wi-Fi, SSH, GPIO and kernel-debug image"
DESCRIPTION = "Enter only SSID and PASSWORD on the FAT partition. Wi-Fi drivers, board firmware, DHCP, SSH, a development root account and GPIO tools are preconfigured; the full-symbol pinned kernel is unchanged."

inherit extrausers

IMAGE_FEATURES:remove = "allow-empty-password empty-root-password"
IMAGE_INSTALL:append = " \
    kernel-module-brcmfmac-wcc \
    linux-firmware-rpidistro-bcm43455 \
    linux-firmware-rpidistro-bcm43456 \
    wireless-regdb-static \
    wpa-supplicant wpa-supplicant-passphrase wpa-supplicant-cli \
    rpi4-network-status \
    avahi-daemon dbus \
"

# Development login: root / Rpi4GPIO-2026! . The kernel symbols are unchanged.
RPI4_ROOT_PASSWORD_HASH = "\$6\$aRkugIdI2FX5BNpu\$ID7zCZ5eEAselvC0C4qkjZ/iMU8.IuByjU6SNUaqIJFi4Gklyf96PVta4Hu4uRiAbjXNGlEgiws/MwroGjt3d0"
EXTRA_USERS_PARAMS = "usermod -p '${RPI4_ROOT_PASSWORD_HASH}' root;"

# The user only needs these two FAT files; legacy key/password examples remain
# available in /usr/share/rpi4-setup, without cluttering the boot partition.
IMAGE_BOOT_FILES:remove = "rpi4-headless-bootfiles/*"
IMAGE_BOOT_FILES:append = " rpi4-headless-bootfiles/network-config;network-config rpi4-headless-bootfiles/README-SETUP.txt;README-SETUP.txt"

ROOTFS_POSTPROCESS_COMMAND:append = " configure_ready_wifi_image; "
configure_ready_wifi_image() {
    printf '%s\n' rpi4-debug > ${IMAGE_ROOTFS}${sysconfdir}/hostname
    install -d ${IMAGE_ROOTFS}${sysconfdir}/modules-load.d
    printf '%s\n' brcmfmac > ${IMAGE_ROOTFS}${sysconfdir}/modules-load.d/rpi4-wifi.conf

    # WPA and SSH use IPv4. Avahi publishes rpi4-debug.local so users need not
    # configure a fixed address or SSH keys before their first login.
    cat > ${IMAGE_ROOTFS}${sysconfdir}/avahi/avahi-daemon.conf <<'AVAHI_SETTINGS'
[server]
host-name=rpi4-debug
domain-name=local
use-ipv4=yes
use-ipv6=no
allow-interfaces=wlan0,eth0
enable-dbus=yes
[publish]
publish-addresses=yes
publish-workstation=no
[reflector]
enable-reflector=no
AVAHI_SETTINGS
}
