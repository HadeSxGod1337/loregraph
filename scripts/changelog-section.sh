#!/usr/bin/env bash
# Prints the CHANGELOG section for one version, to be used as release notes.
# Fails when the section is missing, so a release can never ship empty notes.
#
# Usage: scripts/changelog-section.sh v0.2.0
set -euo pipefail

tag="${1:?usage: changelog-section.sh <tag, e.g. v0.2.0>}"
version="${tag#v}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
changelog="$repo_root/CHANGELOG.md"

section="$(
    awk -v ver="$version" '
        # Section starts at "## [<version>]" and ends at the next heading, or at
        # the trailing block of link definitions when this is the oldest section.
        $0 ~ "^## \\[" ver "\\]"     { found = 1; next }
        found && /^## /              { exit }
        found && /^\[[^]]+\]: http/  { exit }
        found                        { print }
    ' "$changelog"
)"

# Strip leading and trailing blank lines.
section="$(printf '%s\n' "$section" | sed -e '/./,$!d' -e ':a' -e '/^\n*$/{$d;N;ba' -e '}')"

if [ -z "$section" ]; then
    echo "No '## [$version]' section found in CHANGELOG.md" >&2
    exit 1
fi

printf '%s\n' "$section"
