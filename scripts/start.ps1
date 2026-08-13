# Loregraph one-click launcher for non-developers.
# Installs missing tools (uv, Node.js), pulls updates, installs dependencies,
# asks for an API key on first run, starts backend + frontend, opens the browser.
# Run via start.bat in the repo root (double-click).

param(
    [switch]$SkipUpdate,
    # Re-run the first-launch AI provider wizard without deleting .env.
    [switch]$ConfigureAI,
    # Reveal unsupported providers. They remain hidden during normal setup.
    [switch]$ExperimentalProviders,
    # LAN play mode: bind to all interfaces so players on the same network can
    # reach the app through an invite link. Off by default — the app stays on
    # localhost, exactly as before.
    [switch]$Lan,
    [string]$LanHost = "",
    # Internet mode: LAN plus asking the router (over UPnP) to forward the port,
    # so players outside the local network can connect. Implies -Lan.
    [switch]$Internet
)

$ErrorActionPreference = "Stop"
# Three different encodings matter here, and missing any one gives mojibake:
#   OutputEncoding (console)  - how native command output is DECODED
#   $OutputEncoding           - how text piped INTO native commands is encoded
#   UTF8Encoding($false)      - how we WRITE files the bash launcher also reads
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
# One process serves both the interface and the API, so there is a single port
# to allow through a firewall or forward on a router.
$AppPort = 8000
# Scheme follows the TLS settings; filled in once .env has been read below.
$AppScheme = "http"
$LocalUrl = "http://127.0.0.1:$AppPort"
# Where players connect; only differs from $LocalUrl in LAN mode.
$FrontendUrl = $LocalUrl
# uvicorn runs with backend/ as its working directory, so Settings.data_dir
# ("./data") resolves HERE - not at the repo root. The backend reads the same
# update files (see backend/src/loregraph/services/update_status.py).
$DataDir = Join-Path $Backend "data"
# How often the background loop checks the git remote for updates (seconds).
$UpdateCheckInterval = 600
# How long the update prompt waits before assuming "later". Double-clicking
# start.bat has always been unattended; a prompt that blocks forever would
# break that, so an unanswered question just continues without updating.
$UpdatePromptTimeout = 30

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Select-LiveModel([object[]]$models, [string]$purpose) {
    $available = @($models | ForEach-Object { "$($_)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
    if ($available.Count -eq 0) { throw "Провайдер не вернул ни одной доступной модели." }
    Write-Host ""
    Write-Host "    Доступные модели для ${purpose}:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $available.Count; $i++) {
        Write-Host ("      {0,2} - {1}" -f ($i + 1), $available[$i])
    }
    while ($true) {
        $raw = (Read-Host "    Выберите номер (Enter = 1)").Trim()
        if ([string]::IsNullOrWhiteSpace($raw)) { return $available[0] }
        $number = 0
        if ([int]::TryParse($raw, [ref]$number) -and $number -ge 1 -and $number -le $available.Count) {
            return $available[$number - 1]
        }
        Write-Warn2 "Введите номер от 1 до $($available.Count)."
    }
}

function Get-ChatGptAccountId([string]$accessToken) {
    try {
        $part = $accessToken.Split('.')[1].Replace('-', '+').Replace('_', '/')
        while (($part.Length % 4) -ne 0) { $part += "=" }
        $claims = ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part))) | ConvertFrom-Json
        return $claims.'https://api.openai.com/auth'.chatgpt_account_id
    } catch { return $null }
}

