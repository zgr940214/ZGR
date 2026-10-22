#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
clone_pinned() {
  local url=$1 dest=$2 revision=$3
  if [ ! -e "$dest" ]; then
    git clone --depth 1 --no-checkout --branch scarthgap "$url" "$dest"
    if [ "$(git -C "$dest" rev-parse HEAD)" != "$revision" ]; then
      git -C "$dest" fetch --depth 1 origin "$revision"
    fi
    git -C "$dest" checkout --detach "$revision"
  fi
  if [ "$(git -C "$dest" rev-parse HEAD)" != "$revision" ]; then
    echo "Existing $dest is not at the pinned revision; preserving its local history and changes." >&2
    exit 1
  fi
}
clone_pinned https://github.com/yoctoproject/poky.git sources/poky 104772c5fd0653290cbb5e4b77813343957939cc
clone_pinned https://github.com/agherzan/meta-raspberrypi.git sources/meta-raspberrypi 018d44467c4f09eb63f8ea5e86e85d755250cf89
bash scripts/prefetch-kernel.sh
mkdir -p build/conf
for name in bblayers.conf local.conf; do
  if [ ! -e "build/conf/$name" ]; then
    ln -s "../../conf/$name" "build/conf/$name"
  fi
done
bash scripts/container.sh --build
