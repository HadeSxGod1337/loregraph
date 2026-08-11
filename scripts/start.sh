#!/usr/bin/env bash
# Loregraph one-click launcher for macOS/Linux — mirror of start.ps1.
# Installs uv if missing, pulls updates, installs dependencies, asks for an
# AI provider on first run, starts backend + frontend, opens the browser.
# Run from the repo root: bash start.sh   (flag: --skip-update)

set -u

SKIP_UPDATE=0
LAN=0
INTERNET=0
LAN_HOST=""
prev=""
for arg in "$@"; do
    case "$prev" in
        --lan-host) LAN_HOST="$arg"; prev=""; continue ;;
    esac
    case "$arg" in
        --skip-update) SKIP_UPDATE=1 ;;
        # LAN play mode: bind to all interfaces so players on the same network
        # can connect. Off by default — the app stays on localhost.
        --lan)         LAN=1 ;;
        --lan-host)    prev="--lan-host" ;;
        # Internet mode: LAN plus asking the router (over UPnP) to forward the
        # port, so players outside the local network can connect.
        --internet)    INTERNET=1; LAN=1 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
# One process serves both the interface and the API, so there is a single port
# to allow through a firewall or forward on a router.
APP_PORT=8000
# Scheme follows the TLS settings; filled in once .env has been read below.
APP_SCHEME="http"
LOCAL_URL="http://127.0.0.1:$APP_PORT"
# Where players connect; only differs from LOCAL_URL in LAN mode.
FRONTEND_URL="$LOCAL_URL"
# uvicorn runs with backend/ as its working directory, so Settings.data_dir
# ("./data") resolves HERE — not at the repo root. The backend reads the same
# update files (see backend/src/loregraph/services/update_status.py).
DATA_DIR="$BACKEND/data"
# How often the background loop checks the git remote for updates (seconds).
UPDATE_CHECK_INTERVAL=600
# How long the update prompt waits before assuming "later" — an unattended
# launch must never hang on a question nobody is there to answer.
UPDATE_PROMPT_TIMEOUT=30

step()   { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()     { printf '\033[32m    %s\033[0m\n' "$1"; }
warn()   { printf '\033[33m    %s\033[0m\n' "$1"; }
die()    { printf '\033[31m    %s\033[0m\n' "$1"; exit 1; }

# --- Update preferences and status (shared with the backend) -----------------
# Flat key=value files, not JSON: this runs BEFORE uv and Node are installed,
# so neither Python nor jq is guaranteed to exist, and scripts/start.ps1 has to
# parse the very same files. The changelog lives in its own file so neither
# shell ever has to escape multi-line markdown. Mirror of start.ps1.

write_file_atomic() {
    # $1 = path, stdin = content. Rename, so a reader never sees a partial file.
    mkdir -p "$(dirname "$1")"
    cat > "$1.tmp" && mv -f "$1.tmp" "$1"
}

conf_value() {
    # $1 = file, $2 = key. Empty when absent; only the first '=' splits.
    [ -f "$1" ] || return 0
    sed -n "s/^[[:space:]]*$2[[:space:]]*=//p" "$1" | head -n 1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

update_mode() {
    local mode
    mode="$(conf_value "$DATA_DIR/update.conf" mode)"
    case "$mode" in
        ask|auto|never) printf '%s' "$mode" ;;
        *)              printf 'ask' ;;
    esac
}

is_version_skipped() {
    # $1 = version. Comma-separated list, compared whole-item.
    local skipped item
    skipped="$(conf_value "$DATA_DIR/update.conf" skipped_versions)"
    [ -n "$skipped" ] || return 1
    local IFS=,
    for item in $skipped; do
        [ "$(printf '%s' "$item" | tr -d '[:space:]')" = "$1" ] && return 0
    done
    return 1
}

write_update_prefs() {
    # $1 = mode, $2 = comma-separated skipped versions.
    write_file_atomic "$DATA_DIR/update.conf" <<EOF
# Loregraph update preferences.
# Edit here or in the app (sidebar -> preferences -> updates).
# mode: ask | auto | never
mode=$1
skipped_versions=$2
EOF
}