function Connect-OpenAICodex([string]$oauthPath) {
    $issuer = "https://auth.openai.com"
    $clientId = "app_EMoamEEZ73f0CkXaXp7hrann"
    Write-Host ""
    Write-Warn2 "Экспериментальный режим: OpenAI официально не публикует этот Codex OAuth API."
    $device = Invoke-RestMethod -Method Post `
        -Uri "$issuer/api/accounts/deviceauth/usercode" `
        -ContentType "application/json" `
        -Body (@{ client_id = $clientId } | ConvertTo-Json)
    if (-not $device.user_code -or -not $device.device_auth_id) {
        throw "OpenAI вернул неполный код авторизации."
    }
    $verificationUrl = "$issuer/codex/device"
    Write-Host "    Откроется страница OpenAI. Введите код: $($device.user_code)" -ForegroundColor Green
    Start-Process $verificationUrl
    $interval = 5
    if ($device.interval) { $interval = [Math]::Max(3, [int]$device.interval) }
    $deadline = (Get-Date).AddMinutes(15)
    $authorization = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $interval
        try {
            $authorization = Invoke-RestMethod -Method Post `
                -Uri "$issuer/api/accounts/deviceauth/token" `
                -ContentType "application/json" `
                -Body (@{ device_auth_id = $device.device_auth_id; user_code = $device.user_code } | ConvertTo-Json)
            break
        } catch {
            $status = $_.Exception.Response.StatusCode.value__
            if ($status -notin 403, 404) { throw }
        }
    }
    if ($null -eq $authorization) { throw "Время ожидания входа в ChatGPT истекло." }
    $tokens = Invoke-RestMethod -Method Post `
        -Uri "$issuer/oauth/token" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{
            grant_type = "authorization_code"
            code = $authorization.authorization_code
            redirect_uri = "$issuer/deviceauth/callback"
            client_id = $clientId
            code_verifier = $authorization.code_verifier
        }
    if (-not $tokens.access_token -or -not $tokens.refresh_token) {
        throw "OpenAI не вернул полный комплект OAuth-токенов."
    }
    $oauthDir = Split-Path -Parent $oauthPath
    if (-not (Test-Path $oauthDir)) { New-Item -ItemType Directory -Force $oauthDir | Out-Null }
    $oauthJson = @{ tokens = $tokens } | ConvertTo-Json -Depth 8 -Compress
    [IO.File]::WriteAllText($oauthPath, $oauthJson, $Utf8NoBom)

    $headers = @{
        Authorization = "Bearer $($tokens.access_token)"
        originator = "codex_cli_rs"
        "User-Agent" = "codex_cli_rs/0.0.0 (Loregraph experimental)"
    }
    $accountId = Get-ChatGptAccountId $tokens.access_token
    if ($accountId) { $headers["ChatGPT-Account-ID"] = $accountId }
    $catalog = Invoke-RestMethod -Method Get `
        -Uri "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0" `
        -Headers $headers
    $ranked = @($catalog.models | Where-Object {
        $_.slug -and "$($_.visibility)".ToLowerInvariant() -notin @("hide", "hidden")
    } | Sort-Object @{ Expression = {
        if ($null -ne $_.priority) { [int]$_.priority } else { 10000 }
    }}, slug)
    $models = @($ranked | ForEach-Object { $_.slug } | Select-Object -Unique)
    if ($models.Count -eq 0) {
        throw "Авторизация успешна, но ChatGPT не вернул доступных этому аккаунту моделей."
    }
    Write-Ok "Вход в ChatGPT выполнен; получен живой каталог из $($models.Count) моделей."
    return $models
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Test-Command($name) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    return ($null -ne $found)
}

function Get-LocalAddressToward($target) {
    # A connected UDP socket sends nothing — it only resolves which local
    # address the OS would use to reach `target`.
    try {
        $sock = New-Object System.Net.Sockets.Socket(
            [System.Net.Sockets.AddressFamily]::InterNetwork,
            [System.Net.Sockets.SocketType]::Dgram,
            [System.Net.Sockets.ProtocolType]::Udp)
        try {
            $sock.Connect($target, 80)
            return $sock.LocalEndPoint.Address.IPAddressToString
        } finally { $sock.Close() }
    } catch { return $null }
}

function Get-PrimaryLanIp {
    # The address players on this network can reach us at.
    #
    # Deliberately NOT "the address that reaches the internet": a VPN or a
    # virtual adapter routinely owns that route, and its address is invisible
    # to everyone else in the house. What we want is the address facing the
    # real router, so we rank the default routes the way Windows does —
    # RouteMetric + InterfaceMetric, lowest wins — and ask the OS which local
    # address reaches that route's gateway. An adapter with no interface metric
    # is pushed to the back: those are the virtual ones.
    try {
        $best = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop |
            Where-Object { $_.NextHop -and $_.NextHop -ne "0.0.0.0" } |
            Sort-Object -Property @{ Expression = {
                $ifMetric = if ($null -eq $_.InterfaceMetric -or "" -eq "$($_.InterfaceMetric)") { 10000 }
                            else { [int]$_.InterfaceMetric }
                [int]$_.RouteMetric + $ifMetric
            }} |
            Select-Object -First 1
        if ($null -ne $best) {
            $local = Get-LocalAddressToward $best.NextHop
            if (-not [string]::IsNullOrWhiteSpace($local) -and $local -ne "0.0.0.0") {
                return $local
            }
        }
    } catch {}

    # Last resort: whatever address reaches the wider internet.
    return Get-LocalAddressToward "8.8.8.8"
}

function Get-LanIpCandidates {
    # Only used to help when auto-detection fails.
    $addrs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.PrefixOrigin -in 'Dhcp', 'Manual' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.IPAddress -ne '127.0.0.1'
        }
    return @($addrs | Select-Object -ExpandProperty IPAddress)
}

# --- Update preferences and status (shared with the backend) -----------------
# Flat key=value files, not JSON: this runs BEFORE uv and Node are installed,
# so neither Python nor jq is guaranteed to exist, and scripts/start.sh has to
# parse the very same files with plain POSIX tools. The changelog lives in its
# own file so neither shell ever has to escape multi-line markdown.

function Write-FileAtomic($path, $text) {
    $dir = Split-Path -Parent $path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $tmp = "$path.tmp"
    [System.IO.File]::WriteAllText($tmp, $text, $Utf8NoBom)
    # Rename, so a reader never sees a half-written file.
    Move-Item -LiteralPath $tmp -Destination $path -Force
}

function Read-KeyValueFile($path) {
    $map = @{}
    if (-not (Test-Path $path)) { return $map }
    try { $lines = [System.IO.File]::ReadAllLines($path) } catch { return $map }
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $sep = $trimmed.IndexOf("=")
        if ($sep -lt 1) { continue }
        $map[$trimmed.Substring(0, $sep).Trim()] = $trimmed.Substring($sep + 1).Trim()
    }
    return $map
}

function Read-UpdatePrefs {
    $map = Read-KeyValueFile (Join-Path $DataDir "update.conf")
    $mode = "ask"
    if ($map.ContainsKey("mode") -and @("ask", "auto", "never") -contains $map["mode"]) {
        $mode = $map["mode"]
    }
    $skipped = @()
    if ($map.ContainsKey("skipped_versions")) {
        $skipped = @($map["skipped_versions"] -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
    }
    return @{ mode = $mode; skipped = $skipped }
}

function Write-UpdatePrefs($mode, $skipped) {
    $text = "# Loregraph update preferences.`n" +
            "# Edit here or in the app (sidebar -> preferences -> updates).`n" +
            "# mode: ask | auto | never`n" +
            "mode=$mode`n" +
            "skipped_versions=$($skipped -join ',')`n"
    Write-FileAtomic (Join-Path $DataDir "update.conf") $text
}

