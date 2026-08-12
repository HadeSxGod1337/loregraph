#!/usr/bin/env bash
# Loregraph uninstaller for macOS/Linux — mirror of uninstall.ps1.
#
# Two jobs, in this order: first *show* where the disk space actually went,
# then offer to remove it a piece at a time. The showing matters as much as the
# removing — the launcher installs uv and lets it fill its own caches outside
# the project folder, so "just delete the folder" leaves several hundred
# megabytes behind with nothing pointing at them.
#
# Rule for what this script will and will not delete on its own:
#   * Ours (the project folder, its data, its model cache) — offered, with the
#     campaign data called out separately because it is the one thing that
#     cannot be downloaded again.
#   * Shared (uv, Node.js, their package caches) — never removed silently.
#     Other Python and Node projects on this machine use them. They are shown
#     with their size and the exact command to remove them, and that is all.
#
# Run from the repo root: bash uninstall.sh   (flags: --yes, --report-only)
#
# Written for bash 3.2 — the version macOS still ships. No namerefs, no
# associative arrays: entries are "path|label|note" strings in a flat array.

set -u

ASSUME_YES=0
REPORT_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y)      ASSUME_YES=1 ;;
        --report-only) REPORT_ONLY=1 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
DATA_DIR="$BACKEND/data"
TMP="${TMPDIR:-/tmp}"
TMP="${TMP%/}"

# Colour only when stdout is a terminal — piping this into a file or a log
# should not fill it with escape sequences.
if [ -t 1 ]; then
    C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_DIM=$'\033[90m'; C_RESET=$'\033[0m'
else
    C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_DIM=""; C_RESET=""
fi

step() { printf '\n%s==> %s%s\n' "$C_CYAN" "$1" "$C_RESET"; }
ok()   { printf '    %s%s%s\n' "$C_GREEN" "$1" "$C_RESET"; }
warn() { printf '    %s%s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }
dim()  { printf '    %s%s%s\n' "$C_DIM" "$1" "$C_RESET"; }

# Size in kibibytes, empty when the path does not exist. `du -sk` is the one
# spelling that behaves the same on macOS (BSD) and Linux (GNU).
dir_size_kb() {
    [ -e "$1" ] || return 0
    du -sk "$1" 2>/dev/null | awk '{print $1}'
}

format_size() {
    local kb="${1:-}"
    [ -z "$kb" ] && { printf '—'; return; }
    printf '%s %s' "$(format_size_number "$kb")" "$(format_size_unit "$kb")"
}

format_size_number() {
    local kb="$1"
    if [ "$kb" -ge 1048576 ]; then
        awk -v k="$kb" 'BEGIN{printf "%.1f", k/1048576}'
    elif [ "$kb" -ge 1024 ]; then
        awk -v k="$kb" 'BEGIN{printf "%.0f", k/1024}'
    else
        printf '%s' "$kb"
    fi
}

format_size_unit() {
    local kb="$1"
    if [ "$kb" -ge 1048576 ]; then printf 'ГБ'
    elif [ "$kb" -ge 1024 ]; then printf 'МБ'
    else printf 'КБ'; fi
}

field() { printf '%s' "$1" | cut -d'|' -f"$2"; }

# The size goes FIRST and the label last, and only the ASCII number is padded.
#
# Every other arrangement was wrong: printf's width specifiers count bytes, and
# a Cyrillic character is two of them in UTF-8, so "%-38s" pads a Russian label
# to roughly half the intended column. ${#s} would count characters — but only
# in a UTF-8 locale, and this script runs under whatever locale the user has
# (Git Bash on Windows commonly reports C, where it counts bytes again). Rather
# than depend on the locale, nothing variable-width is ever padded.
print_row() {
    local kb="$1" label="$2"
    printf '    %6s %-2s  %s\n' \
        "$(format_size_number "$kb")" "$(format_size_unit "$kb")" "$label"
}

OURS=()
OURS+=("$BACKEND/.venv|Окружение Python|зависимости бэкенда")
OURS+=("$FRONTEND/node_modules|Зависимости фронтенда|")
OURS+=("$DATA_DIR/models|Модель для поиска по лору|скачивается один раз")
# Pre-0.3.1 installs cached the model in the system temp directory (fastembed's
# own default). Nothing writes there any more, but ~240 MB of it is still on
# disk for anyone who ran an earlier version, and nothing else will ever
# collect it — so it is listed as ours, because it is.
if [ -d "$TMP/fastembed_cache" ]; then
    OURS+=("$TMP/fastembed_cache|Модель, старое расположение|от версий до 0.3.1, больше не используется")
fi

SHARED=()
SHARED+=("$HOME/.cache/uv|Кэш uv|ускоряет установку других проектов на Python")
SHARED+=("$HOME/Library/Caches/uv|Кэш uv|ускоряет установку других проектов на Python")
SHARED+=("$HOME/.npm|Кэш npm|ускоряет установку других проектов на Node")
SHARED+=("$HOME/.local/share/uv|Python, скачанный uv|им могут пользоваться другие проекты")

# Prints each existing entry and returns the group total on stdout's last line.
show_group() {
    local title="$1"; shift
    local total=0 printed=0 entry path label note size
    for entry in "$@"; do
        path="$(field "$entry" 1)"
        size="$(dir_size_kb "$path")"
        [ -z "$size" ] && continue
        if [ "$printed" -eq 0 ]; then printf '\n  %s\n' "$title" >&2; printed=1; fi
        label="$(field "$entry" 2)"
        note="$(field "$entry" 3)"
        total=$((total + size))
        print_row "$size" "$label" >&2
        dim "  $path" >&2
        [ -n "$note" ] && dim "  $note" >&2
    done
    printf '%s' "$total"
}

printf '\n  Loregraph — удаление\n'
printf '  %sСначала посмотрим, что и где занимает место.%s\n' "$C_DIM" "$C_RESET"

OURS_TOTAL="$(show_group "Принадлежит Loregraph" "${OURS[@]}")"

DATA_SIZE="$(dir_size_kb "$DATA_DIR")"
if [ -n "$DATA_SIZE" ]; then
    print_row "$DATA_SIZE" "Данные кампаний"
    dim "  $DATA_DIR"
    dim "  база, вложения, векторный индекс"
    OURS_TOTAL=$((OURS_TOTAL + DATA_SIZE))
fi

SHARED_TOTAL="$(show_group "Общие инструменты — их этот скрипт не трогает" "${SHARED[@]}")"

printf '\n  Всего наше:   %s\n' "$(format_size "$OURS_TOTAL")"
if [ "$SHARED_TOTAL" -gt 0 ]; then
    printf '  %sОбщие кэши:   %s%s\n\n' "$C_DIM" "$(format_size "$SHARED_TOTAL")" "$C_RESET"
    warn "Общие кэши принадлежат uv и npm, а не Loregraph. Если других"
    warn "проектов на Python и Node у вас нет, очистить их можно так:"
    dim "  uv cache clean"
    dim "  npm cache clean --force"
    dim "Сам uv удаляется командой:  uv self uninstall"
fi

if [ "$REPORT_ONLY" -eq 1 ]; then
    echo
    ok "Ничего не удалено (запуск с --report-only)."
    exit 0
fi

confirm() {
    local question="$1" default="$2" answer suffix
    [ "$ASSUME_YES" -eq 1 ] && return 0
    if [ "$default" = "yes" ]; then suffix="[Д/н]"; else suffix="[д/Н]"; fi
    read -r -p "  $question $suffix " answer </dev/tty || return 1
    if [ -z "$answer" ]; then
        [ "$default" = "yes" ]
        return
    fi
    case "$answer" in [дДyY]*) return 0 ;; *) return 1 ;; esac
}