write_update_status() {
    # $1 = git_available, $2 = worktree_dirty, $3 = current, $4 = latest,
    # $5 = changelog section (empty removes the file).
    write_file_atomic "$DATA_DIR/update-status.conf" <<EOF
git_available=$1
worktree_dirty=$2
current_version=$3
latest_version=$4
checked_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
    if [ -n "$5" ]; then
        printf '%s\n' "$5" | write_file_atomic "$DATA_DIR/update-changelog.md"
    else
        rm -f "$DATA_DIR/update-changelog.md"
    fi
}

local_version() {
    [ -f "$BACKEND/pyproject.toml" ] || return 0
    sed -n 's/^version = "\(.*\)"/\1/p' "$BACKEND/pyproject.toml" | head -n 1
}

remote_version() {
    # $1 = upstream ref. --no-pager: without it git may hand output to `less`.
    (cd "$ROOT" && git --no-pager show "$1:backend/pyproject.toml" 2>/dev/null) |
        sed -n 's/^version = "\(.*\)"/\1/p' | head -n 1
}

show_changelog_preview() {
    printf '%s\n' "$1" | head -n 25 | while IFS= read -r line; do
        printf '\033[90m      %s\033[0m\n' "$line"
    done
    if [ "$(printf '%s\n' "$1" | wc -l)" -gt 25 ]; then
        printf '\033[90m      ... остальное — в CHANGELOG.md\033[0m\n'
    fi
}

# Digits, not letters: a Russian keyboard layout cannot type [Y]/[N] without
# switching, and the whole point is that this stays one keypress.
read_choice_with_timeout() {
    # $1 = enter choice, $2 = timeout choice. Echoes the chosen digit.
    local answer
    if [ ! -t 0 ]; then
        printf '%s' "$2"
        return 0
    fi
    printf '\033[36m    Ваш выбор (Enter = %s, через %s с продолжу без обновления): \033[0m' "$1" "$UPDATE_PROMPT_TIMEOUT"
    if read -r -t "$UPDATE_PROMPT_TIMEOUT" -n 1 answer; then
        printf '\n'
        [ -n "$answer" ] || answer="$1"
    else
        printf '\n'
        answer="$2"
    fi
    printf '%s' "$answer"
}

# --- 1. Git update (skipped for zip downloads without .git) -----------------

HAS_GIT=0
if [ -d "$ROOT/.git" ] && command -v git >/dev/null 2>&1; then
    HAS_GIT=1
fi
LOCAL_VERSION="$(local_version)"

# Zip install or no git binary: say so, instead of letting the app claim
# everything is up to date.
[ "$HAS_GIT" -eq 0 ] && write_update_status 0 0 "$LOCAL_VERSION" "" ""

