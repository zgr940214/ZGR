#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
mkdir -p logs
run_id=$(date -u +%Y%m%dT%H%M%SZ)
df -h "$project_root"
bash scripts/bitbake.sh -c install virtual/kernel 2>&1 | tee "logs/kernel-install-$run_id.log"
python3 scripts/prune-kernel-objects.py 2>&1 | tee "logs/kernel-objects-$run_id.log"
bash scripts/container.sh bash -c '
  set -e
  image_run_id=$1
  project_root=$PWD
  preserve_image_task_logs() {
    local original_status=$?
    local image_work="$project_root/build/tmp/work/raspberrypi4_64-poky-linux/rpi4-debug-image"
    local log_root="$project_root/logs/image-tasks-$image_run_id"
    local task_temp version_dir version
    trap - EXIT
    # Preserve only task logs from volatile image WORKDIR, never rootfs or
    # image payloads. Log-copy errors must not replace the BitBake exit status.
    if mkdir -p "$log_root"; then
      shopt -s nullglob
      for task_temp in "$image_work"/*/temp; do
        [ -d "$task_temp" ] || continue
        version_dir=${task_temp%/temp}
        version=${version_dir##*/}
        if mkdir -p "$log_root/$version"; then
          if ! cp -a "$task_temp" "$log_root/$version/"; then
            echo "Could not preserve image task logs: $task_temp" >&2
          fi
        else
          echo "Could not create image task log directory: $log_root/$version" >&2
        fi
      done
    else
      echo "Could not create persistent image task log directory: $log_root" >&2
    fi
    exit "$original_status"
  }
  trap preserve_image_task_logs EXIT
  source sources/poky/oe-init-build-env build >/dev/null
  # Image WORKDIR is volatile tmpfs. Discard its old task stamps before every
  # image invocation, then build inside this same container and mount.
  bitbake -c clean rpi4-debug-image
  bitbake rpi4-debug-image
' rpi4-image "$run_id" 2>&1 | tee "logs/build-$run_id.log"
python3 scripts/verify-artifacts.py build/tmp/deploy/images/raspberrypi4-64 \
  2>&1 | tee "logs/artifacts-$run_id.log"
