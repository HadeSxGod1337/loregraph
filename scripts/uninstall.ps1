# Loregraph uninstaller for non-developers.
#
# Two jobs, in this order: first *show* where the disk space actually went,
# then offer to remove it a piece at a time. The showing matters as much as the
# removing — the launcher installs uv and Node.js and lets them fill their own
# caches outside the project folder, so "just delete the folder" leaves several
# hundred megabytes behind with nothing pointing at them.
#
# Rule for what this script will and will not delete on its own:
#   * Ours (the project folder, its data, its model cache) — offered, with the
#     campaign data called out separately because it is the one thing that
#     cannot be downloaded again.
#   * Shared (uv, Node.js, their package caches) — never removed silently.
#     Other Python and Node projects on this machine use them. They are shown
#     with their size and the exact command to remove them, and that is all.
#
# Run via uninstall.bat in the repo root (double-click).

param(
    # Skip every prompt and remove only what is unambiguously ours *except*
    # campaign data. For scripted cleanup; the interactive path is the default.
    [switch]$Yes,
    # Print the report and exit without touching anything.
    [switch]$ReportOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$DataDir = Join-Path $Backend "data"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Dim($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }

function Get-DirSize($path) {
    if (-not (Test-Path $path)) { return $null }
    try {
        $sum = (Get-ChildItem $path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { return 0 } else { return $sum }
    } catch {
        return $null
    }
}

function Format-Size($bytes) {
    if ($null -eq $bytes) { return "—" }
    if ($bytes -ge 1GB) { return "{0:N1} ГБ" -f ($bytes / 1GB) }
    if ($bytes -ge 1MB) { return "{0:N0} МБ" -f ($bytes / 1MB) }
    return "{0:N0} КБ" -f ($bytes / 1KB)
}

# An entry is one removable thing: where it is, what it is, and whether this
# script is allowed to delete it (see the rule in the header).
function New-Entry($path, $label, $note, $shared) {
    return [pscustomobject]@{
        Path   = $path
        Label  = $label
        Note   = $note
        Shared = $shared
        Size   = Get-DirSize $path
    }
}

Write-Host ""
Write-Host "  Loregraph — удаление" -ForegroundColor White
Write-Host "  Сначала посмотрим, что и где занимает место." -ForegroundColor DarkGray

# --- 1. What is ours ---------------------------------------------------------

$ours = @(
    (New-Entry (Join-Path $Backend ".venv") "Окружение Python" "зависимости бэкенда" $false),
    (New-Entry (Join-Path $Frontend "node_modules") "Зависимости фронтенда" "" $false),
    (New-Entry (Join-Path $DataDir "models") "Модель для поиска по лору" "скачивается один раз" $false)
)

# Pre-0.3.1 installs cached the model in the system temp directory (fastembed's
# own default). Nothing writes there any more, but ~240 MB of it is still on
# disk for anyone who ran an earlier version, and nothing else will ever
# collect it — so it is listed as ours, because it is.
$legacyModelCache = Join-Path $env:TEMP "fastembed_cache"
if (Test-Path $legacyModelCache) {
    $ours += New-Entry $legacyModelCache "Модель, старое расположение" `
        "от версий до 0.3.1, больше не используется" $false
}

# Campaign data is deliberately its own entry, never folded into "the project
# folder": it is the only thing here that no download can bring back.
$data = New-Entry $DataDir "Данные кампаний" "база, вложения, векторный индекс" $false

# --- 2. What is shared -------------------------------------------------------

$shared = @(
    (New-Entry (Join-Path $env:LOCALAPPDATA "uv\cache") "Кэш uv" `
        "ускоряет установку других проектов на Python" $true),
    (New-Entry (Join-Path $env:LOCALAPPDATA "npm-cache") "Кэш npm" `
        "ускоряет установку других проектов на Node" $true),
    # On Windows uv keeps its managed interpreters and tools under %APPDATA%,
    # not under ~/.local/share as it does on Linux/macOS. Only present when uv
    # had to download a Python — an installer that already had a suitable one
    # will not have this at all.
    (New-Entry (Join-Path $env:APPDATA "uv\python") "Python, скачанный uv" `
        "им могут пользоваться другие проекты" $true),
    (New-Entry (Join-Path $env:APPDATA "uv\tools") "Инструменты uv" "" $true)
)

# --- 3. The report -----------------------------------------------------------

function Show-Group($title, $entries) {
    $present = @($entries | Where-Object { $null -ne $_.Size })
    if ($present.Count -eq 0) { return 0 }
    Write-Host ""
    Write-Host "  $title" -ForegroundColor White
    $total = 0
    foreach ($e in $present) {
        $total += $e.Size
        # Size first, label last — same layout as uninstall.sh, which cannot
        # pad a Cyrillic label reliably (see print_row there).
        $line = "    {0,9}  {1}" -f (Format-Size $e.Size), $e.Label
        Write-Host $line -ForegroundColor Gray
        Write-Dim "      $($e.Path)"
        if ($e.Note) { Write-Dim "      $($e.Note)" }
    }
    return $total
}

$oursTotal = Show-Group "Принадлежит Loregraph" ($ours + @($data))
$sharedTotal = Show-Group "Общие инструменты — их этот скрипт не трогает" $shared

Write-Host ""
Write-Host ("  Всего наше:   {0}" -f (Format-Size $oursTotal)) -ForegroundColor White
if ($sharedTotal -gt 0) {
    Write-Host ("  Общие кэши:   {0}" -f (Format-Size $sharedTotal)) -ForegroundColor DarkGray
}

if ($sharedTotal -gt 0) {
    Write-Host ""
    Write-Warn2 "Общие кэши принадлежат uv и npm, а не Loregraph. Если других"
    Write-Warn2 "проектов на Python и Node у вас нет, очистить их можно так:"
    Write-Dim "  uv cache clean"
    Write-Dim "  npm cache clean --force"
    Write-Dim "Сам uv удаляется командой:  uv self uninstall"
    Write-Dim "Node.js — через «Параметры → Приложения», если его ставил лаунчер."
}

if ($ReportOnly) {
    Write-Host ""
    Write-Ok "Ничего не удалено (запуск с -ReportOnly)."
    exit 0
}

# --- 4. Removal --------------------------------------------------------------

function Confirm-Action($question, $default) {
    if ($Yes) { return $true }
    $suffix = if ($default) { "[Д/н]" } else { "[д/Н]" }
    $answer = Read-Host "  $question $suffix"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer -match '^(д|y)'
}

function Remove-Entry($entry) {
    if ($null -eq $entry.Size) { return }
    try {
        Remove-Item -LiteralPath $entry.Path -Recurse -Force -ErrorAction Stop
        Write-Ok "Удалено: $($entry.Label) ($(Format-Size $entry.Size))"
    } catch {
        # A locked file (the app still running, a file open in an editor) is the
        # normal failure here, and it must not abort the rest of the cleanup.
        Write-Warn2 "Не удалось удалить $($entry.Path): $($_.Exception.Message)"
        Write-Warn2 "Закройте приложение и запустите скрипт ещё раз."
    }
}

$removable = @($ours | Where-Object { $null -ne $_.Size })
if ($removable.Count -gt 0) {
    Write-Step "Удаляю то, что скачивается заново"
    foreach ($e in $removable) {
        if (Confirm-Action "Удалить «$($e.Label)» ($(Format-Size $e.Size))?" $true) {
            Remove-Entry $e
        } else {
            Write-Dim "Оставлено: $($e.Label)"
        }
    }
}

if ($null -ne $data.Size) {
    Write-Step "Данные кампаний"
    Write-Warn2 "Это ваши кампании: сущности, связи, вложения, заметки игроков."
    Write-Warn2 "Восстановить их будет неоткуда. Экспорт проекта делается в"
    Write-Warn2 "приложении: «Действия с проектом» → «Экспортировать»."
    # Defaults to NO, and -Yes does not override it: an unattended run must
    # never be the reason someone's campaign is gone.
    if (-not $Yes -and (Confirm-Action "Удалить данные кампаний ($(Format-Size $data.Size))?" $false)) {
        Remove-Entry $data
    } else {
        Write-Dim "Данные кампаний оставлены: $($data.Path)"
    }
}

Write-Step "Готово"
Write-Ok "Осталось удалить саму папку проекта, если она больше не нужна:"
Write-Dim "  $Root"
Write-Dim "Скрипт не удаляет её сам — он лежит внутри неё."
Write-Host ""
