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
    Write-Host "      Enter - пропустить, настроить позже"
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
    }

    if ($null -ne $envLines) {
        Write-Host ""
        Write-Host "      Векторный поиск по лору (эмбеддинги):"
        Write-Host "      1 - Локальная модель (по умолчанию; лор не покидает машину)"
        Write-Host "      2 - OpenAI (качественнее, но текст лора уходит в OpenAI)"
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
