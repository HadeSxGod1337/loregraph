# Installs @loregraph/private-ui for a local private build.
#
# Why this exists instead of `npm install --no-save git+ssh://...`: that
# command is unreliable on Windows — npm's internal git-clone handling for
# private GitHub repos silently produces an empty temp directory (confirmed
# via `--loglevel silly`, not a guess), independent of SSH auth working fine
# for plain `git`/`uv`. This script does the clone itself with plain `git`
# (proven reliable) and copies the result into node_modules — no npm git
# resolution involved. `git+ssh://...` in Dockerfile.private is left as is:
# that runs on Linux, where this Windows-specific npm behavior may not
# reproduce (untested here, no Docker available in that session).
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/sync-private-ui.ps1

$ErrorActionPreference = "Stop"

$repoUrl = "https://github.com/HadeSxGod1337/loregraph-private.git"
$cacheDir = Join-Path $PSScriptRoot "..\.private-cache\loregraph-private"
$destDir = Join-Path $PSScriptRoot "..\node_modules\@loregraph\private-ui"

if (Test-Path $cacheDir) {
    git -C $cacheDir pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $cacheDir) | Out-Null
    git clone $repoUrl $cacheDir
}

if (Test-Path $destDir) {
    Remove-Item -Recurse -Force $destDir
}
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -Path (Join-Path $cacheDir "frontend\package.json") -Destination $destDir
Copy-Item -Path (Join-Path $cacheDir "frontend\src") -Destination $destDir -Recurse

Write-Host "@loregraph/private-ui synced into node_modules from $cacheDir"