if [ "$SKIP_UPDATE" -eq 0 ] && [ "$HAS_GIT" -eq 1 ] && [ "$(update_mode)" != "never" ]; then
    step "Проверяю обновления проекта..."
    if ! (cd "$ROOT" && git fetch --quiet 2>/dev/null); then
        warn "Не удалось проверить обновления (нет сети?), продолжаю."
    else
        LOCAL_REV="$(cd "$ROOT" && git rev-parse HEAD)"
        # --verify --quiet: empty output instead of stderr noise when no upstream
        REMOTE_REV="$(cd "$ROOT" && git rev-parse --verify --quiet '@{u}' || true)"
        if [ -z "$REMOTE_REV" ] || [ "$LOCAL_REV" = "$REMOTE_REV" ]; then
            write_update_status 1 0 "$LOCAL_VERSION" "$LOCAL_VERSION" ""
            ok "Проект актуален."
        else
            UPSTREAM="$(cd "$ROOT" && git rev-parse --abbrev-ref --symbolic-full-name '@{u}')"
            LATEST_VERSION="$(remote_version "$UPSTREAM")"
            # The new section only exists in the REMOTE changelog.
            CHANGELOG_SECTION="$(
                (cd "$ROOT" && git --no-pager show "$UPSTREAM:CHANGELOG.md" 2>/dev/null) |
                    bash "$ROOT/scripts/changelog-section.sh" "v$LATEST_VERSION" - 2>/dev/null || true
            )"
            DIRTY=0
            [ -n "$(cd "$ROOT" && git status --porcelain)" ] && DIRTY=1
            write_update_status 1 "$DIRTY" "$LOCAL_VERSION" "$LATEST_VERSION" "$CHANGELOG_SECTION"

            if is_version_skipped "$LATEST_VERSION"; then
                ok "Доступна версия $LATEST_VERSION, но вы её пропустили."
            elif [ "$(update_mode)" = "auto" ]; then
                if [ "$DIRTY" -eq 1 ]; then
                    warn "Есть обновление, но у вас локальные изменения - пропускаю git pull."
                else
                    warn "Найдено обновление $LATEST_VERSION, скачиваю..."
                    if (cd "$ROOT" && git pull --ff-only --quiet); then
                        write_update_status 1 0 "$LATEST_VERSION" "$LATEST_VERSION" ""
                        ok "Проект обновлён."
                    else
                        warn "Не удалось обновиться, продолжаю на текущей версии."
                    fi
                fi
            else
                printf '\n'
                if [ -z "$LATEST_VERSION" ]; then
                    warn "Доступно обновление Loregraph."
                else
                    warn "Доступна версия $LATEST_VERSION (у вас $LOCAL_VERSION). Что нового:"
                    [ -n "$CHANGELOG_SECTION" ] && show_changelog_preview "$CHANGELOG_SECTION"
                fi
                printf '\n'
                if [ "$DIRTY" -eq 1 ]; then
                    warn "Обновиться сейчас нельзя: в папке проекта есть ваши изменения."
                    printf '\033[90m      Сохраните или отмените их (git status), потом запустите снова.\033[0m\n'
                    printf '      [2] Позже   [3] Больше не предлагать эту версию\n'
                    ANSWER="$(read_choice_with_timeout 2 2)"
                else
                    printf '      [1] Обновить сейчас   [2] Позже   [3] Больше не предлагать эту версию\n'
                    ANSWER="$(read_choice_with_timeout 1 2)"
                fi
                case "$ANSWER" in
                    1)
                        warn "Обновляю..."
                        if (cd "$ROOT" && git pull --ff-only --quiet); then
                            write_update_status 1 0 "$LATEST_VERSION" "$LATEST_VERSION" ""
                            ok "Проект обновлён до $LATEST_VERSION."
                        else
                            warn "Не удалось обновиться, продолжаю на текущей версии."
                        fi
                        ;;
                    3)
                        if [ -n "$LATEST_VERSION" ]; then
                            EXISTING_SKIPPED="$(conf_value "$DATA_DIR/update.conf" skipped_versions)"
                            if [ -n "$EXISTING_SKIPPED" ]; then
                                EXISTING_SKIPPED="$EXISTING_SKIPPED,$LATEST_VERSION"
                            else
                                EXISTING_SKIPPED="$LATEST_VERSION"
                            fi
                            write_update_prefs "$(update_mode)" "$EXISTING_SKIPPED"
                            ok "Версия $LATEST_VERSION больше не будет предлагаться."
                        fi
                        ;;
                    *)
                        ok "Хорошо, обновимся позже."
                        ;;
                esac
            fi
        fi
    fi
fi

# --- 2. Tools: uv and Node.js ------------------------------------------------

step "Проверяю инструменты..."

if ! command -v uv >/dev/null 2>&1; then
    warn "uv не найден, устанавливаю..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || die "Не удалось установить uv. Установите вручную: https://docs.astral.sh/uv/"
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv установлен, но не найден в PATH. Перезапустите терминал и попробуйте снова."
fi
ok "uv: $(uv --version)"

if ! command -v npm >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        warn "Node.js не найден, устанавливаю через Homebrew..."
        brew install node || true
    fi
    if ! command -v npm >/dev/null 2>&1; then
        die "Node.js не найден. Установите (macOS: brew install node; Ubuntu/Debian: sudo apt install nodejs npm; https://nodejs.org) и запустите скрипт снова."
    fi
fi
ok "Node.js: $(node --version), npm: $(npm --version)"

# --- 3. API key (.env) on first run ------------------------------------------

