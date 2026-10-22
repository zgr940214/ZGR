# Minimal tools-only adaptation of meta-openembedded scarthgap:
# https://github.com/openembedded/meta-openembedded/tree/0f00f8b9a21950640da8c5707343e5540133f86e/meta-oe/recipes-support/libgpiod
# Keep the official source and license checksums; omit bindings and ptests.
SUMMARY = "C library and command-line tools for Linux GPIO character devices"
HOMEPAGE = "https://git.kernel.org/pub/scm/libs/libgpiod/libgpiod.git/"
LICENSE = "GPL-2.0-or-later & LGPL-2.1-or-later & CC-BY-SA-4.0"
LIC_FILES_CHKSUM = " \
    file://LICENSES/GPL-2.0-or-later.txt;md5=b234ee4d69f5fce4486a80fdaf4a4263 \
    file://LICENSES/LGPL-2.1-or-later.txt;md5=4b54a1fd55a448865a0b32d41598759d \
    file://LICENSES/CC-BY-SA-4.0.txt;md5=fba3b94d88bfb9b81369b869a1e9a20f \
"

SRC_URI = "https://www.kernel.org/pub/software/libs/libgpiod/libgpiod-${PV}.tar.xz"
SRC_URI[sha256sum] = "2be4c0b03e995d236c0e476e14aeb475d7b431dd1439609b6d65c540f91eaf58"

inherit autotools pkgconfig

DEPENDS = "autoconf-archive-native"
EXTRA_OECONF = " \
    --enable-tools \
    --disable-tests \
    --disable-examples \
    --disable-profiling \
    --disable-bindings-cxx \
    --disable-bindings-python \
    --disable-bindings-rust \
    --disable-gpioset-interactive \
"

PACKAGES =+ "${PN}-tools"
FILES:${PN}-tools = " \
    ${bindir}/gpiodetect \
    ${bindir}/gpioinfo \
    ${bindir}/gpioget \
    ${bindir}/gpioset \
    ${bindir}/gpiomon \
    ${bindir}/gpionotify \
"
