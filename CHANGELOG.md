# Changelog

All notable changes to Loregraph are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Loregraph is an application, not a library, so version numbers describe impact on
**you and your campaign data** rather than an API contract:

- **MAJOR** — on-disk data or agent state changed in a way that needs manual action.
- **MINOR** — new features; existing campaigns migrate automatically on first start.
- **PATCH** — fixes only.

While the version is `0.x`, MINOR acts as the effective major.

Every entry that touches stored campaigns carries a **Migration** note. Read those
before upgrading.

## [Unreleased]

## [0.1.0] — 2026-07-22

First tagged release. Everything below is the state of the app as of this tag.

### Added

- **Entity + graph editor.** Campaigns are stored as entities (NPCs, factions,
  locations, items — any type) connected by typed, directional relationships.
  Full manual CRUD works standalone, with no LLM key configured.
- **Graph view.** Force-directed layout with All / Focused modes, click-to-expand
  neighbours in place, persisted node positions, inline edge creation and editing.
- **AI Assistant (optional, BYOK).** A conversational LangGraph agent that answers
  questions grounded in retrieved lore, asks clarifying questions back, and drafts
  whole batches of entities plus the relationship web between them and existing
  lore. Pipeline: hybrid retrieve → duplicate checks → batch draft → grounding
  verification → review → commit.
- **Human-in-the-loop review gate.** Nothing reaches canon without review. Batch
  review supports approve (with per-entity edits and exclusions), reject, and
  request-changes for iterative revision of the same draft.
- **Streaming turns.** Pipeline stages and answer tokens stream over SSE, backed by
  an in-process project-scoped event bus.
- **Multi-provider LLM support.** Anthropic, OpenAI, Ollama, and other providers via
  LangChain adapters; configured through `backend/.env`.
- **Local embeddings.** Semantic retrieval uses a local multilingual model,
  downloaded on first use — lore never leaves the machine except for the LLM calls
  you explicitly configure.
- **MCP integration.** Generic passthrough to any MCP server as an agent tool
  source, with progressive disclosure. Ships a stdio MCP server (`loregraph-mcp`)
  for external MCP clients.
- **Knowledge base and bulk import.** Document handling, attachment processing,
  dedicated import jobs, and native LSS character sheet parsing with live embed.
- **Rich text with `[[wikilinks]]`** resolving to entity references.
- **Observability.** Token usage and cost tracking, plus optional LangSmith and
  Langfuse tracing.
- **Evaluation framework** for retrieval and hallucination metrics.
- **One-click launcher.** `start.bat` / `start.sh` bootstrap dependencies and start
  both services.

### Migration

None — this is the first release.

[Unreleased]: https://github.com/HadeSxGod1337/loregraph/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.1.0
