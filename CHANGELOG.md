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

## [0.2.0] — 2026-07-22

The assistant can work on relationships. Asked to connect two characters that
already exist, it used to invent a third one to hang the connection on —
because a relationship's starting point could only ever be an entity from the
same draft. Relationships are now a first-class thing the agent proposes,
changes and removes, and external MCP clients can do the same.

### Added

- **`manage_relationships` skill.** Ask the assistant to link, re-type,
  reverse or unlink entities that already exist and it proposes exactly that —
  no invented entities, and far cheaper than routing the request through lore
  generation.
- **Relationship operations in review.** A proposal can now create, change or
  remove connections, each shown with what it does and, for a change, what the
  connection says today. A proposal may consist of nothing but these.
- **Contradiction warnings at review.** Proposing `enemy_of` for a pair the
  world already records as `ally_of` is flagged, as is proposing a connection
  that already exists. Both are warnings, not refusals — a falling-out is a
  legitimate story beat and only you can tell it from a mistake.
- **MCP relationship tools:** `list_edges`, `update_edge`, `delete_edge` and
  `update_entity`; `get_entity_graph` now returns each relationship's id.

### Changed

- **Both ends of a relationship are now equal.** Either side may be an entity
  from the draft or one that already exists. Previously only the target side
  could be an existing entity.
- **Existing relationships reach the assistant with their ids**, and no longer
  only when a graph entity is in focus — a search-driven run used to see none
  of them at all, which is exactly when it guessed at connections that were
  already recorded.
- **MCP delete policy.** Entities and projects still cannot be deleted through
  MCP. Removing a relationship now can be: it destroys no text, only a link
  that can be recreated, and withholding it while allowing re-typing was a
  pretense. Write tools still require your client to confirm with you first —
  do not enable auto-approve.

### Fixed

- "Request changes" on a proposed entity edit ran the lore generator over it
  instead of the editor.
- The graph view kept showing old connections after a commit that only changed
  relationships.

### Migration

None. Sessions interrupted mid-review under 0.1.0 resume normally — the draft
format was extended, not broken.

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

[Unreleased]: https://github.com/HadeSxGod1337/loregraph/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.2.0
[0.1.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.1.0