remove_path() {
    local path="$1" label="$2" size="$3"
    # A file still held open (the app running) is the normal failure here, and
    # it must not abort the rest of the cleanup.
    if rm -rf "$path" 2>/dev/null; then
        ok "Удалено: $label ($(format_size "$size"))"
    else
        warn "Не удалось удалить $path"
        warn "Закройте приложение и запустите скрипт ещё раз."
    fi
}

step "Удаляю то, что скачивается заново"
for entry in "${OURS[@]}"; do
    path="$(field "$entry" 1)"
    size="$(dir_size_kb "$path")"
    [ -z "$size" ] && continue
    label="$(field "$entry" 2)"
    if confirm "Удалить «$label» ($(format_size "$size"))?" yes; then
        remove_path "$path" "$label" "$size"
    else
        dim "Оставлено: $label"
    fi
done

if [ -n "$DATA_SIZE" ]; then
    step "Данные кампаний"
    warn "Это ваши кампании: сущности, связи, вложения, заметки игроков."
    warn "Восстановить их будет неоткуда. Экспорт проекта делается в"
    warn "приложении: «Действия с проектом» → «Экспортировать»."
    # Defaults to NO, and --yes does not override it: an unattended run must
    # never be the reason someone's campaign is gone.
    if [ "$ASSUME_YES" -eq 0 ] && confirm "Удалить данные кампаний ($(format_size "$DATA_SIZE"))?" no; then
        remove_path "$DATA_DIR" "Данные кампаний" "$DATA_SIZE"
    else
        dim "Данные кампаний оставлены: $DATA_DIR"
    fi
fi

step "Готово"
ok "Осталось удалить саму папку проекта, если она больше не нужна:"
dim "  $ROOT"
dim "Скрипт не удаляет её сам — он лежит внутри неё."
echo
