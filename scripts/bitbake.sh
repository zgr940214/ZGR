#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$project_root/scripts/container.sh" bash -c '
  set -e
  source sources/poky/oe-init-build-env build >/dev/null
  exec bitbake "$@"
' bitbake "$@"