function Write-UpdateStatus($gitAvailable, $dirty, $current, $latest, $changelog) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $text = "git_available=$gitAvailable`n" +
            "worktree_dirty=$dirty`n" +
            "current_version=$current`n" +
            "latest_version=$latest`n" +
            "checked_at=$stamp`n"
    Write-FileAtomic (Join-Path $DataDir "update-status.conf") $text
    $changelogPath = Join-Path $DataDir "update-changelog.md"
    if ([string]::IsNullOrWhiteSpace($changelog)) {
        if (Test-Path $changelogPath) { Remove-Item $changelogPath -Force }
    } else {
        Write-FileAtomic $changelogPath $changelog
    }
}

function Get-LocalVersion {
    $tomlPath = Join-Path $Backend "pyproject.toml"
    if (-not (Test-Path $tomlPath)) { return "" }
    $toml = [System.IO.File]::ReadAllText($tomlPath)
    if ($toml -match '(?m)^version = "([^"]+)"') { return $Matches[1] }
    return ""
}

function Get-RemoteVersion($ref) {
    # --no-pager: without it git may hand the output to `less` and hang.
    $toml = (git --no-pager show "${ref}:backend/pyproject.toml") -join "`n"
    if ($toml -match '(?m)^version = "([^"]+)"') { return $Matches[1] }
    return ""
}

# Same extraction as scripts/changelog-section.sh, reimplemented because bash
# is not guaranteed on Windows (winget's MinGit ships none). Keep the two in
# sync if the CHANGELOG heading format ever changes.
function Get-ChangelogSection([string]$text, [string]$targetVersion) {
    if ([string]::IsNullOrWhiteSpace($text) -or [string]::IsNullOrWhiteSpace($targetVersion)) { return "" }
    $collected = New-Object System.Collections.Generic.List[string]
    $found = $false
    foreach ($line in ($text -split "`r?`n")) {
        if (-not $found) {
            if ($line -match ('^## \[' + [regex]::Escape($targetVersion) + '\]')) { $found = $true }
            continue
        }
        if ($line -match '^## ') { break }
        if ($line -match '^\[[^\]]+\]: http') { break }
        $collected.Add($line)
    }
    return ($collected -join "`n").Trim()
}

function Show-ChangelogPreview([string]$section) {
    if ([string]::IsNullOrWhiteSpace($section)) { return }
    $lines = $section -split "`n"
    $limit = 25
    foreach ($line in ($lines | Select-Object -First $limit)) {
        Write-Host "      $line" -ForegroundColor Gray
    }
    if ($lines.Count -gt $limit) {
        Write-Host "      ... ещё $($lines.Count - $limit) строк, полный список - в CHANGELOG.md" -ForegroundColor DarkGray
    }
}

# Digits, not letters: a Russian keyboard layout can't type [Y]/[N] or [О]/[П]
# without switching, and the whole point is that this is one keypress.
function Read-ChoiceWithTimeout([string[]]$valid, [string]$enterChoice, [string]$timeoutChoice) {
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        # Non-interactive (scheduled task, piped stdin): never block.
        return $timeoutChoice
    }
    $deadline = (Get-Date).AddSeconds($UpdatePromptTimeout)
    $shown = -1
    try {
        while ($true) {
            $left = [int][Math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
            if ($left -le 0) { Write-Host ""; return $timeoutChoice }
            if ($left -ne $shown) {
                Write-Host ("`r    Ваш выбор ($($valid -join '/'), Enter = $enterChoice), автоматически через $left с... ") -NoNewline -ForegroundColor Cyan
                $shown = $left
            }
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq "Enter") { Write-Host ""; return $enterChoice }
                $char = ([string]$key.KeyChar)
                if ($valid -contains $char) { Write-Host ""; return $char }
            }
            Start-Sleep -Milliseconds 150
        }
    } catch {
        # No real console behind the host - behave as if nobody answered.
        return $timeoutChoice
    }
}

# --- 1. Git update (skipped for zip downloads without .git) -----------------

$hasGit = (Test-Path (Join-Path $Root ".git")) -and (Test-Command "git")
$localVersion = Get-LocalVersion

if (-not $hasGit) {
    # Zip install or no git binary: say so instead of letting the app claim
    # everything is up to date.
    Write-UpdateStatus 0 0 $localVersion "" ""
}

