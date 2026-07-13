<p align="center">
  <img src="frontend/public/favicon.svg" width="72" height="72" alt="Loregraph logo">
</p>

<h1 align="center">Loregraph</h1>

<p align="center">
  A local, self-hosted app for preparing and running tabletop RPG campaigns —
  entities and relationships in a graph, with an AI agent layer on top.
</p>

## What this is

Loregraph stores your campaign as **entities** (NPCs, factions, locations, items —
anything) connected by a **graph** of typed relationships. You edit it directly, or
the AI agent proposes new entities and relationships grounded in your existing lore
via hybrid retrieval (vector + graph), with a mandatory human-in-the-loop review
gate before anything is written to canon. Foundry VTT and Markdown are export
connectors, not the core of the product.

**Status**: the manual entity/graph editor (v0) and a conversational agent
layer are usable. The AI Assistant is a chat: it answers questions about
your world (grounded in retrieved lore via tools, never from imagination),
asks clarifying questions back, and creates whole pieces of world in one
run — a batch of entities (it picks types and count itself) plus the
relationship web between them and existing lore (LangGraph: assistant loop
with read tools → propose pipeline: hybrid retrieve → duplicate checks →
batch draft → grounding verification → review → commit). Turns stream over
SSE — you see pipeline stages and answer tokens live. Inline batch review
supports approve (with per-entity edits/exclusions), reject, and **request
changes** — iterative revision of the same draft. The assistant lives as a
drawer right in the graph view (an empty world opens it automatically) and
on its own tab. Also: `[[wikilink]]` entity references in rich text, and a
stdio MCP server (`loregraph-mcp`) for external MCP clients. Multi-step session
preparation (orchestrator + parallel workers) and Foundry/Markdown connectors
are planned.

### AI Assistant setup (optional, BYOK)

Create `backend/.env` with `CAMPAIGN_ANTHROPIC_API_KEY=sk-ant-...` (or
`CAMPAIGN_LLM_PROVIDER=openai|ollama` + matching settings, see
`backend/src/loregraph/config.py`). Without a key the manual editor works
fully; the Assistant tab shows setup instructions. Semantic retrieval uses a
local multilingual embedding model by default (downloaded on first use); the
lore never leaves your machine except for the LLM calls you configure.

## Stack

- **Backend**: FastAPI + Pydantic v2, SQLAlchemy 2.0 (async) + SQLite, `uv` for
  dependency management.
- **Frontend**: React 19 + TypeScript + Vite, `@xyflow/react` for the graph canvas,
  Tiptap for rich text, `@tanstack/react-query` for data fetching.
- **Planned**: LangGraph agent orchestration, Chroma (vector store), networkx (graph
  store), Anthropic SDK as the primary LLM provider (BYOK).

## Running locally

### Quick start (no dev tools required)

- **Windows**: double-click `start.bat` in the repo root.
- **macOS / Linux**: run `./start.sh` (or `bash start.sh`) in the repo root.

Either script installs missing tools (`uv`, Node.js), pulls the latest updates
from git, installs dependencies, lets you pick an LLM provider (Anthropic,
OpenAI, or local Ollama) and embedding source on first run — or press Enter to
skip and configure the AI assistant later — then starts both servers and opens
the app in your browser. Close the console window (or Ctrl+C on macOS/Linux)
to stop everything. While running, it periodically checks for new commits and
tells you when a restart would pick up an update.

### Backend

```bash
cd backend
uv sync
uv run uvicorn loregraph.main:app --reload
```

Runs on `http://localhost:8000`. Create `backend/.env` if you need to override
defaults in `Settings` (see `backend/src/loregraph/config.py`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on `http://localhost:5173` and talks to the backend on `:8000`.

## Development

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

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free to use, modify, and fork for
noncommercial purposes. Commercial use (including hosting it as a service for
others, or selling a modified version) is not permitted without permission.