ENV_FILE="$BACKEND/.env"
if [ ! -f "$ENV_FILE" ]; then
    step "Первый запуск: настройка AI-ассистента (необязательно)"
    printf '    Без AI редактор мира работает полностью, не будет только AI-ассистента.\n\n'
    printf '      1  - Anthropic / Claude (рекомендуется)\n'
    printf '      2  - OpenAI\n'
    printf '      3  - Google Gemini (бесплатный tier)\n'
    printf '      4  - Mistral\n'
    printf '      5  - DeepSeek (дешёвый, сильный)\n'
    printf '      6  - Groq (ультра-быстрый)\n'
    printf '      7  - xAI / Grok\n'
    printf '      8  - OpenRouter (агрегатор: 100+ моделей)\n'
    printf '      9  - Cohere\n'
    printf '      10 - Together AI\n'
    printf '      11 - Fireworks AI\n'
    printf '      12 - Cerebras (быстрый инференс)\n'
    printf '      13 - Perplexity\n'
    printf '      14 - Nebius\n'
    printf '      15 - Ollama (локальные модели, без ключа)\n'
    printf '      Enter - пропустить, настроить позже\n\n'
    read -r -p "    Выберите провайдера (номер или Enter): " choice || choice=""

    ENV_LINES=()
    HAS_OPENAI_KEY=0
    case "$choice" in
        1)
            read -r -p "    Вставьте Anthropic API ключ (sk-ant-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_ANTHROPIC_API_KEY=${key// /}")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        2)
            read -r -p "    Вставьте OpenAI API ключ (sk-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=openai")
                ENV_LINES+=("CAMPAIGN_OPENAI_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=gpt-4o-mini")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=gpt-4o-mini")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=gpt-4o")
                HAS_OPENAI_KEY=1
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        3)
            read -r -p "    Вставьте Google API ключ (AIza...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=google")
                ENV_LINES+=("CAMPAIGN_GOOGLE_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=gemini-2.0-flash")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=gemini-2.0-flash")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=gemini-2.5-pro-preview-05-06")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        4)
            read -r -p "    Вставьте Mistral API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=mistral")
                ENV_LINES+=("CAMPAIGN_MISTRAL_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=mistral-small-latest")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=mistral-small-latest")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=mistral-large-latest")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        5)
            read -r -p "    Вставьте DeepSeek API ключ (sk-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=deepseek")
                ENV_LINES+=("CAMPAIGN_DEEPSEEK_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=deepseek-chat")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=deepseek-chat")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=deepseek-reasoner")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        6)
            read -r -p "    Вставьте Groq API ключ (gsk_...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=groq")
                ENV_LINES+=("CAMPAIGN_GROQ_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=llama-3.3-70b-versatile")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=llama-3.3-70b-versatile")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=llama-3.3-70b-versatile")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        7)
            read -r -p "    Вставьте xAI API ключ (xai-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=xai")
                ENV_LINES+=("CAMPAIGN_XAI_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=grok-3-mini")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=grok-3-mini")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=grok-3")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        8)
            read -r -p "    Вставьте OpenRouter API ключ (sk-or-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=openrouter")
                ENV_LINES+=("CAMPAIGN_OPENROUTER_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=anthropic/claude-3.5-haiku")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=anthropic/claude-3.5-haiku")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=anthropic/claude-sonnet-4")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        9)
            read -r -p "    Вставьте Cohere API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=cohere")
                ENV_LINES+=("CAMPAIGN_COHERE_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=command-r-plus")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=command-r")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=command-r-plus")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        10)
            read -r -p "    Вставьте Together AI API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=together")
                ENV_LINES+=("CAMPAIGN_TOGETHER_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=meta-llama/Llama-3-70b-chat-hf")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=meta-llama/Llama-3-8b-chat-hf")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=meta-llama/Llama-3-70b-chat-hf")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        11)
            read -r -p "    Вставьте Fireworks AI API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=fireworks")
                ENV_LINES+=("CAMPAIGN_FIREWORKS_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=accounts/fireworks/models/llama-v3p3-70b-instruct")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=accounts/fireworks/models/llama-v3p3-70b-instruct")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=accounts/fireworks/models/llama-v3p3-70b-instruct")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        12)
            read -r -p "    Вставьте Cerebras API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=cerebras")
                ENV_LINES+=("CAMPAIGN_CEREBRAS_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=llama-3.3-70b")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=llama-3.3-70b")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=llama-3.3-70b")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        13)
            read -r -p "    Вставьте Perplexity API ключ (pplx-...): " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=perplexity")
                ENV_LINES+=("CAMPAIGN_PERPLEXITY_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=sonar")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=sonar")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=sonar-pro")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        14)
            read -r -p "    Вставьте Nebius API ключ: " key || key=""
            if [ -n "${key// /}" ]; then
                ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=nebius")
                ENV_LINES+=("CAMPAIGN_NEBIUS_API_KEY=${key// /}")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=meta-llama/Llama-3-70B-Instruct")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=meta-llama/Llama-3-8B-Instruct")
                ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=meta-llama/Llama-3-70B-Instruct")
            else
                warn "Ключ пустой - пропускаю настройку."
            fi
            ;;
        15)
            read -r -p "    Имя модели Ollama (Enter = llama3.3; модель должна быть скачана: ollama pull <имя>): " model || model=""
            model="${model// /}"
            [ -n "$model" ] || model="llama3.3"
            ENV_LINES+=("CAMPAIGN_LLM_PROVIDER=ollama")
            ENV_LINES+=("CAMPAIGN_LLM_MODEL_ASSISTANT=$model")
            ENV_LINES+=("CAMPAIGN_LLM_MODEL_EXTRACTION=$model")
            ENV_LINES+=("CAMPAIGN_LLM_MODEL_GENERATION=$model")
            ;;
    esac

    if [ "${#ENV_LINES[@]}" -gt 0 ]; then
        printf '\n'
        printf '      Векторный поиск по лору (эмбеддинги):\n'
        printf '      1 - Локальная модель (по умолчанию; лор не покидает машину)\n'
        printf '      2 - OpenAI (качественнее, но текст лора уходит в OpenAI)\n'
        printf '      3 - Google Gemini\n'
        printf '      4 - Mistral\n'
        printf '      5 - Cohere\n'
        printf '      6 - Together AI\n'
        printf '      7 - Fireworks AI\n'
        printf '      8 - Ollama (локальные модели через Ollama)\n'
        printf '      9 - Отключить (ассистент будет хуже находить связанный лор)\n\n'
        read -r -p "    Выберите (1-9 или Enter = 1): " emb_choice || emb_choice=""
        case "$emb_choice" in
            2)
                if [ "$HAS_OPENAI_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте OpenAI API ключ для эмбеддингов (sk-...): " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_OPENAI_API_KEY=${emb_key// /}")
                        HAS_OPENAI_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_OPENAI_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=openai")
                fi
                ;;
            3)
                HAS_GOOGLE_KEY=0
                for line in "${ENV_LINES[@]}"; do
                    case "$line" in CAMPAIGN_GOOGLE_API_KEY=*) HAS_GOOGLE_KEY=1 ;; esac
                done
                if [ "$HAS_GOOGLE_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте Google API ключ для эмбеддингов (AIza...): " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_GOOGLE_API_KEY=${emb_key// /}")
                        HAS_GOOGLE_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_GOOGLE_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=google")
                fi
                ;;
            4)
                HAS_MISTRAL_KEY=0
                for line in "${ENV_LINES[@]}"; do
                    case "$line" in CAMPAIGN_MISTRAL_API_KEY=*) HAS_MISTRAL_KEY=1 ;; esac
                done
                if [ "$HAS_MISTRAL_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте Mistral API ключ для эмбеддингов: " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_MISTRAL_API_KEY=${emb_key// /}")
                        HAS_MISTRAL_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_MISTRAL_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=mistral")
                fi
                ;;
            5)
                HAS_COHERE_KEY=0
                for line in "${ENV_LINES[@]}"; do
                    case "$line" in CAMPAIGN_COHERE_API_KEY=*) HAS_COHERE_KEY=1 ;; esac
                done
                if [ "$HAS_COHERE_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте Cohere API ключ для эмбеддингов: " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_COHERE_API_KEY=${emb_key// /}")
                        HAS_COHERE_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_COHERE_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=cohere")
                fi
                ;;
            6)
                HAS_TOGETHER_KEY=0
                for line in "${ENV_LINES[@]}"; do
                    case "$line" in CAMPAIGN_TOGETHER_API_KEY=*) HAS_TOGETHER_KEY=1 ;; esac
                done
                if [ "$HAS_TOGETHER_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте Together AI API ключ для эмбеддингов: " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_TOGETHER_API_KEY=${emb_key// /}")
                        HAS_TOGETHER_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_TOGETHER_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=together")
                fi
                ;;
            7)
                HAS_FIREWORKS_KEY=0
                for line in "${ENV_LINES[@]}"; do
                    case "$line" in CAMPAIGN_FIREWORKS_API_KEY=*) HAS_FIREWORKS_KEY=1 ;; esac
                done
                if [ "$HAS_FIREWORKS_KEY" -eq 0 ]; then
                    read -r -p "    Вставьте Fireworks AI API ключ для эмбеддингов: " emb_key || emb_key=""
                    if [ -n "${emb_key// /}" ]; then
                        ENV_LINES+=("CAMPAIGN_FIREWORKS_API_KEY=${emb_key// /}")
                        HAS_FIREWORKS_KEY=1
                    else
                        warn "Ключ пустой - оставляю локальные эмбеддинги."
                    fi
                fi
                if [ "$HAS_FIREWORKS_KEY" -eq 1 ]; then
                    ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=fireworks")
                fi
                ;;
            8)
                read -r -p "    Имя модели Ollama для эмбеддингов (Enter = nomic-embed-text): " emb_model || emb_model=""
                emb_model="${emb_model// /}"
                [ -n "$emb_model" ] || emb_model="nomic-embed-text"
                ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=ollama")
                ENV_LINES+=("CAMPAIGN_OLLAMA_EMBEDDING_MODEL=$emb_model")
                ;;
            9)
                ENV_LINES+=("CAMPAIGN_EMBEDDING_PROVIDER=disabled")
                ;;
            # Enter / anything else = local, the Settings default: nothing to write.
        esac

        printf '%s\n' "${ENV_LINES[@]}" > "$ENV_FILE"
        ok "Настройки сохранены в backend/.env (там же их можно поменять)."
    else
        cp "$BACKEND/.env.example" "$ENV_FILE"
        ok "Пропущено. AI можно настроить позже в backend/.env (см. подсказки внутри файла)."
    fi
