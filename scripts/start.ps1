# Loregraph one-click launcher for non-developers.
# Installs missing tools (uv, Node.js), pulls updates, installs dependencies,
# asks for an API key on first run, starts backend + frontend, opens the browser.
# Run via start.bat in the repo root (double-click).

param(
    [switch]$SkipUpdate
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendUrl = "http://127.0.0.1:8000"
$FrontendUrl = "http://127.0.0.1:5173"
# How often the background loop checks the git remote for updates (seconds).
$UpdateCheckInterval = 600

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Test-Command($name) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    return ($null -ne $found)
}

# --- 1. Git update (skipped for zip downloads without .git) -----------------

if (-not $SkipUpdate -and (Test-Path (Join-Path $Root ".git")) -and (Test-Command "git")) {
    Write-Step "Проверяю обновления проекта..."
    Push-Location $Root
    try {
        cmd /c "git fetch --quiet 2>nul"
        $local = git rev-parse HEAD
        # --verify --quiet: empty output instead of stderr noise when no upstream
        $remote = git rev-parse --verify --quiet '@{u}'
        if (-not [string]::IsNullOrWhiteSpace($remote) -and $local -ne $remote) {
            $dirty = git status --porcelain
            if ([string]::IsNullOrWhiteSpace($dirty)) {
                Write-Warn2 "Найдено обновление, скачиваю..."
                git pull --ff-only --quiet
                Write-Ok "Проект обновлён."
            } else {
                Write-Warn2 "Есть обновление, но у вас локальные изменения - пропускаю git pull."
            }
        } else {
            Write-Ok "Проект актуален."
        }
    } catch {
        Write-Warn2 "Не удалось проверить обновления (нет сети?), продолжаю."
    } finally {
        Pop-Location
    }
}

# --- 2. Tools: uv and Node.js ------------------------------------------------

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
if (-not (Test-Path $EnvFile)) {
    Write-Step "Первый запуск: настройка AI-ассистента (необязательно)"
    Write-Host "    Без AI редактор мира работает полностью, не будет только AI-ассистента." -ForegroundColor Gray
    Write-Host ""
    Write-Host "      1 - Anthropic / Claude (рекомендуется, нужен API-ключ)"
    Write-Host "      2 - OpenAI (нужен API-ключ)"
    Write-Host "      3 - Ollama (локальные модели, без ключа; Ollama должна быть установлена)"
    Write-Host "      Enter - пропустить, настроить позже"
    Write-Host ""
    $choice = (Read-Host "    Выберите провайдера (1/2/3 или Enter)").Trim()

    # $null = skip and copy .env.example instead.
    $envLines = $null
    if ($choice -eq "1") {
        $key = (Read-Host "    Вставьте Anthropic API ключ (sk-ant-...)").Trim()
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            # Default provider and models are already Anthropic — the key is enough.
            $envLines = @("CAMPAIGN_ANTHROPIC_API_KEY=$key")
        } else {
            Write-Warn2 "Ключ пустой - пропускаю настройку."
        }
    } elseif ($choice -eq "2") {
        $key = (Read-Host "    Вставьте OpenAI API ключ (sk-...)").Trim()
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            # Default model ids are Anthropic — must override all three tiers.
            $envLines = @(
                "CAMPAIGN_LLM_PROVIDER=openai",
                "CAMPAIGN_OPENAI_API_KEY=$key",
                "CAMPAIGN_LLM_MODEL_EXTRACTION=gpt-4o-mini",
                "CAMPAIGN_LLM_MODEL_GENERATION=gpt-4o",
                "CAMPAIGN_LLM_MODEL_COMPOSITION=gpt-4o"
            )
        } else {
            Write-Warn2 "Ключ пустой - пропускаю настройку."
        }
    } elseif ($choice -eq "3") {
        $model = (Read-Host "    Имя модели Ollama (Enter = llama3.1; модель должна быть скачана: ollama pull <имя>)").Trim()
        if ([string]::IsNullOrWhiteSpace($model)) { $model = "llama3.1" }
        $envLines = @(
            "CAMPAIGN_LLM_PROVIDER=ollama",
            "CAMPAIGN_LLM_MODEL_EXTRACTION=$model",
            "CAMPAIGN_LLM_MODEL_GENERATION=$model",
            "CAMPAIGN_LLM_MODEL_COMPOSITION=$model"
        )
    }

    if ($null -ne $envLines) {
        Write-Host ""
        Write-Host "      Векторный поиск по лору (эмбеддинги):"
        Write-Host "      1 - Локальная модель (по умолчанию; лор не покидает машину)"
        Write-Host "      2 - OpenAI (качественнее, но текст лора уходит в OpenAI; нужен OpenAI-ключ)"
        Write-Host "      3 - Отключить (ассистент будет хуже находить связанный лор)"
        Write-Host ""
        $embChoice = (Read-Host "    Выберите (1/2/3 или Enter = 1)").Trim()
        if ($embChoice -eq "2") {
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
        } elseif ($embChoice -eq "3") {
            $envLines += "CAMPAIGN_EMBEDDING_PROVIDER=disabled"
        }
        # Enter / anything else = local, the Settings default: nothing to write.

        $content = ($envLines -join "`n") + "`n"
        [System.IO.File]::WriteAllText($EnvFile, $content, [System.Text.Encoding]::ASCII)
        Write-Ok "Настройки сохранены в backend\.env (там же их можно поменять)."
    } else {
        Copy-Item (Join-Path $Backend ".env.example") $EnvFile
        Write-Ok "Пропущено. AI можно настроить позже в backend\.env (см. подсказки внутри файла)."
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

# --- 5. Launch ------------------------------------------------------------------

Write-Step "Запускаю Loregraph..."

$portsBusy = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq 8000 -or $_.LocalPort -eq 5173 }
if ($null -ne $portsBusy) {
    throw "Порт 8000 или 5173 уже занят. Возможно, Loregraph уже запущен - проверьте открытые окна (или браузер: $FrontendUrl)."
}

