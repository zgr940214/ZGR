require recipes-core/images/core-image-minimal.bb

SUMMARY = "Minimal Raspberry Pi 4 image for built-in kernel boot and RCU debugging"
DESCRIPTION = "Uses the existing pinned full-DWARF kernel with a small init and shell rootfs. Runtime kernel module packages, Wi-Fi firmware, OpenSSH and gdbserver are not installed by this image. Boot and serial-console support come from built-in kernel drivers."
COMPATIBLE_MACHINE = "^raspberrypi4-64$"

# The BSP recommends every kernel module and wireless firmware. The focused
# image deliberately installs only the hard dependencies of core-image-minimal.
NO_RECOMMENDATIONS = "1"
# Serial-console study image: permit a local root login with an empty password.
# No SSH server or other remote-login service is added here.
IMAGE_FEATURES = "allow-empty-password empty-root-password"
IMAGE_FSTYPES = "wic.xz wic.bmap tar.bz2"

# The final compressed images persist in DEPLOY_DIR_IMAGE; avoid storing a
# second image-complete cache copy on this small cloud filesystem.
SSTATE_SKIP_CREATION:task-image-complete = "1"