fi

# --- 4. Dependencies ----------------------------------------------------------

step "Устанавливаю зависимости бэкенда (uv sync)..."
(cd "$BACKEND" && uv sync) || die "uv sync завершился с ошибкой - смотрите сообщения выше."
ok "Бэкенд готов."

step "Устанавливаю зависимости фронтенда (npm install)..."
(cd "$FRONTEND" && npm install --no-fund --no-audit) || die "npm install завершился с ошибкой - смотрите сообщения выше."
ok "Фронтенд готов."

# The backend serves this build itself, so there is one process and one port:
# one firewall rule, one port to forward, and no CORS at all.
step "Собираю интерфейс..."
(cd "$FRONTEND" && npm run build) || die "Сборка интерфейса не удалась - смотрите сообщения выше."
ok "Интерфейс собран."

# --- 5. LAN play mode (opt-in) --------------------------------------------------

detect_lan_ip() {
    # The address players on this network can reach us at — which is the one
    # facing the real router, not necessarily the one that reaches the
    # internet: a VPN or virtual adapter often owns the default route, and its
    # address is invisible to everyone else in the house.
    local gateway ip

    # Linux: ask for the route to the default gateway, and take its source.
    if command -v ip >/dev/null 2>&1; then
        gateway="$(ip route show default 2>/dev/null | awk '/via/ {print $3; exit}')"
        if [ -n "$gateway" ]; then
            ip="$(ip route get "$gateway" 2>/dev/null |
                awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
            [ -n "$ip" ] && { printf '%s' "$ip"; return 0; }
        fi
    fi

    # macOS: the interface carrying the default route, then its address.
    if command -v route >/dev/null 2>&1 && command -v ipconfig >/dev/null 2>&1; then
        local iface
        iface="$(route -n get default 2>/dev/null | awk '/interface:/ {print $2; exit}')"
        if [ -n "$iface" ]; then
            ip="$(ipconfig getifaddr "$iface" 2>/dev/null)"
            [ -n "$ip" ] && { printf '%s' "$ip"; return 0; }
        fi
    fi

    # Fallbacks: whatever reaches the wider internet, then the first address.
    if command -v ip >/dev/null 2>&1; then
        ip="$(ip route get 1.1.1.1 2>/dev/null |
            awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
        [ -n "$ip" ] && { printf '%s' "$ip"; return 0; }
    fi
    hostname -I 2>/dev/null | awk '{print $1}'
}

