#!/usr/bin/env bash
# Prepare a local file:// PREMIRRORS source without cloning Linux history.
# Keep it outside DL_DIR: a failed remote mirror download may clean DL_DIR's
# same-named file before the Git fetcher gets a chance to consume it.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
revision=d8ab4e908235da7727f22dd36ad5af224671677d
branch=rpi-6.12.y
upstream=https://github.com/raspberrypi/linux.git
cache_name=gitshallow_github.com.raspberrypi.linux.git_d8ab4e9-1_rpi-6.12.y.tar.gz
cache_root="$project_root/kernel-source-cache"
archive="$cache_root/$cache_name"
mkdir -p "$cache_root"
exec 9>"$cache_root/.kernel-shallow.lock"
flock 9
staging=$(mktemp -d "$cache_root/.kernel-shallow.XXXXXXXX")
trap 'rm -rf -- "$staging"' EXIT

verify_repository() {
    local repository=$1
    test "$(git -C "$repository" rev-parse --verify "refs/remotes/origin/$branch^{commit}")" = "$revision"
    test "$(git -C "$repository" rev-parse --is-shallow-repository)" = true
    test "$(git -C "$repository" rev-list --all --count)" = 1
    test ! -e "$repository/.git/objects/info/alternates"
    # Verify every tree and blob reachable from the pinned commit. The shallow
    # boundary intentionally excludes earlier commits, without excluding files.
    git -C "$repository" fsck --full --strict --no-reflogs "$revision"
}

verify_archive() {
    local candidate=$1 repository=$2
    mkdir -p "$repository"
    # Inspect before extraction: a standard GitFetcher shallow tar contains a
    # normal .git directory and no checked-out files, links, or external paths.
    python3 - "$candidate" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1], "r:gz") as archive:
    seen_head = False
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit("Unsafe path in kernel shallow archive")
        if path.parts and path.parts[0] != ".git":
            raise SystemExit("Expected a GitFetcher .git archive")
        if not (member.isfile() or member.isdir()):
            raise SystemExit("Links or special files in kernel shallow archive")
        if str(path) == ".git/HEAD" and member.isfile():
            seen_head = True
    if not seen_head:
        raise SystemExit("Missing .git/HEAD in kernel shallow archive")
PY
    tar -xzf "$candidate" -C "$repository"
    verify_repository "$repository"
}

if [ -e "$archive" ]; then
    verify_archive "$archive" "$staging/existing"
    echo "Reusing verified kernel shallow cache: $archive"
else
    git init --quiet --initial-branch="$branch" "$staging/repository"
    git -C "$staging/repository" remote add origin "$upstream"
    git -C "$staging/repository" fetch --progress --depth=1 --no-tags origin \
        "$revision:refs/remotes/origin/$branch"
    git -C "$staging/repository" update-ref "refs/heads/$branch" "$revision"
    test "$(git -C "$staging/repository" rev-parse --verify HEAD)" = "$revision"
    verify_repository "$staging/repository"
    tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 \
        -czf "$staging/$cache_name" -C "$staging/repository" .
    verify_archive "$staging/$cache_name" "$staging/round-trip"
    # A hard link publishes the complete archive atomically without replacing
    # an existing cache. BitBake owns DL_DIR symlinks and completion stamps.
    if ln "$staging/$cache_name" "$archive"; then
        echo "Published verified kernel shallow cache: $archive"
    else
        verify_archive "$archive" "$staging/raced-existing"
        echo "Reusing concurrently published kernel shallow cache: $archive"
    fi
fi
sha256sum "$archive"
wc -c < "$archive"
