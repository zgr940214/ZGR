SUMMARY = "Report actual startup Wi-Fi, IPv4 and SSH status on the Raspberry Pi boot partition"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://rpi4-network-status file://rpi4-network-status.init"
S = "${WORKDIR}"

inherit update-rc.d
INITSCRIPT_NAME = "rpi4-network-status"
# Networking S01, sshd S09 and Avahi S21 have been invoked before this.
INITSCRIPT_PARAMS = "start 22 2 3 4 5 ."
RDEPENDS:${PN} = "busybox wpa-supplicant-cli"

do_install() {
    install -d ${D}${sbindir} ${D}${sysconfdir}/init.d
    install -m 0755 ${WORKDIR}/rpi4-network-status ${D}${sbindir}/rpi4-network-status
    install -m 0755 ${WORKDIR}/rpi4-network-status.init ${D}${sysconfdir}/init.d/rpi4-network-status
}
