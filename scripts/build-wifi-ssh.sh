#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
mkdir -p logs
run_id=$(date -u +%Y%m%dT%H%M%SZ)
printf '%s\n' "$run_id" > logs/wifi-ssh-current-run.txt
export RPI4_IMAGE_TMPFS_GB=${RPI4_IMAGE_TMPFS_GB-0}
bash scripts/bitbake.sh -c install virtual/kernel 2>&1 | tee "logs/wifi-ssh-kernel-install-$run_id.log"
python3 scripts/prune-kernel-objects.py 2>&1 | tee "logs/wifi-ssh-kernel-objects-$run_id.log"
bash scripts/bitbake.sh rpi4-boot-rcu-wifi-image 2>&1 | tee "logs/wifi-ssh-build-$run_id.log"
python3 scripts/verify-wifi-ssh-artifacts.py 2>&1 | tee "logs/wifi-ssh-artifacts-$run_id.log"