if (-not $SkipUpdate -and $hasGit) {
    $prefs = Read-UpdatePrefs
    if ($prefs.mode -eq "never") {
        Write-Ok "Проверка обновлений выключена в настройках."
    } else {
        Write-Step "Проверяю обновления проекта..."
        Push-Location $Root
        try {
            cmd /c "git fetch --quiet 2>nul"
            $local = git rev-parse HEAD
            # --verify --quiet: empty output instead of stderr noise when no upstream
            $remote = git rev-parse --verify --quiet '@{u}'
            if ([string]::IsNullOrWhiteSpace($remote) -or $local -eq $remote) {
                Write-UpdateStatus 1 0 $localVersion $localVersion ""
                Write-Ok "Проект актуален."
            } else {
                $upstream = git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
                $latestVersion = Get-RemoteVersion $upstream
                # The new section only exists in the REMOTE changelog.
                $remoteChangelog = (git --no-pager show "${upstream}:CHANGELOG.md") -join "`n"
                $section = Get-ChangelogSection $remoteChangelog $latestVersion
                $dirty = git status --porcelain
                $isDirty = -not [string]::IsNullOrWhiteSpace($dirty)
                Write-UpdateStatus 1 ([int]$isDirty) $localVersion $latestVersion $section

                if ($prefs.skipped -contains $latestVersion) {
                    Write-Ok "Доступна версия $latestVersion, но вы её пропустили."
                } elseif ($prefs.mode -eq "auto") {
                    if ($isDirty) {
                        Write-Warn2 "Есть обновление, но у вас локальные изменения - пропускаю git pull."
                    } else {
                        Write-Warn2 "Найдено обновление $latestVersion, скачиваю..."
                        git pull --ff-only --quiet
                        Write-UpdateStatus 1 0 $latestVersion $latestVersion ""
                        Write-Ok "Проект обновлён."
                    }
                } else {
                    Write-Host ""
                    if ([string]::IsNullOrWhiteSpace($latestVersion)) {
                        Write-Warn2 "Доступно обновление Loregraph."
                    } else {
                        Write-Warn2 "Доступна версия $latestVersion (у вас $localVersion). Что нового:"
                        Show-ChangelogPreview $section
                    }
                    Write-Host ""
                    if ($isDirty) {
                        Write-Warn2 "Обновиться сейчас нельзя: в папке проекта есть ваши изменения."
                        Write-Host "      Сохраните или отмените их (git status), потом запустите снова." -ForegroundColor Gray
                        Write-Host "      [2] Позже   [3] Больше не предлагать эту версию" -ForegroundColor White
                        $answer = Read-ChoiceWithTimeout @("2", "3") "2" "2"
                    } else {
                        Write-Host "      [1] Обновить сейчас   [2] Позже   [3] Больше не предлагать эту версию" -ForegroundColor White
                        $answer = Read-ChoiceWithTimeout @("1", "2", "3") "1" "2"
                    }
                    if ($answer -eq "1") {
                        Write-Warn2 "Обновляю..."
                        git pull --ff-only --quiet
                        Write-UpdateStatus 1 0 $latestVersion $latestVersion ""
                        Write-Ok "Проект обновлён до $latestVersion."
                    } elseif ($answer -eq "3" -and -not [string]::IsNullOrWhiteSpace($latestVersion)) {
                        Write-UpdatePrefs $prefs.mode (@($prefs.skipped) + $latestVersion)
                        Write-Ok "Версия $latestVersion больше не будет предлагаться."
                    } else {
                        Write-Ok "Хорошо, обновимся позже."
                    }
                }
            }
        } catch {
            Write-Warn2 "Не удалось проверить обновления (нет сети?), продолжаю."
        } finally {
            Pop-Location
        }
    }
}

# --- 2. Tools: uv and Node.js ------------------------------------------------

# Say what this is about to download, and where, BEFORE downloading it. The
# install is roughly a gigabyte and only part of it lands in the project folder
# — the rest goes into per-user caches the person running this has no reason to
# expect. Finding that out afterwards, from the free-space counter, is how you
# get someone asking where their disk went.
$FirstInstall = -not (Test-Path (Join-Path $Backend ".venv")) -or
                -not (Test-Path (Join-Path $Frontend "node_modules"))
if ($FirstInstall) {
    Write-Step "Первая установка: что будет скачано"
    Write-Host "    В папку проекта (удаляется вместе с ней):" -ForegroundColor Gray
    Write-Host "         ~490 МБ  зависимости бэкенда (backend\.venv)" -ForegroundColor DarkGray
    Write-Host "         ~140 МБ  зависимости фронтенда (frontend\node_modules)" -ForegroundColor DarkGray
    Write-Host "         ~240 МБ  модель для поиска по лору (backend\data\models)" -ForegroundColor DarkGray
    Write-Host "    Вне папки проекта, общее для всех проектов на этой машине:" -ForegroundColor Gray
    Write-Host "                  кэши uv и npm (%LOCALAPPDATA%)" -ForegroundColor DarkGray
    if (-not (Test-Command "uv")) {
        Write-Host "                  uv (%USERPROFILE%\.local\bin)" -ForegroundColor DarkGray
    }
    if (-not (Test-Command "npm")) {
        Write-Host "                  Node.js LTS (через winget, в Program Files)" -ForegroundColor DarkGray
    }
    Write-Host "    Итого около 1 ГБ. Удалить всё это потом: uninstall.bat" -ForegroundColor Gray
    # Enter continues: double-clicking start.bat has always been the unattended
    # path, and this is a notice, not a gate. Saying no exits cleanly.
    $answer = Read-Host "    Продолжить? [Д/н]"
    if (-not [string]::IsNullOrWhiteSpace($answer) -and $answer -notmatch '^(д|y)') {
        Write-Host ""
        Write-Ok "Установка отменена, ничего не скачано."
        exit 0
    }
}

Write-Step "Проверяю инструменты..."

if (-not (Test-Command "uv")) {
    Write-Warn2 "uv не найден, устанавливаю..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    Update-SessionPath
    if (-not (Test-Command "uv")) {
        throw "Не удалось установить uv. Установите вручную: https://docs.astral.sh/uv/"
    }
}
Write-Ok "uv: $(uv --version)"

if (-not (Test-Command "npm")) {
    Write-Warn2 "Node.js не найден, устанавливаю через winget..."
    winget install --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    Update-SessionPath
    if (-not (Test-Command "npm")) {
        throw "Не удалось установить Node.js. Установите вручную с https://nodejs.org и запустите скрипт снова."
    }
}
Write-Ok "Node.js: $(node --version), npm: $(npm --version)"

# --- 3. API key (.env) on first run ------------------------------------------

