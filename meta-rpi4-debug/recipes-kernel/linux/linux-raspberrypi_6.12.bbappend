FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append = " file://full-kernel-debug.cfg"

# Keep the release string and both named Git revisions explicit. Never AUTOREV.
LINUX_VERSION = "6.12.93"
LINUX_RPI_BRANCH = "rpi-6.12.y"
LINUX_RPI_KMETA_BRANCH = "yocto-6.12"
SRCREV_machine = "d8ab4e908235da7727f22dd36ad5af224671677d"
SRCREV_meta = "e66f40994fc740818776a0f3af55e8b6d74bfbef"

# Scope this to the kernel recipe. The rootfs .ko files and deploy archives
# retain full DWARF; normal userspace package handling is unchanged.
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
KERNEL_IMAGE_STRIP_EXTRA_SECTIONS = ""
KERNEL_DEBUG_BUNDLE = "rpi4-kernel-debug-${KERNEL_VERSION}"

do_configure:append() {
    for setting in \
        CONFIG_DEBUG_KERNEL=y CONFIG_DEBUG_INFO=y CONFIG_DEBUG_INFO_DWARF4=y \
        CONFIG_DEBUG_INFO_COMPRESSED_NONE=y CONFIG_GDB_SCRIPTS=y \
        CONFIG_KALLSYMS=y CONFIG_KALLSYMS_ALL=y CONFIG_MODULES=y \
        CONFIG_IKCONFIG=y CONFIG_IKCONFIG_PROC=y; do
        grep -Fqx "$setting" "${B}/.config" || bbfatal "Required kernel setting missing: $setting"
    done
    for option in DEBUG_INFO_REDUCED DEBUG_INFO_SPLIT DEBUG_INFO_NONE MODULE_COMPRESS; do
        if grep -Fqx "CONFIG_$option=y" "${B}/.config"; then
            bbfatal "Incomplete debug information: CONFIG_$option is enabled"
        fi
    done
}

do_compile:append() {
    # The normal recipe builds Image, not the kernel's "all" target. Explicitly
    # generate the GDB helpers and constants for this exact configuration.
    oe_runmake -C "${B}" scripts_gdb
}

do_deploy:append() {
    debugdir="${DEPLOYDIR}/${KERNEL_DEBUG_BUNDLE}"
    install -d "$debugdir"
    install -m 0644 "${B}/vmlinux" "$debugdir/vmlinux"
    install -m 0644 "${B}/System.map" "$debugdir/System.map"
    install -m 0644 "${B}/.config" "$debugdir/kernel.config"
    install -m 0644 "${B}/Module.symvers" "$debugdir/Module.symvers"

    # do_package operates on PKGD, not D, and its stripping/debug split is
    # inhibited above. Thus all packaged, rootfs and archived modules retain
    # symbols even when packaging and deployment run concurrently.
    tar --sort=name --owner=0 --group=0 --numeric-owner \
        --mtime="@${SOURCE_DATE_EPOCH}" -czf "$debugdir/modules-with-debug.tar.gz" \
        -C "${D}" ".${nonarch_base_libdir}/modules"

    # Keep the exact source used for DWARF source lookup, including GDB helpers.
    # Git history and kernel metadata are unnecessary for source debugging.
    tar --sort=name --owner=0 --group=0 --numeric-owner \
        --mtime="@${SOURCE_DATE_EPOCH}" --exclude=.git --exclude=.kernel-meta \
        -czf "$debugdir/kernel-source.tar.gz" -C "${S}" .

    # Out-of-tree helper builds contain absolute symlinks to the source tree.
    # Dereference them into a portable archive, and include the generated
    # constants.py, which does not exist in the pristine source archive.
    gdbdir="$debugdir/.gdb-helper-files"
    install -d "$gdbdir/scripts/gdb"
    cp -rL "${S}/scripts/gdb/." "$gdbdir/scripts/gdb/"
    install -m 0644 "${B}/scripts/gdb/linux/constants.py" "$gdbdir/scripts/gdb/linux/constants.py"
    install -m 0644 "${S}/scripts/gdb/vmlinux-gdb.py" "$gdbdir/vmlinux-gdb.py"
    tar --sort=name --owner=0 --group=0 --numeric-owner \
        --mtime="@${SOURCE_DATE_EPOCH}" -czf "$debugdir/gdb-scripts.tar.gz" -C "$gdbdir" .
    rm -rf "$gdbdir"

    cat > "$debugdir/build-metadata.json" <<-EOF
	{
	  "machine": "${MACHINE}",
	  "linux_version": "${LINUX_VERSION}",
	  "kernel_release": "${KERNEL_VERSION}",
	  "srcrev_machine": "${SRCREV_machine}",
	  "srcrev_meta": "${SRCREV_meta}",
	  "dwarf_version": 4,
	  "modules_stripped": false,
	  "source_debug_prefix": "${KERNEL_SRC_PATH}"
	}
	EOF
    (
        cd "$debugdir"
        sha256sum vmlinux System.map kernel.config Module.symvers \
            modules-with-debug.tar.gz kernel-source.tar.gz gdb-scripts.tar.gz build-metadata.json \
            > SHA256SUMS
    )
    ln -sfn "${KERNEL_DEBUG_BUNDLE}" "${DEPLOYDIR}/rpi4-kernel-debug"
}
