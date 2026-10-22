#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
mkdir -p logs
run_id=$(date -u +%Y%m%dT%H%M%SZ)
printf '%s\n' "$run_id" > logs/boot-rcu-current-run.txt
# This small image uses disk scratch. The original full image's tmpfs is not
# needed; users can still override the container setting explicitly.
export RPI4_IMAGE_TMPFS_GB=${RPI4_IMAGE_TMPFS_GB-0}
bash scripts/bitbake.sh -c install virtual/kernel 2>&1 | tee "logs/boot-rcu-kernel-install-$run_id.log"
python3 scripts/prune-kernel-objects.py 2>&1 | tee "logs/boot-rcu-kernel-objects-$run_id.log"
bash scripts/bitbake.sh rpi4-boot-rcu-image 2>&1 | tee "logs/boot-rcu-build-$run_id.log"
python3 scripts/verify-boot-rcu-artifacts.py 2>&1 | tee "logs/boot-rcu-artifacts-$run_id.log"