# The server reads TLS settings itself (see loregraph/server.py); this only
# needs to know the scheme to print the right links.
if [ -n "$(conf_value "$BACKEND/.env" CAMPAIGN_SSL_CERTFILE)" ] &&
   [ -n "$(conf_value "$BACKEND/.env" CAMPAIGN_SSL_KEYFILE)" ]; then
    APP_SCHEME="https"
fi
LOCAL_URL="${APP_SCHEME}://127.0.0.1:${APP_PORT}"
FRONTEND_URL="$LOCAL_URL"

BIND_HOST="127.0.0.1"
if [ "$LAN" -eq 1 ]; then
    if [ -z "$LAN_HOST" ]; then
        LAN_HOST="$(detect_lan_ip)"
        [ -n "$LAN_HOST" ] || die "Не удалось определить IP в сети. Укажите: bash start.sh --lan --lan-host 192.168.1.5"
        ok "Адрес в сети: $LAN_HOST (изменить: --lan-host <адрес>)"
    fi
    BIND_HOST="0.0.0.0"
    FRONTEND_URL="${APP_SCHEME}://${LAN_HOST}:${APP_PORT}"
    export CAMPAIGN_PLAY_MODE_ENABLED=1
    export CAMPAIGN_PLAY_HOST="$LAN_HOST"
    [ "$INTERNET" -eq 1 ] && export CAMPAIGN_INTERNET_MODE_ENABLED=1
