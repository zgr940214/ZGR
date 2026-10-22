require recipes-core/images/rpi4-boot-rcu-image.bb

SUMMARY = "Headless SSH and GPIO image for Raspberry Pi 4 boot and RCU study"
DESCRIPTION = "Full-symbol kernel with OpenSSH, wired networking and GPIO tools. Import a public key and network settings from the FAT boot partition without a serial console. Wireless/AP support is not installed."

# Keep initial local serial login, but require a password for SSH.
IMAGE_FEATURES:remove = "allow-empty-password"
IMAGE_FEATURES:append = " ssh-server-openssh allow-root-login"
IMAGE_INSTALL:append = " init-ifupdown busybox-udhcpc libgpiod-tools rpi4-headless-setup"

# Windows-editable settings are deployed into the root of the FAT partition.
IMAGE_BOOT_FILES:append = " rpi4-headless-bootfiles/*"
do_image_wic[depends] += "rpi4-headless-setup:do_deploy"

ROOTFS_POSTPROCESS_COMMAND:append = " configure_boot_rcu_ssh; "
configure_boot_rcu_ssh() {
    install -d ${IMAGE_ROOTFS}${sysconfdir}/ssh/sshd_config.d
    install -d ${IMAGE_ROOTFS}${sysconfdir}/network

    cat > ${IMAGE_ROOTFS}${sysconfdir}/ssh/sshd_config.d/00-local.conf <<'SSH_SETTINGS'
Port 22
AddressFamily inet
PermitRootLogin yes
PasswordAuthentication yes
PermitEmptyPasswords no
PubkeyAuthentication yes
SSH_SETTINGS

    cat > ${IMAGE_ROOTFS}${sysconfdir}/network/interfaces <<'NETWORK_SETTINGS'
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
NETWORK_SETTINGS
}
