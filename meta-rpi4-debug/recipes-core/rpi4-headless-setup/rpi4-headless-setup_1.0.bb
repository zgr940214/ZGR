SUMMARY = "Import network and SSH access from the Raspberry Pi FAT boot partition"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://rpi4-headless-setup \
           file://rpi4-headless-setup.init \
           file://network-config \
           file://authorized_keys.example \
           file://userconf.txt.example \
           file://README-SETUP.txt"
S = "${WORKDIR}"

inherit update-rc.d deploy
INITSCRIPT_NAME = "rpi4-headless-setup"
# rcS runs entirely before rc2-5 networking S01 and sshd S09. Run after
# mountall S03 and volatile-directory setup S37 so rootfs and /run are ready.
INITSCRIPT_PARAMS = "start 39 S ."
RDEPENDS:${PN} = "busybox openssh-keygen"
FILES:${PN} += "${datadir}/rpi4-setup"

BOOT_SETUP_TEMPLATES = "network-config authorized_keys.example userconf.txt.example README-SETUP.txt"

do_install() {
    install -d ${D}${sbindir} ${D}${sysconfdir}/init.d ${D}${datadir}/rpi4-setup
    install -m 0755 ${WORKDIR}/rpi4-headless-setup ${D}${sbindir}/rpi4-headless-setup
    install -m 0755 ${WORKDIR}/rpi4-headless-setup.init ${D}${sysconfdir}/init.d/rpi4-headless-setup
    for name in ${BOOT_SETUP_TEMPLATES}; do
        install -m 0644 ${WORKDIR}/$name ${D}${datadir}/rpi4-setup/$name
    done
}

do_deploy() {
    install -d ${DEPLOYDIR}/rpi4-headless-bootfiles
    for name in ${BOOT_SETUP_TEMPLATES}; do
        install -m 0644 ${WORKDIR}/$name ${DEPLOYDIR}/rpi4-headless-bootfiles/$name
    done
}
addtask deploy after do_install before do_build