fi

# --- 6. Launch ------------------------------------------------------------------

step "Запускаю Loregraph..."

port_busy() { ( exec 3<>"/dev/tcp/127.0.0.1/$1" ) 2>/dev/null; }
if port_busy "$APP_PORT"; then
    die "Порт $APP_PORT уже занят. Возможно, Loregraph уже запущен - проверьте браузер: $LOCAL_URL"
fi

echo "    Первый запуск может занять пару минут (скачивается локальная embedding-модель)."

# One process, one port: the backend serves the built interface too.
# loregraph-serve (not uvicorn directly) so TLS is read from settings in one
# place instead of being parsed out of .env by each launcher script.
(cd "$BACKEND" && exec uv run loregraph-serve --host "$BIND_HOST" --port "$APP_PORT") &
BACK_PID=$!

cleanup() {
    trap - INT TERM EXIT
    printf '\n\033[36mОстанавливаю Loregraph...\033[0m\n'
    kill "$BACK_PID" 2>/dev/null
    wait "$BACK_PID" 2>/dev/null
    # Belt and braces: anything left in our process group.
    kill 0 2>/dev/null
}
trap cleanup INT TERM EXIT

# Wait for the health endpoint before opening the browser.
HEALTHY=0
i=0
while [ "$i" -lt 120 ]; do
    kill -0 "$BACK_PID" 2>/dev/null || die "Loregraph завершился с ошибкой - смотрите сообщения выше."
    # -k: a self-signed certificate is the common case for a home game, and
    # this poll only talks to our own just-started server.
    if curl -fsSk -m 2 "$LOCAL_URL/api/health" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
    i=$((i + 1))
done
[ "$HEALTHY" -eq 1 ] || die "Loregraph не ответил за 4 минуты - смотрите сообщения выше."

# The DM opens the app on this machine via localhost even in LAN mode.
if command -v open >/dev/null 2>&1; then
    open "$LOCAL_URL"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$LOCAL_URL" >/dev/null 2>&1 || true
fi

# Ask the app where it actually ended up reachable, so this banner and the
# links in the interface can never disagree (see api/routers/network.py).
NET_JSON="$(curl -fsSk -m 5 "$LOCAL_URL/api/network" 2>/dev/null || true)"
net_field() { printf '%s' "$NET_JSON" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"; }
NET_BASE_URL="$(net_field base_url)"
UPNP_OUTCOME="$(net_field outcome)"
EXTERNAL_IP="$(net_field external_ip)"
[ -n "$NET_BASE_URL" ] && FRONTEND_URL="$NET_BASE_URL"

printf '\n\033[32m=========================================================\033[0m\n'
printf '\033[32m  Loregraph запущен: %s\033[0m\n' "$LOCAL_URL"
if [ "$INTERNET" -eq 1 ]; then
    case "$UPNP_OUTCOME" in
        mapped)
            printf '\033[32m  Доступ из интернета настроен автоматически.\033[0m\n'
            ;;
        cgnat)
            warn "Доступ из интернета невозможен: провайдер выдал адрес"
            warn "$EXTERNAL_IP - это общий адрес (CGNAT), а не ваш личный."
            warn "Закажите у провайдера 'белый IP' либо используйте Tailscale."
            warn "По локальной сети всё работает."
            ;;
        no_router)
            warn "Роутер не ответил на UPnP - скорее всего он выключен в его настройках."
            warn "Включите UPnP или пробросьте порт $APP_PORT вручную. По сети всё работает."
            ;;
        refused)
            warn "Роутер отказался пробрасывать порт. Пробросьте порт $APP_PORT вручную."
            warn "По локальной сети всё работает."
            ;;
        *)
            warn "Не удалось настроить доступ из интернета. По локальной сети всё работает."
            ;;
    esac
