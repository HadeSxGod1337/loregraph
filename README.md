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
(planned) an AI agent proposes NPCs, factions, and story hooks grounded in your
existing lore via hybrid retrieval (vector + graph), with a human-in-the-loop review
gate before anything is written to canon. Foundry VTT and Markdown are export
connectors, not the core of the product.

**Status**: the manual entity/graph editor (v0) is done and usable. The LangGraph
agent layer described above is planned, not yet built.

## Stack

- **Backend**: FastAPI + Pydantic v2, SQLAlchemy 2.0 (async) + SQLite, `uv` for
  dependency management.
- **Frontend**: React 19 + TypeScript + Vite, `@xyflow/react` for the graph canvas,
  Tiptap for rich text, `@tanstack/react-query` for data fetching.
- **Planned**: LangGraph agent orchestration, Chroma (vector store), networkx (graph
  store), Anthropic SDK as the primary LLM provider (BYOK).

## Running locally

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
