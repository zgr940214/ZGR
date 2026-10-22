#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export DOCKER_CONFIG="$project_root/.docker"
mkdir -p "$DOCKER_CONFIG"
image=rpi4-yocto-build:scarthgap
trust_file=${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}
proxy_args=()
while IFS= read -r host_entry; do
  [ -z "$host_entry" ] || proxy_args+=(--add-host "$host_entry")
done < <(python3 - <<'PY'
import os, socket
from urllib.parse import urlsplit
hosts = {urlsplit(os.environ[name]).hostname for name in
         ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy')
         if os.environ.get(name)}
for host in sorted(hosts):
    print(f'{host}:{socket.gethostbyname(host)}')
PY
)
if [ "${1:-}" = --build ]; then
  docker build "${proxy_args[@]}" \
    --build-arg HTTP_PROXY --build-arg HTTPS_PROXY \
    --build-arg http_proxy --build-arg https_proxy \
    --secret "id=trust,src=$trust_file" \
    --tag "$image" "$project_root/container"
  exit
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  bash "$project_root/scripts/container.sh" --build
fi
mkdir -p "$project_root/.home"
image_tmpfs_gb=${RPI4_IMAGE_TMPFS_GB-12}
if [[ ! "$image_tmpfs_gb" =~ ^[0-9]+$ ]]; then
  echo 'RPI4_IMAGE_TMPFS_GB must be a nonnegative integer (0 disables image tmpfs)' >&2
  exit 2
fi
# Canonicalize decimal input before passing the size to the mount parser.
while [[ ${#image_tmpfs_gb} -gt 1 && "$image_tmpfs_gb" == 0* ]]; do
  image_tmpfs_gb=${image_tmpfs_gb#0}
done
docker_args=(--rm --init --user "$(id -u):$(id -g)"
  --mount "type=bind,src=$project_root,dst=$project_root"
  --mount "type=bind,src=$trust_file,dst=/etc/ssl/certs/ca-certificates.crt,readonly"
  --workdir "$project_root" --env "HOME=$project_root/.home"
  --env SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  --env REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  --env GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt
  --env HTTP_PROXY --env HTTPS_PROXY --env http_proxy --env https_proxy
  --env NO_PROXY --env no_proxy)
if [[ "$image_tmpfs_gb" != 0 ]]; then
  image_tmpfs_root="$project_root/build/tmp/work/raspberrypi4_64-poky-linux/rpi4-debug-image"
  # Create the mountpoint as the caller, rather than letting the daemon create
  # a root-owned directory. Only volatile image scratch lives in this tmpfs;
  # kernel work, packages and deployed compressed outputs remain on disk.
  mkdir -p "$image_tmpfs_root"
  docker_args+=(--tmpfs "$image_tmpfs_root:rw,exec,nosuid,nodev,size=${image_tmpfs_gb}g,mode=0755,uid=$(id -u),gid=$(id -g)")
fi
if [ -t 0 ] && [ -t 1 ]; then docker_args+=(-it); fi
exec docker run "${docker_args[@]}" "${proxy_args[@]}" "$image" "$@"