fi
if [ "$LAN" -eq 1 ]; then
    printf '\033[32m  Режим игры по сети включён.\033[0m\n'
    printf '\033[32m  Ссылки-приглашения создавайте в: Настройки проекта -> Игроки.\033[0m\n'
    printf '\033[32m  Игроки подключаются на: %s\033[0m\n' "$FRONTEND_URL"
    printf '\033[33m  Если не открывается - разрешите порт %s в брандмауэре.\033[0m\n' "$APP_PORT"
    if [ "$APP_SCHEME" = "https" ]; then
        printf '\033[33m  ВНИМАНИЕ: ваш мир доступен всем в этой сети по ссылкам.\033[0m\n'
        printf '\033[33m  Отзывайте ссылки, когда они не нужны.\033[0m\n'
    else
        printf '\033[33m  ВНИМАНИЕ: ваш мир доступен всем в этой сети по ссылкам,\033[0m\n'
        printf '\033[33m  трафик не шифруется. Отзывайте ссылки, когда они не нужны.\033[0m\n'
    fi
fi
printf '\033[32m  Чтобы остановить - нажмите Ctrl+C\033[0m\n'
printf '\033[32m=========================================================\033[0m\n'

# Keep the script alive; periodically check the remote for new commits.
# The console is told once, but the status file is refreshed on every check
# so the in-app updates section doesn't go stale.
UPDATE_ANNOUNCED=0
SINCE_CHECK=0
while :; do
    sleep 15
    SINCE_CHECK=$((SINCE_CHECK + 15))
    if ! kill -0 "$BACK_PID" 2>/dev/null; then
        warn "Loregraph завершился, останавливаю."
        break
    fi
    if [ "$SINCE_CHECK" -ge "$UPDATE_CHECK_INTERVAL" ] && [ "$HAS_GIT" -eq 1 ] && [ "$(update_mode)" != "never" ]; then
        SINCE_CHECK=0
        LOCAL_REV="$(cd "$ROOT" && git rev-parse HEAD)"
        REMOTE_REV="$(cd "$ROOT" && git fetch --quiet 2>/dev/null; git rev-parse --verify --quiet '@{u}' || true)"
        if [ -n "$REMOTE_REV" ] && [ "$LOCAL_REV" != "$REMOTE_REV" ]; then
            UPSTREAM="$(cd "$ROOT" && git rev-parse --abbrev-ref --symbolic-full-name '@{u}')"
            LATEST_VERSION="$(remote_version "$UPSTREAM")"
            CHANGELOG_SECTION="$(
                (cd "$ROOT" && git --no-pager show "$UPSTREAM:CHANGELOG.md" 2>/dev/null) |
                    bash "$ROOT/scripts/changelog-section.sh" "v$LATEST_VERSION" - 2>/dev/null || true
            )"
            DIRTY=0
            [ -n "$(cd "$ROOT" && git status --porcelain)" ] && DIRTY=1
            write_update_status 1 "$DIRTY" "$LOCAL_VERSION" "$LATEST_VERSION" "$CHANGELOG_SECTION"
            if [ "$UPDATE_ANNOUNCED" -eq 0 ]; then
                printf '\n'
                warn "Вышло обновление Loregraph! Остановите (Ctrl+C) и запустите start.sh заново, чтобы обновиться."
                UPDATE_ANNOUNCED=1
            fi
        else
            write_update_status 1 0 "$LOCAL_VERSION" "$LOCAL_VERSION" ""
        fi
    fi
done
