#!/usr/bin/env bash
# Guards a release: backend, frontend and the git tag must all state the same
# version. Catches the classic "tagged v0.2.0 but forgot to bump pyproject".
#
# Usage: scripts/check-version.sh v0.2.0
set -euo pipefail

tag="${1:?usage: check-version.sh <tag, e.g. v0.2.0>}"
version="${tag#v}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

backend_version="$(
    sed -n 's/^version = "\(.*\)"/\1/p' "$repo_root/backend/pyproject.toml" | head -1
)"
frontend_version="$(
    sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$repo_root/frontend/package.json" | head -1
)"

status=0

if [ "$backend_version" != "$version" ]; then
    echo "backend/pyproject.toml says '$backend_version', tag says '$version'" >&2
    status=1
fi

if [ "$frontend_version" != "$version" ]; then
    echo "frontend/package.json says '$frontend_version', tag says '$version'" >&2
    status=1
fi

# uv.lock pins the project's own version too, so bumping pyproject.toml alone
# leaves it stale — and CI runs `uv sync --locked`, which refuses to proceed.
# Caught here rather than eight minutes into a release run.
lock_version="$(
    sed -n '/^name = "loregraph"$/,/^version = /s/^version = "\(.*\)"/\1/p' \
        "$repo_root/backend/uv.lock" | head -1
)"

if [ "$lock_version" != "$version" ]; then
    echo "backend/uv.lock says '$lock_version', tag says '$version'" >&2
    echo "  run: cd backend && uv lock" >&2
    status=1
fi

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "Fix the versions, commit, then move the tag before it is pushed." >&2
    exit 1
fi

echo "Version $version is consistent across backend, frontend, uv.lock and tag."
