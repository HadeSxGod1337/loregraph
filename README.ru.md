<p align="center">
  <img src="frontend/public/favicon.svg" width="72" height="72" alt="Логотип Loregraph">
</p>

<h1 align="center">Loregraph</h1>

<p align="center">
  Локальное self-hosted приложение для подготовки и ведения настольных RPG-кампаний —
  сущности и связи в графе, поверх — слой AI-агента.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-5c6ac4?style=flat-square" alt="Лицензия: PolyForm Noncommercial"></a>
  <a href="backend/pyproject.toml"><img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="backend/pyproject.toml"><img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="frontend/package.json"><img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React 19"></a>
  <a href="frontend/package.json"><img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript"></a>
  <a href="backend/pyproject.toml"><img src="https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=flat-square&logo=langchain&logoColor=white" alt="LangGraph"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/self--hosted-local%20first-2ea44f?style=flat-square" alt="Self-hosted, локально">
  <img src="https://img.shields.io/badge/BYOK-свой%20API--ключ-8b5cf6?style=flat-square" alt="BYOK">
  <img src="https://img.shields.io/badge/HITL-ревью%20человеком-f97316?style=flat-square" alt="Human-in-the-loop">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-4b5563?style=flat-square" alt="Windows, macOS, Linux">
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Русский</b>
</p>

---

## Что это

Loregraph хранит кампанию как **сущности** (NPC, фракции, локации, предметы —
что угодно), связанные **графом** типизированных отношений. Редактируете вручную
или AI-агент предлагает новые сущности и связи, опираясь на уже существующий лор
через гибридный retrieval (vector + graph), с обязательным human-in-the-loop
ревью перед записью в канон. Foundry VTT и Markdown — коннекторы экспорта, не
ядро продукта.

**Статус**: ручной редактор сущностей/графа (v0) и разговорный слой агента уже
работают. AI Assistant — это чат: отвечает на вопросы о вашем мире (только на
основе retrieved-лора через инструменты, не из «памяти» модели), задаёт уточняющие
вопросы и за один прогон создаёт целые куски мира — пакет сущностей (типы и
количество выбирает сам) плюс сеть связей между ними и существующим лором
(LangGraph: цикл ассистента с read-tools → propose-пайплайн: hybrid retrieve →
проверка дубликатов → batch draft → grounding verification → review → commit).
Ходы стримятся по SSE — стадии пайплайна и токены ответа видны в реальном времени.
Inline batch review: approve (с правками/исключениями по сущностям), reject и
**request changes** — итеративная доработка того же драфта. Ассистент живёт
drawer'ом прямо в виде графа (пустой мир открывает его автоматически) и на
отдельной вкладке. Также: `[[wikilink]]`-ссылки на сущности в rich text и stdio
MCP-сервер (`loregraph-mcp`) для внешних MCP-клиентов. Многошаговая подготовка
сессий (оркестратор + параллельные воркеры) и коннекторы Foundry/Markdown — в
планах.

### Настройка AI Assistant (опционально, BYOK)

Создайте `backend/.env` с `CAMPAIGN_ANTHROPIC_API_KEY=sk-ant-...` (или
`CAMPAIGN_LLM_PROVIDER=openai|ollama` и соответствующие настройки, см.
`backend/src/loregraph/config.py`). Без ключа ручной редактор работает полностью;
на вкладке Assistant показываются инструкции по настройке. Семантический retrieval
по умолчанию использует локальную многоязычную embedding-модель (скачивается при
первом запуске); лор не покидает вашу машину, кроме LLM-вызовов, которые вы сами
настроите.

## Стек

- **Backend**: FastAPI + Pydantic v2, SQLAlchemy 2.0 (async) + SQLite, `uv` для
  управления зависимостями.
- **Frontend**: React 19 + TypeScript + Vite, `@xyflow/react` для canvas графа,
  Tiptap для rich text, `@tanstack/react-query` для загрузки данных.
- **В планах**: оркестрация LangGraph-агента, Chroma (vector store), networkx
  (graph store), Anthropic SDK как основной LLM-провайдер (BYOK).

## Локальный запуск

### Быстрый старт (без dev-инструментов)

- **Windows**: двойной клик по `start.bat` в корне репозитория.
- **macOS / Linux**: `./start.sh` (или `bash start.sh`) в корне репозитория.

Скрипт ставит недостающие инструменты (`uv`, Node.js), подтягивает обновления из
git, устанавливает зависимости, при первом запуске предлагает выбрать LLM-провайдера
(Anthropic, OpenAI или локальный Ollama) и источник эмбеддингов — или Enter, чтобы
пропустить и настроить ассистента позже — затем поднимает оба сервера и открывает
приложение в браузере. Закройте окно консоли (или Ctrl+C на macOS/Linux), чтобы
остановить всё. Пока работает, периодически проверяет новые коммиты и сообщает,
когда перезапуск подтянет обновление.

### Backend

```bash
cd backend
uv sync
uv run uvicorn loregraph.main:app --reload
```

Слушает `http://localhost:8000`. Создайте `backend/.env`, если нужно переопределить
дефолты в `Settings` (см. `backend/src/loregraph/config.py`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Слушает `http://localhost:5173` и ходит в backend на `:8000`.

## Разработка

```bash
# backend
cd backend
uv run pytest
uv run ruff check .
uv run mypy .

# frontend
cd frontend
npx tsc -b
npx oxlint src
npm run build
```

## Лицензия

[PolyForm Noncommercial 1.0.0](LICENSE) — можно свободно использовать, менять и
форкать в некоммерческих целях. Коммерческое использование (включая хостинг как
сервис для других или продажу модифицированной версии) без разрешения запрещено.