Write-Host "    Первый запуск может занять пару минут (скачивается локальная embedding-модель)." -ForegroundColor Gray

# -NoNewWindow keeps both servers attached to this console: closing this
# window (or Ctrl+C) takes everything down with it.
$backendProc = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "loregraph.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $Backend -NoNewWindow -PassThru

$frontendProc = Start-Process -FilePath "cmd" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $Frontend -NoNewWindow -PassThru

try {
    # Wait for the backend health endpoint before opening the browser.
    $healthy = $false
    foreach ($i in 1..120) {
        if ($backendProc.HasExited) { throw "Бэкенд завершился с ошибкой - смотрите сообщения выше." }
        try {
            $resp = Invoke-WebRequest -Uri "$BackendUrl/api/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw "Бэкенд не ответил за 4 минуты - смотрите сообщения выше." }

    Start-Process $FrontendUrl
    Write-Host ""
    Write-Host "=========================================================" -ForegroundColor Green
    Write-Host "  Loregraph запущен: $FrontendUrl" -ForegroundColor Green
    Write-Host "  Чтобы остановить - закройте это окно или нажмите Ctrl+C" -ForegroundColor Green
    Write-Host "=========================================================" -ForegroundColor Green

    # Keep the console alive; periodically check the remote for new commits.
    $updateAnnounced = $false
    $sinceCheck = 0
    while ($true) {
        Start-Sleep -Seconds 15
        $sinceCheck += 15
        if ($backendProc.HasExited -or $frontendProc.HasExited) {
            Write-Warn2 "Один из процессов завершился, останавливаю всё."
            break
        }
        if (-not $updateAnnounced -and $sinceCheck -ge $UpdateCheckInterval -and (Test-Path (Join-Path $Root ".git")) -and (Test-Command "git")) {
            $sinceCheck = 0
            Push-Location $Root
            try {
                cmd /c "git fetch --quiet 2>nul"
                $local = git rev-parse HEAD
                $remote = git rev-parse --verify --quiet '@{u}'
                if (-not [string]::IsNullOrWhiteSpace($remote) -and $local -ne $remote) {
                    Write-Host ""
                    Write-Warn2 "Вышло обновление Loregraph! Закройте окно и запустите start.bat заново, чтобы обновиться."
                    $updateAnnounced = $true
                }
            } catch {} finally { Pop-Location }
        }
    }
} finally {
    Write-Host "`nОстанавливаю Loregraph..." -ForegroundColor Cyan
    foreach ($p in @($backendProc, $frontendProc)) {
        if ($null -ne $p -and -not $p.HasExited) {
            # /T kills the whole tree (uv -> python, cmd -> node).
            cmd /c "taskkill /PID $($p.Id) /T /F >nul 2>&1"
        }
    }
}
