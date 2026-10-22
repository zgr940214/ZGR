require recipes-core/images/core-image-minimal.bb

SUMMARY = "Raspberry Pi 4 developer image with complete kernel module symbols"
DESCRIPTION = "Bootable 64-bit Raspberry Pi 4 image with OpenSSH, gdbserver, and all kernel modules retaining their full DWARF symbols. The matching unstripped vmlinux and source archive are deployed alongside the image."
COMPATIBLE_MACHINE = "^raspberrypi4-64$"

IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_INSTALL:append = " kernel-modules gdbserver"

# Provision a password or SSH public key separately before remote login.
# Do not strip the rootfs modules; the requested image retains full symbols.

# Keep the bootable compressed image and its matching bmap, without publishing
# another multi-gigabyte uncompressed WIC when that format was not requested.
# do_image_complete is Python; register this shell function through its hook.
IMAGE_POSTPROCESS_COMMAND:append = " rpi4_discard_raw_wic;"

rpi4_discard_raw_wic() {
    case " ${IMAGE_FSTYPES} " in
        *" wic "*) return 0 ;;
    esac
    if [ -s "${IMGDEPLOYDIR}/${IMAGE_NAME}.wic.bz2" ] && \
       [ -s "${IMGDEPLOYDIR}/${IMAGE_NAME}.wic.bmap" ]; then
        rm -f "${IMGDEPLOYDIR}/${IMAGE_NAME}.wic"
    fi
}
