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

### Added

- **Limited player access.** You can now let your players see the world you
  choose to show them. Reveal a card (one click from the board, or the "Player
  access" panel on any entity), write a separate text meant for players, and
  tick which of its fields they may see — everything else stays hidden. Each
  player gets an invite link; opening it shows only the revealed cards and a
  read-only board, and lets them keep their own notes, public to the party or
  private (you see all of them). Manage players under **Project settings →
  Players**: invite, rotate a leaked link, revoke (keeps their notes), or
  delete (removes them). Nothing is shown to anyone until you reveal it.
- **Play over the local network.** Launch with `start.bat --lan` (or
  `start.sh --lan`) and the app binds to your network so players can open their
  invite links from their own devices. The launcher prints the link and a
  reminder that, in this mode, the world is reachable by anyone on the network
  over unencrypted traffic — revoke links when a session ends. Without the
  flag, nothing changes: the app stays on localhost.
- **Updates ask before they happen.** When a git-cloned copy finds a newer
  version on start, the launcher shows what version it is and the changelog for
  it, then offers *update now*, *later*, or *skip this version* — and remembers
  the choice (ask / automatic / never) in `backend/data/update.conf`. The
  in-app preferences popover shows the current version, any waiting update, and
  lets you change the mode. Double-clicking `start.bat` stays unattended: an
  unanswered prompt just continues without updating after 30 seconds.

- **A real editor toolbar for rich text fields.** Block format (paragraph,
  four heading levels, quote, code block), font family and size, text colour
  and highlighter, alignment, checklists, indent/outdent, links, tables and a
  clear-formatting button, next to the bold/italic/list controls that were
  there before. Everything is one click away with a tooltip; nothing changed
  about how field values are stored.
- **Tables and checklists survive Markdown export/import.** They round-trip as
  GFM tables and `- [x]` items, and `==highlighted==` text keeps its
  highlight. Text colour, font and alignment are presentation-only and are
  dropped on Markdown export — the text itself always survives.
- **The modifier next to a stat is no longer hard-wired to D&D.** A
  stat-and-modifier block now carries its own formula (over `value`, its own
  score, plus any other field on the template), or none at all for systems
  that have no such notion. Left unset it still uses the 5e rule, so nothing
  on an existing sheet moves.
- **Computed values choose whether to show a sign.** "+3" says "add this to a
  roll" — right for a saving throw, wrong for a passive score. Per block, in
  the designer.
- **Import a whole party's character sheets in one go.** "Импорт листов
  персонажей" now sits on the Entities page, where the party is, instead of
  behind a connection you first had to create in project settings — the
  button makes that connection itself. Drag in every `.json` the players
  exported from longstoryshort.app at once; the dialog leads with the file
  drop (the path that always works) and folds the share link — which needs
  the site to answer, and it does not — into "other ways". The result names
  every character that came in, and a file that fails to parse costs that one
  character, not the run.

### Changed

- **Integrations are their own section in the left rail.** They were a tab
  inside project settings — a place you had to remember the way to, for
  something you use during a session rather than configure once.
- **An imported character arrives as a character sheet.** Import binds the
  party-member template — your own if the project has one, the built-in
  otherwise — so a freshly imported party is readable and printable without
  binding a template by hand, once per character. Characters imported earlier
  get theirs on their next refresh.
- **The two switches on a connection say what they do, and only appear where
  they do something.** "Use for grounding" is now "Let the assistant read this
  source" and "Auto-push after commit" is "Export automatically after
  approval", each with a line under it explaining the consequence. Both used
  to be offered on every connection, including ones that can neither be read
  by the assistant nor export anything — as did the Export and Import buttons,
  which answered 422 on connections with no such capability. Every action and
  switch is now gated on what the connector actually supports.

### Fixed

- **Grounding through LongStoryShort no longer silently contributes nothing.**
  LSS publishes no JSON endpoint we may call, so the live fetch fails for
  everyone — and the source answered with an empty list, making the switch a
  no-op. It falls back to the sheet as last imported, labelled as such so
  stale HP can't read as current.
- **The entity list refreshes after an import.** It kept showing the party as
  it was before.

- **A stray click no longer throws away a template you were designing.** The
  designer closed on any click that landed on the backdrop, and on Escape,
  with no warning and no way back. Both now ask first. The sheet modal does
  the same while you are filling one in.
- **A refused template save says why.** The designer covers the settings page
  behind it, so a 422 from the server was invisible — the button simply
  appeared to do nothing. The reason now shows inside the designer, and the
  two mistakes the server cannot describe usefully (a blank field key, two
  fields sharing one) are caught before saving, with the offending chip
  marked in the field palette.
- **The field list under a block only offers fields that block can draw.**
  Binding a stat box to a text field was possible right up until the save
  failed. An unbound block also showed the first field as though it were
  selected.
- **Fields the template declares but an entity never had can be filled in.**
  A template that gained a field left every older entity with a permanently
  read-only slot for it, and no plain field editor to fall back on (a bound
  template hides it). Typing into the slot now creates the field.
- **A tracker's maximum is editable.** `HP / max HP` counted the max as
  placed, so it never appeared under "Прочие поля" either — there was no
  screen anywhere that could change it.
- **Rating dots and sheet tabs work from the keyboard.** Dots were `<span>`s
  with a click handler and no tab stop; the tab bar had no arrow-key
  navigation and no link between a tab and its panel.
- **Toolbar buttons show what is actually active.** Bold, lists, headings and
  the rest never lit up while typing and never turned off again — the toolbar
  was frozen at whatever the document looked like when the editor opened, so
  the only way to see a state change was to select text first. It now follows
  the cursor.

### Migration

- The database gains two tables (players, player notes) and two entity columns,
  added automatically on first start — nothing to do. **Every entity starts
  hidden**: players see nothing until you reveal it.
- Project export now carries each entity's reveal state, player text and field
  whitelist. Files exported before this version import cleanly, as all-hidden.
  Players and their notes are **not** part of an export — invite tokens and
  personal notes never travel in a file; re-invite players after importing a
  project elsewhere.
- Serving attachments moved from a static mount to an access-checked route.
  URLs are unchanged; there is nothing to migrate. If you run behind a reverse
  proxy, set `CAMPAIGN_TRUST_LOOPBACK=false` and put real authentication in
  front — loopback trust assumes the peer address is the real client.

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