$EnvFile = Join-Path $Backend ".env"
$hadEnvFile = Test-Path $EnvFile
if (-not $hadEnvFile -or $ConfigureAI) {
    Write-Step "Первый запуск: настройка AI-ассистента (необязательно)"
    if ($hadEnvFile) {
        Write-Warn2 "Повторная настройка: текущий .env будет сохранён перед заменой."
    }
    Write-Host "    Без AI редактор мира работает полностью, не будет только AI-ассистента." -ForegroundColor Gray
    Write-Host ""
    Write-Host "      1  - Anthropic / Claude (рекомендуется)"
    Write-Host "      2  - OpenAI"
    Write-Host "      3  - Google Gemini (бесплатный tier)"
    Write-Host "      4  - Mistral"
    Write-Host "      5  - DeepSeek (дешёвый, сильный)"
    Write-Host "      6  - Groq (ультра-быстрый)"
    Write-Host "      7  - xAI / Grok"
    Write-Host "      8  - OpenRouter (агрегатор: 100+ моделей)"
    Write-Host "      9  - Cohere"
    Write-Host "      10 - Together AI"
    Write-Host "      11 - Fireworks AI"
    Write-Host "      12 - Cerebras (быстрый инференс)"
    Write-Host "      13 - Perplexity"
    Write-Host "      14 - Nebius"
    Write-Host "      15 - Ollama (локальные модели, без ключа)"
    if ($ExperimentalProviders) {
        Write-Host "      16 - ChatGPT / Codex OAuth (НЕПОДДЕРЖИВАЕМЫЙ эксперимент)" -ForegroundColor Yellow
    }
    Write-Host "      Enter - пропустить: провайдер, ключ и модели настраиваются в самом приложении (Настройки ИИ)"
    Write-Host ""
    $choice = (Read-Host "    Выберите провайдера (номер или Enter)").Trim()

    # $null = skip and copy .env.example instead.
    $envLines = $null
    switch ($choice) {
        "1" {
            $key = (Read-Host "    Вставьте Anthropic API ключ (sk-ant-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @("CAMPAIGN_ANTHROPIC_API_KEY=$key")
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "2" {
            $key = (Read-Host "    Вставьте OpenAI API ключ (sk-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=openai",
                    "CAMPAIGN_OPENAI_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=gpt-4o-mini",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=gpt-4o-mini",
                    "CAMPAIGN_LLM_MODEL_GENERATION=gpt-4o"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "3" {
            $key = (Read-Host "    Вставьте Google API ключ (AIza...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=google",
                    "CAMPAIGN_GOOGLE_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=gemini-2.0-flash",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=gemini-2.0-flash",
                    "CAMPAIGN_LLM_MODEL_GENERATION=gemini-2.5-pro-preview-05-06"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "4" {
            $key = (Read-Host "    Вставьте Mistral API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=mistral",
                    "CAMPAIGN_MISTRAL_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=mistral-small-latest",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=mistral-small-latest",
                    "CAMPAIGN_LLM_MODEL_GENERATION=mistral-large-latest"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "5" {
            $key = (Read-Host "    Вставьте DeepSeek API ключ (sk-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=deepseek",
                    "CAMPAIGN_DEEPSEEK_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=deepseek-chat",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=deepseek-chat",
                    "CAMPAIGN_LLM_MODEL_GENERATION=deepseek-reasoner"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "6" {
            $key = (Read-Host "    Вставьте Groq API ключ (gsk_...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=groq",
                    "CAMPAIGN_GROQ_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=llama-3.3-70b-versatile",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=llama-3.3-70b-versatile",
                    "CAMPAIGN_LLM_MODEL_GENERATION=llama-3.3-70b-versatile"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "7" {
            $key = (Read-Host "    Вставьте xAI API ключ (xai-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=xai",
                    "CAMPAIGN_XAI_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=grok-3-mini",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=grok-3-mini",
                    "CAMPAIGN_LLM_MODEL_GENERATION=grok-3"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "8" {
            $key = (Read-Host "    Вставьте OpenRouter API ключ (sk-or-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=openrouter",
                    "CAMPAIGN_OPENROUTER_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=anthropic/claude-3.5-haiku",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=anthropic/claude-3.5-haiku",
                    "CAMPAIGN_LLM_MODEL_GENERATION=anthropic/claude-sonnet-4"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "9" {
            $key = (Read-Host "    Вставьте Cohere API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=cohere",
                    "CAMPAIGN_COHERE_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=command-r-plus",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=command-r",
                    "CAMPAIGN_LLM_MODEL_GENERATION=command-r-plus"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "10" {
            $key = (Read-Host "    Вставьте Together AI API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=together",
                    "CAMPAIGN_TOGETHER_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=meta-llama/Llama-3-70b-chat-hf",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=meta-llama/Llama-3-8b-chat-hf",
                    "CAMPAIGN_LLM_MODEL_GENERATION=meta-llama/Llama-3-70b-chat-hf"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "11" {
            $key = (Read-Host "    Вставьте Fireworks AI API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=fireworks",
                    "CAMPAIGN_FIREWORKS_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=accounts/fireworks/models/llama-v3p3-70b-instruct",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=accounts/fireworks/models/llama-v3p3-70b-instruct",
                    "CAMPAIGN_LLM_MODEL_GENERATION=accounts/fireworks/models/llama-v3p3-70b-instruct"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "12" {
            $key = (Read-Host "    Вставьте Cerebras API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=cerebras",
                    "CAMPAIGN_CEREBRAS_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=llama-3.3-70b",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=llama-3.3-70b",
                    "CAMPAIGN_LLM_MODEL_GENERATION=llama-3.3-70b"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "13" {
            $key = (Read-Host "    Вставьте Perplexity API ключ (pplx-...)").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=perplexity",
                    "CAMPAIGN_PERPLEXITY_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=sonar",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=sonar",
                    "CAMPAIGN_LLM_MODEL_GENERATION=sonar-pro"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "14" {
            $key = (Read-Host "    Вставьте Nebius API ключ").Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                $envLines = @(
                    "CAMPAIGN_LLM_PROVIDER=nebius",
                    "CAMPAIGN_NEBIUS_API_KEY=$key",
                    "CAMPAIGN_LLM_MODEL_ASSISTANT=meta-llama/Llama-3-70B-Instruct",
                    "CAMPAIGN_LLM_MODEL_EXTRACTION=meta-llama/Llama-3-8B-Instruct",
                    "CAMPAIGN_LLM_MODEL_GENERATION=meta-llama/Llama-3-70B-Instruct"
                )
            } else {
                Write-Warn2 "Ключ пустой - пропускаю настройку."
            }
        }
        "15" {
            $model = (Read-Host "    Имя модели Ollama (Enter = llama3.3; модель должна быть скачана: ollama pull <имя>)").Trim()
            if ([string]::IsNullOrWhiteSpace($model)) { $model = "llama3.3" }
            $envLines = @(
                "CAMPAIGN_LLM_PROVIDER=ollama",
                "CAMPAIGN_LLM_MODEL_ASSISTANT=$model",
                "CAMPAIGN_LLM_MODEL_EXTRACTION=$model",
                "CAMPAIGN_LLM_MODEL_GENERATION=$model"
            )
        }
        "16" {
            if (-not $ExperimentalProviders) {
                Write-Warn2 "Экспериментальные провайдеры скрыты. Запустите start.bat -ConfigureAI -ExperimentalProviders."
                break
            }
            Write-Warn2 "Этот режим использует внутренний неподдерживаемый API ChatGPT/Codex."
            Write-Warn2 "OpenAI может изменить или заблокировать его; риск для аккаунта и поддержку вы принимаете на себя."
            $ack = (Read-Host "    Чтобы продолжить, введите I ACCEPT").Trim()
            if ($ack -cne "I ACCEPT") {
                Write-Warn2 "Подтверждение не получено - настройка отменена."
                break
            }
            $oauthPath = Join-Path $DataDir "openai_codex_oauth.json"
            $models = Connect-OpenAICodex $oauthPath
            $assistantModel = Select-LiveModel $models "обычного чата"
            $extractionModel = Select-LiveModel $models "проверок и извлечения"
            $generationModel = Select-LiveModel $models "творческой генерации"
            $envLines = @(
                "CAMPAIGN_EXPERIMENTAL_PROVIDERS_ENABLED=true",
                "CAMPAIGN_LLM_PROVIDER=openai_codex",
                "CAMPAIGN_LLM_MODEL_ASSISTANT=$assistantModel",
                "CAMPAIGN_LLM_MODEL_EXTRACTION=$extractionModel",
                "CAMPAIGN_LLM_MODEL_GENERATION=$generationModel"
            )
        }
    }

    if ($null -ne $envLines) {
        Write-Host ""
        Write-Host "      Векторный поиск по лору (эмбеддинги):"
        Write-Host "      1 - Локальная модель (по умолчанию; лор не покидает машину)"
        Write-Host "      2 - OpenAI (качественнее, но text лора уходит в OpenAI)"
        Write-Host "      3 - Google Gemini"
        Write-Host "      4 - Mistral"
        Write-Host "      5 - Cohere"
        Write-Host "      6 - Together AI"
        Write-Host "      7 - Fireworks AI"
        Write-Host "      8 - Ollama (локальные модели через Ollama)"
        Write-Host "      9 - Отключить (ассистент будет хуже находить связанный лор)"
        Write-Host ""
        $embChoice = (Read-Host "    Выберите (1-9 или Enter = 1)").Trim()
        switch ($embChoice) {
            "2" {
                $hasOpenAiKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_OPENAI_API_KEY=*" }).Count -gt 0
                if (-not $hasOpenAiKey) {
                    $embKey = (Read-Host "    Вставьте OpenAI API ключ для эмбеддингов (sk-...)").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_OPENAI_API_KEY=$embKey"
                        $hasOpenAiKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasOpenAiKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=openai" }
            }
            "3" {
                $hasKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_GOOGLE_API_KEY=*" }).Count -gt 0
                if (-not $hasKey) {
                    $embKey = (Read-Host "    Вставьте Google API ключ для эмбеддингов (AIza...)").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_GOOGLE_API_KEY=$embKey"
                        $hasKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=google" }
            }
            "4" {
                $hasKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_MISTRAL_API_KEY=*" }).Count -gt 0
                if (-not $hasKey) {
                    $embKey = (Read-Host "    Вставьте Mistral API ключ для эмбеддингов").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_MISTRAL_API_KEY=$embKey"
                        $hasKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=mistral" }
            }
            "5" {
                $hasKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_COHERE_API_KEY=*" }).Count -gt 0
                if (-not $hasKey) {
                    $embKey = (Read-Host "    Вставьте Cohere API ключ для эмбеддингов").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_COHERE_API_KEY=$embKey"
                        $hasKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=cohere" }
            }
            "6" {
                $hasKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_TOGETHER_API_KEY=*" }).Count -gt 0
                if (-not $hasKey) {
                    $embKey = (Read-Host "    Вставьте Together AI API ключ для эмбеддингов").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_TOGETHER_API_KEY=$embKey"
                        $hasKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=together" }
            }
            "7" {
                $hasKey = @($envLines | Where-Object { $_ -like "CAMPAIGN_FIREWORKS_API_KEY=*" }).Count -gt 0
                if (-not $hasKey) {
                    $embKey = (Read-Host "    Вставьте Fireworks AI API ключ для эмбеддингов").Trim()
                    if (-not [string]::IsNullOrWhiteSpace($embKey)) {
                        $envLines += "CAMPAIGN_FIREWORKS_API_KEY=$embKey"
                        $hasKey = $true
                    } else {
                        Write-Warn2 "Ключ пустой - оставляю локальные эмбеддинги."
                    }
                }
                if ($hasKey) { $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=fireworks" }
            }
            "8" {
                $model = (Read-Host "    Имя модели Ollama для эмбеддингов (Enter = nomic-embed-text)").Trim()
                if ([string]::IsNullOrWhiteSpace($model)) { $model = "nomic-embed-text" }
                $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=ollama"
                $envLines += "CAMPAIGN_OLLAMA_EMBEDDING_MODEL=$model"
            }
            "9" {
                $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=disabled"
            }
            # Enter / anything else = local, the Settings default: nothing to write.
        }

        $content = ($envLines -join "`n") + "`n"
        if ($hadEnvFile) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $backup = "$EnvFile.backup-$stamp"
            Copy-Item -LiteralPath $EnvFile -Destination $backup
            Write-Ok "Предыдущие настройки сохранены: backend\$(Split-Path -Leaf $backup)"
        }
        [System.IO.File]::WriteAllText($EnvFile, $content, [System.Text.Encoding]::ASCII)
        Write-Ok "Настройки сохранены в backend\.env (там же их можно поменять)."
    } else {
        if ($hadEnvFile) {
            Write-Ok "Настройка отменена; существующий backend\.env не изменён."
        } else {
            Copy-Item (Join-Path $Backend ".env.example") $EnvFile
            Write-Ok "Пропущено. AI можно настроить позже в backend\.env (см. подсказки внутри файла)."
        }
    }
}

# --- 4. Dependencies ----------------------------------------------------------

Write-Step "Устанавливаю зависимости бэкенда (uv sync)..."
Push-Location $Backend
try { uv sync } finally { Pop-Location }
Write-Ok "Бэкенд готов."

Write-Step "Устанавливаю зависимости фронтенда (npm install)..."
Push-Location $Frontend
try { npm install --no-fund --no-audit } finally { Pop-Location }
Write-Ok "Фронтенд готов."

# The backend serves this build itself, so there is one process and one port:
# one firewall rule, one port to forward, and no CORS at all.
Write-Step "Собираю интерфейс..."
Push-Location $Frontend
try { npm run build } finally { Pop-Location }
Write-Ok "Интерфейс собран."

# --- 5. LAN play mode (opt-in) --------------------------------------------------

# The server reads TLS settings itself (see loregraph/server.py); this only
# needs to know the scheme to print the right links.
$envSettings = Read-KeyValueFile $EnvFile
if (-not [string]::IsNullOrWhiteSpace($envSettings["CAMPAIGN_SSL_CERTFILE"]) -and
    -not [string]::IsNullOrWhiteSpace($envSettings["CAMPAIGN_SSL_KEYFILE"])) {
    $AppScheme = "https"
}
$LocalUrl = "${AppScheme}://127.0.0.1:$AppPort"
$FrontendUrl = $LocalUrl

# Loopback-only by default; --Lan opens the app to the local network.
# -Internet is LAN plus a router port-forward, so it implies -Lan.
if ($Internet) { $Lan = $true }
$BindHost = "127.0.0.1"
if ($Lan) {
    if ([string]::IsNullOrWhiteSpace($LanHost)) {
        $LanHost = Get-PrimaryLanIp
        if ([string]::IsNullOrWhiteSpace($LanHost)) {
            $ips = Get-LanIpCandidates
            if ($ips.Count -gt 0) {
                Write-Warn2 "Не удалось определить основной адрес. Найдены: $($ips -join ', ')"
            }
            throw "Укажите адрес вручную: start.bat -Lan -LanHost 192.168.1.5"
        }
        Write-Ok "Адрес в сети: $LanHost (изменить: -LanHost <адрес>)"
    }
    $BindHost = "0.0.0.0"
    $FrontendUrl = "${AppScheme}://${LanHost}:$AppPort"
    # Passed to the child process via inherited environment (see config.py).
    $env:CAMPAIGN_PLAY_MODE_ENABLED = "1"
    $env:CAMPAIGN_PLAY_HOST = $LanHost
    if ($Internet) { $env:CAMPAIGN_INTERNET_MODE_ENABLED = "1" }
}

# --- 6. Launch ------------------------------------------------------------------

Write-Step "Запускаю Loregraph..."

$portsBusy = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq $AppPort }
if ($null -ne $portsBusy) {
    throw "Порт $AppPort уже занят. Возможно, Loregraph уже запущен - проверьте открытые окна (или браузер: $LocalUrl)."
}

Write-Host "    Первый запуск может занять пару минут (скачивается локальная embedding-модель)." -ForegroundColor Gray

if ($AppScheme -eq "https") {
    # The health poll below must not fail on a self-signed certificate — the
    # common case for a home game. PS 5.1 has no -SkipCertificateCheck, so
    # trust is relaxed for THIS process only, and only for our own poll.
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
}

# One process, one port: the backend serves the built interface too.
# loregraph-serve (not uvicorn directly) so TLS is read from settings in one
# place instead of being parsed out of .env by each launcher script.
# -NoNewWindow keeps it attached to this console, so closing this window
# (or Ctrl+C) takes it down with it.
$backendProc = Start-Process -FilePath "uv" `
    -ArgumentList "run", "loregraph-serve", "--host", $BindHost, "--port", "$AppPort" `
    -WorkingDirectory $Backend -NoNewWindow -PassThru

try {
    # Wait for the health endpoint before opening the browser.
    $healthy = $false
    foreach ($i in 1..120) {
        if ($backendProc.HasExited) { throw "Loregraph завершился с ошибкой - смотрите сообщения выше." }
        try {
            $resp = Invoke-WebRequest -Uri "$LocalUrl/api/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw "Loregraph не ответил за 4 минуты - смотрите сообщения выше." }

    # Ask the app where it actually ended up reachable, so this banner and the
    # links in the interface can never disagree (see api/routers/network.py).
    $net = $null
    try {
        $net = Invoke-RestMethod -Uri "$LocalUrl/api/network" -UseBasicParsing -TimeoutSec 5
        if ($net.base_url) { $FrontendUrl = $net.base_url }
    } catch {}

    # In LAN mode the DM still opens the app on this machine via localhost.
    Start-Process $LocalUrl
    Write-Host ""
    Write-Host "=========================================================" -ForegroundColor Green
    Write-Host "  Loregraph запущен: $LocalUrl" -ForegroundColor Green
    if ($Internet) {
        switch ($net.upnp.outcome) {
            "mapped" {
                Write-Host "  Доступ из интернета настроен автоматически." -ForegroundColor Green
            }
            "cgnat" {
                Write-Warn2 "Доступ из интернета невозможен: провайдер выдал адрес"
                Write-Warn2 "$($net.upnp.external_ip) - это общий адрес (CGNAT), а не ваш личный."
                Write-Warn2 "Закажите у провайдера 'белый IP' либо используйте Tailscale."
                Write-Warn2 "По локальной сети всё работает."
            }
            "no_router" {
                Write-Warn2 "Роутер не ответил на UPnP - скорее всего он выключен в настройках роутера."
                Write-Warn2 "Включите UPnP или пробросьте порт $AppPort вручную. По локальной сети всё работает."
            }
            "refused" {
                Write-Warn2 "Роутер отказался пробрасывать порт. Пробросьте порт $AppPort вручную."
                Write-Warn2 "По локальной сети всё работает."
            }
            default {
                Write-Warn2 "Не удалось настроить доступ из интернета. По локальной сети всё работает."
            }
        }
    }
    if ($Lan) {
        Write-Host "  Режим игры по сети включён." -ForegroundColor Green
        Write-Host "  Ссылки-приглашения для игроков создавайте в:" -ForegroundColor Green
        Write-Host "  Настройки проекта -> Игроки." -ForegroundColor Green
        Write-Host "  Игроки подключаются на: $FrontendUrl" -ForegroundColor Green
        Write-Host "  Если не открывается - разрешите порт $AppPort в брандмауэре." -ForegroundColor Yellow
        if ($AppScheme -eq "https") {
            Write-Host "  ВНИМАНИЕ: ваш мир доступен всем в этой сети по ссылкам." -ForegroundColor Yellow
            Write-Host "  Отзывайте ссылки, когда они не нужны." -ForegroundColor Yellow
        } else {
            Write-Host "  ВНИМАНИЕ: ваш мир доступен всем в этой сети по ссылкам," -ForegroundColor Yellow
            Write-Host "  трафик не шифруется. Отзывайте ссылки, когда они не нужны." -ForegroundColor Yellow
        }
    }
    Write-Host "  Чтобы остановить - закройте это окно или нажмите Ctrl+C" -ForegroundColor Green
    Write-Host "=========================================================" -ForegroundColor Green

    # Keep the console alive; periodically check the remote for new commits.
    # The console is told once, but the status file is refreshed on every
    # check so the in-app updates section doesn't go stale.
    $updateAnnounced = $false
    $sinceCheck = 0
    while ($true) {
        Start-Sleep -Seconds 15
        $sinceCheck += 15
        if ($backendProc.HasExited) {
            Write-Warn2 "Loregraph завершился, останавливаю."
            break
        }
        if ($sinceCheck -ge $UpdateCheckInterval -and $hasGit -and (Read-UpdatePrefs).mode -ne "never") {
            $sinceCheck = 0
            Push-Location $Root
            try {
                cmd /c "git fetch --quiet 2>nul"
                $local = git rev-parse HEAD
                $remote = git rev-parse --verify --quiet '@{u}'
                if (-not [string]::IsNullOrWhiteSpace($remote) -and $local -ne $remote) {
                    $upstream = git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
                    $latestVersion = Get-RemoteVersion $upstream
                    $remoteChangelog = (git --no-pager show "${upstream}:CHANGELOG.md") -join "`n"
                    $section = Get-ChangelogSection $remoteChangelog $latestVersion
                    $dirty = git status --porcelain
                    Write-UpdateStatus 1 ([int](-not [string]::IsNullOrWhiteSpace($dirty))) $localVersion $latestVersion $section
                    if (-not $updateAnnounced) {
                        Write-Host ""
                        Write-Warn2 "Вышло обновление Loregraph! Закройте окно и запустите start.bat заново, чтобы обновиться."
                        $updateAnnounced = $true
                    }
                } else {
                    Write-UpdateStatus 1 0 $localVersion $localVersion ""
                }
            } catch {} finally { Pop-Location }
        }
    }
} finally {
    Write-Host "`nОстанавливаю Loregraph..." -ForegroundColor Cyan
    if ($null -ne $backendProc -and -not $backendProc.HasExited) {
        # /T kills the whole tree (uv -> python).
        cmd /c "taskkill /PID $($backendProc.Id) /T /F >nul 2>&1"
    }
}
