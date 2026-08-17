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

## [0.6.0] — 2026-08-17

This release is mostly about the two screens you spend the most time in —
the graph and the assistant panel — plus a public place to see what's next
and say something about it without leaving the app.

### Added

- **Hierarchy collapse on the graph.** Entities with children (a faction and
  its members, a town and its places) get a collapse/expand chevron on the
  graph canvas, using the same containment rules as the Entities list.
  Collapsing a branch hides its descendants and shows how many are folded
  away; "collapse all" / "expand all" live in the graph's overflow menu, and
  the collapsed state is remembered per project.
- **Graph toolbar consolidation.** Zoom, fit, reset and lock are one toolbar
  instead of scattered controls, with an optional grid and snap-to-grid for
  laying out a scene by hand. Edges declutter automatically based on zoom,
  hover and selection instead of staying uniformly dense at every level.
- **One assistant composer.** The input bar, attachments and send controls
  are a single component instead of three kept in sync by hand. The idle
  state and event notices read apart more easily, and the session-history
  menu now follows the app's own theme instead of default browser chrome.
- **Modal project creation.** "New project" opens as a dialog instead of an
  inline form on the projects page, which also gained filtering and a real
  empty state.
- **Entity editor sections.** The edit form is split into jump-to sections
  with delete moved into its own danger zone, instead of one long scroll.
  Creating an entity now stages its icon and shows the card preview before
  the first save. The rich-text toolbar tucks rarely-used actions into an
  overflow menu, and image cropping gained a Fit mode that pads instead of
  cropping.
- **Project Hub & feedback, in-app.** Help has a new support block linking
  to the public Loregraph Project Hub (roadmap, what's next) and a feedback
  form — both public Notion pages, opened in an overlay inside Loregraph via
  Notion's dedicated embed route rather than just a link out. "Open in a new
  tab" stays available in every state, in case an embed doesn't load. A
  compact feedback button also sits in the sidebar footer, since it doesn't
  need a project open the way Help does. No backend involvement — these are
  public URLs, nothing is proxied, and nothing is stored.

### Changed

- Project settings' scrollbar gutter is now always reserved, so opening a
  panel that adds a scrollbar no longer narrows the page by a few pixels.
- The demo build's fake backend returns independent clones of its seed data
  instead of shared references, so editing one demo entity can no longer
  bleed into another.
- The image crop modal's Fit-mode backdrop is a blurred version of the image
  instead of a flat matte color.

## [0.5.0] — 2026-08-14

Create, edit and relate used to be three skills the assistant picked between up
front — the wrong pick was how "fill in this existing character" turned into a
duplicate NPC instead of an edit. This release collapses them into one
proposal pipeline, adds a brainstorm mode that separates inventing ideas from
changing the world, and makes structured generation work against DeepSeek's
reasoning models.

### Added

- **Brainstorm mode.** "Придумай врага для Ордена" now routes to a
  non-mutating skill that generates ideas grounded in existing canon (the
  named faction's goals, allies and enemies) and answers in chat — no review
  gate, no commit, nothing written. A suggested idea never becomes canon on
  its own; "…и добавь его" still routes to the proposal pipeline, and mutation
  intent wins when both are asked for in the same turn.
- **Read-before-write routing.** A read tool bundled with a proposal in the
  same turn now runs first, deferring the proposal so the model reissues it
  with the ids the read produced instead of starting on context it never
  received. A per-turn tool-call ceiling stops a runaway read loop from
  burning the whole budget.
- **Complete relationship listing.** `list_relationships` enumerates a hub
  entity's edges completely and page by page, separating incoming from
  outgoing and reporting the exact total — "show me all of X's connections"
  is now actually completable instead of a truncated first page read as the
  whole neighborhood.
- **DeepSeek structured output.** DeepSeek's reasoning models (`deepseek-
  reasoner`, DeepSeek V4 thinking mode) don't support the tool-forced
  structured output every other provider uses; the generator now resolves a
  per-provider/model capability policy and falls back to JSON mode or raw-JSON
  parsing so generation, extraction and import still return validated,
  schema-checked results. A model that rejects the forced tool choice at
  request time downgrades once for the rest of that run instead of failing
  the turn.
- **Hybrid lore search.** Retrieval reworked onto a hybrid vector + keyword
  ranker with entity-level chunking, so long entities are no longer silently
  truncated to the first ~480 characters before embedding. An exact-name hit
  no longer loses to a poor embedding rank, so several namesakes all surface
  when the assistant needs to ask which one you mean. Dense retrieval
  degrades to the lexical result on an embedding-provider or vector-store
  failure instead of failing the whole search.
- **Stale-index detection.** The app now notices at startup when stored
  vectors were written by a configuration it can no longer read (embedding
  model or chunk layout changed) and surfaces it as a reindex status instead
  of the assistant silently finding nothing.

### Changed

- **One proposal pipeline.** Create, edit and relationship changes are now a
  single `propose_changes` skill and a single review card, instead of the
  assistant guessing create-vs-edit-vs-link up front and two mutually
  exclusive review UIs. Edits go through a real patch (set or remove fields by
  key) instead of a whole-row replace, so template, per-field visibility,
  field types and attachments survive an agent edit instead of being silently
  wiped.
- **Commit preflights against a stale review.** The approved proposal is
  re-validated against the current world immediately before any write: a
  patch target that vanished, a created title that now collides with a
  namesake, or a relationship edge that no longer exists refuses the whole
  proposal cleanly instead of applying it half way.
- **Multi-tool turns are honest.** A tool call the turn didn't actually run is
  now reported as not run, instead of being answered as if it had started.

### Migration

- Agent checkpoint state version bumped (unifying create/edit/link into one
  pipeline changed its shape). Any campaign with a draft paused mid-review
  when you upgrade has that draft reset — resume by asking the assistant
  again. Nothing already committed to a project is affected.
- Existing search indexes are unaffected by the retrieval rework; the
  stale-index check only fires if your embedding configuration itself
  changes.

## [0.4.0] — 2026-08-13

Everything about running the assistant used to mean editing `backend/.env` and
restarting: the provider, the key, which model does what, and — if you ever
changed the embedding model — the search index went stale until you found the
per-project reindex button yourself. This release moves all of that into the
app, and gives the sidebar and the entity list an overhaul that had been
overdue since projects stopped being the only thing in the rail.

### Added

- **AI settings in the app.** A new page in the left rail (`/settings`) sets the
  provider, the API key, one model per task class (assistant / extraction /
  generation), the agent's token budget, and the embedding provider and model —
  without editing `.env` and without a restart. A model change applies to the
  next request; a running generation finishes on the model it started with.
  Each field says where its value came from (`.env` or set here) and can be
  reset back to the file, so "I edited `.env` and nothing happened" has an
  answer on screen.
- **Test before you rely on it.** A "Test" button makes one tiny call with the
  configuration currently in the form — a wrong key, a mistyped model id or an
  Ollama that isn't running now surfaces here instead of mid-generation. The
  embedding test also reports the model's dimensions.
- **Model suggestions from the provider.** Where a provider publishes a model
  list (OpenAI-compatible APIs, Anthropic, Ollama), the model fields suggest
  what is actually available; the field stays free text either way.
- **Automatic reindex after an embedding change.** Vectors from two different
  models are not comparable, so switching models now rebuilds every project's
  search data by itself — entities from SQLite, knowledge-base documents from
  their stored files — with progress on the settings page. It used to be a
  silent loss of retrieval until you found the per-project reindex button.

- **A sidebar that is never empty.** On the project list the rail used to hold
  a logo and three buttons; it now offers your recent projects, and inside a
  project it shows that project's sections. The two are labelled zones —
  *Project* above, *App* below — separated from each other.
- **Search (Ctrl/⌘ K).** Jump to an entity in the open project, or to any
  project by name, without walking the navigation.
- **The assistant's state is visible from anywhere.** A line at the bottom of
  the rail names the model that answers, warns when no API key is set, and
  shows a reindex while it runs. Previously a missing key surfaced only when
  you opened the assistant.
- **Continue where you left off.** The project list leads with the world you
  had open last, and gains a filter once you have more than a handful.

- **The entity list groups itself by your relationships.** A faction that
  `contains` its people — or whose people are `member_of` it — is now a folder
  you can fold, with its members nested inside; a town holds the places
  `located_in` it, however deep the nesting goes. Search still finds a member
  inside a folded folder and opens the way to it, and an entity that belongs to
  two factions is shown in both, marked as such rather than duplicated by
  accident. Two other arrangements are one click away — *by type* and the old
  *flat* list — and the choice is remembered per project. Dragging a row onto
  another row creates the containment relationship for real (with an undo in
  the toast), so the list is a way to edit the graph, not a second place where
  structure lives. Which relationship types count as "inside" is yours to set:
  *Project settings → Grouping* lists the types your world actually uses.

### Changed

- **No more two "Settings".** The project's own settings are now called
  *Project settings* and stay in the project zone; the installation's are
  simply *Settings* at the bottom of the rail.
- **Appearance is a settings section, not a popover.** Theme, accent, language
  and updates each got their own place — the settings page is now tabbed
  (Models · Embeddings · Appearance · Updates · Tracing · Startup), with theme
  previews you can see before choosing. The one control frequent enough to
  stay in the rail is the light/dark/system switch.
- **Collapse is a chevron on the rail's edge**, not an item in the navigation
  list that looked like a fourth place you could go.
- `backend/.env` is now the bootstrap path rather than the only one: it is read
  at startup, and a value set in the UI overrides it. The first-run launcher
  wizard says so when you skip it, and the Assistant's setup card links to the
  settings page instead of printing `.env` snippets.
- `GET /api/agent/config` also reports which model backs each tier.

### Migration

Automatic. A new `app_settings` table is created on first start; installations
that never open the settings page keep running exactly on their `.env`.

## [0.3.1] — 2026-08-12

Installing took about a gigabyte and never said so, and a quarter of that went
somewhere nobody would think to look. This release makes the footprint visible
before it happens, puts the stray part back where it belongs, and gives you a
way to take it all off again.

### Added

- **An uninstaller.** `uninstall.bat` on Windows, `bash uninstall.sh` on
  macOS/Linux. It leads with a report — what is where, with real sizes
  measured on your machine — and only then offers to remove it, one piece at a
  time. Your campaign data is asked about separately and defaults to *no*,
  because it is the one thing here no download can bring back. Tools shared
  with your other projects (uv, Node.js, their package caches) are never
  deleted for you; they are listed with the commands to remove them yourself.
  `--report-only` shows the report and touches nothing.
- **The launcher says what it is about to download.** On a first install it
  lists the sizes and destinations — including the parts that land outside the
  project folder — and waits for you to agree. Pressing Enter continues, so
  double-clicking `start.bat` still works unattended.
- **A "disk space, and how to remove it" section in the README**, in both
  languages, with the same table.

### Fixed

- **Loregraph starts on Apple Silicon.** On an M-series Mac the app died during
  startup with "the greenlet library is required to use this function".
  `greenlet` reached us only as a transitive dependency of SQLAlchemy, whose
  own dependency marker lists the ARM machine as `aarch64` — what Linux
  reports — while macOS reports `arm64`, so it was never installed. We now ask
  for `sqlalchemy[asyncio]`, which requires `greenlet` on every platform.
  Thanks to @VatariShin for the report ([#1]).
- **The search model no longer hides in the system temp folder.** The local
  embedding model (~240 MB, downloaded on first use) was cached wherever
  fastembed defaults to, which on Windows is `%TEMP%`. That is wrong twice
  over: you cannot find it, and Disk Cleanup deletes it — after which the app
  silently downloads the same quarter of a gigabyte again. It now lives in
  `backend/data/models`, next to the rest of the app's data, so deleting the
  project folder really does delete the app.

### Migration

- The model moves on its own: nothing is copied, it is simply downloaded once
  more into the new location on first use. The old copy in your system temp
  folder is now orphaned — **the uninstaller lists it** (as "модель, старое
  расположение") so you can reclaim the ~240 MB, or delete
  `%TEMP%\fastembed_cache` by hand. Nothing else on disk changes.

## [0.3.0] — 2026-08-12

A campaign is more than a graph of names. This release gives entities a
**sheet** — a character sheet you design yourself, fill in and print — and
gives your **players** a way in: a link that shows them exactly the cards you
chose to reveal, on your machine, over the Wi-Fi, or over the internet.

### Added

- **Entity templates and character sheets.** An entity can now be bound to a
  template: a set of fields plus a layout for them. One layout renders three
  ways — a compact sheet in the graph drawer, a full one in the editor, and a
  print version through your browser's own print dialog — so a character is
  readable at the table and on paper without maintaining it twice. Four
  built-in templates ship (Character, NPC, Location, Faction); the Character
  one is a full D&D 5e sheet whose saves, skills and passive scores are
  computed, not typed.

  A template stays a **preset, never a schema**: fields it creates are yours
  to edit, add to and delete afterwards, and a field the layout does not
  mention is shown under "Other fields" rather than hidden — a sheet can never
  swallow data. An entity with no template keeps the plain field list it
  always had.

- **A designer for those templates**, under **Project settings → Templates**.
  Build a sheet out of regions (a flat band, side-by-side columns, or tabs),
  sections and blocks, by dragging; a built-in can be duplicated and rebuilt
  for your own system. Ten widgets draw the same stored value different ways —
  a number can be a plain input, an ability-score box with its modifier, a row
  of rating dots, or a current/max tracker — because how a value is *drawn* is
  a property of your system, not of the store. The modifier next to a stat
  carries its own formula (D&D halves the score; a system with no such notion
  sets it to nothing), and the whole sheet is keyboard-navigable, tabs and
  rating dots included.

- **Computed values.** A block can show a value derived from other fields —
  an ability modifier, a skill bonus that accounts for proficiency, a carrying
  capacity — written in a small expression language of its own, with no `eval`
  and no reach beyond the current entity's fields. Proficiency toggles sit
  right in the row, so ticking "Stealth" recomputes the bonus in place.
  Whether the result carries a leading "+" is per block: "+3" says "add this
  to a roll", which a saving throw means and a passive score does not.
  A bad formula is refused when the template is saved, with the reason shown
  in the designer, rather than surfacing later as a wrong number on a sheet.

- **Sheet presets.** A section you built — an ability with its skills, a
  resource tracker, a checklist — can be saved and dropped whole into another
  template. Three ship built in.

- **Limited player access.** You can now let your players see the world you
  choose to show them. Reveal a card (one click from the board, or the "Player
  access" panel on any entity), write a separate text meant for players, and
  tick which of its fields they may see — everything else stays hidden. Each
  player gets an invite link; opening it shows only the revealed cards and a
  read-only board, and lets them keep their own notes, public to the party or
  private (you see all of them). Manage players under **Project settings →
  Players**: invite, rotate a leaked link, revoke (keeps their notes), or
  delete (removes them). Nothing is shown to anyone until you reveal it.
- **Play over the local network, or over the internet.** `start.bat --lan` opens
  the app to your Wi-Fi so players connect from their own devices;
  `start.bat --internet` additionally asks the router, over UPnP, to forward the
  port, and invite links switch to your public address — players anywhere just
  open a link, with nothing to install. The mapping is removed when the app
  closes. Without a flag nothing changes: the app stays on this machine.
  When internet access can't work, the app says which of the causes it is —
  a shared provider address (CGNAT), UPnP switched off, or a router that
  refused — because each needs a different fix, and the local network keeps
  working meanwhile. Shown both in the launcher and under Project settings →
  Players.
- **Optional HTTPS.** Point `CAMPAIGN_SSL_CERTFILE` and `CAMPAIGN_SSL_KEYFILE`
  at a certificate and its key and everything, invite links included, moves to
  https. Off by default; half a pair is refused at startup rather than serving
  plain HTTP while looking secure.
- **One process, one port.** The app and its API now share port 8000 — one
  firewall rule, one port to forward, and no CORS. The launcher builds the
  interface at startup instead of running a second dev server.
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
- **A live demo in the browser**, at
  [hadesxgod1337.github.io/loregraph](https://hadesxgod1337.github.io/loregraph/)
  — a sample campaign with its graph, its sheets and a scripted assistant,
  running entirely in your browser with no backend, no install and no API key.
  Nothing you do there leaves the tab, and a reload restores the world.
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
- **Toolbar buttons show what is actually active.** Bold, lists, headings and
  the rest never lit up while typing and never turned off again — the toolbar
  was frozen at whatever the document looked like when the editor opened, so
  the only way to see a state change was to select text first. It now follows
  the cursor.

### Migration

- The database gains four tables (templates, sheet presets, players, player
  notes) and three entity columns, added automatically on first start —
  nothing to do. **Every entity starts hidden**: players see nothing until you
  reveal it. Nothing you already have is bound to a template; existing
  entities keep their plain field list until you pick one.
- Project export now carries your templates and sheet presets, each entity's
  template binding, and its reveal state, player text and field whitelist.
  Files exported before this version import cleanly (no templates, all
  hidden), and a file written now still opens in 0.2.0 — the older build just
  ignores what it does not know. Players and their notes are **not** part of
  an export — invite tokens and personal notes never travel in a file;
  re-invite players after importing a project elsewhere.
- Serving attachments moved from a static mount to an access-checked route.
  URLs are unchanged; there is nothing to migrate. If you run behind a reverse
  proxy, set `CAMPAIGN_TRUST_LOOPBACK=false` and put real authentication in
  front — loopback trust assumes the peer address is the real client.
- **The app now lives on port 8000 only.** Port 5173 is no longer used by the
  launcher, so a firewall rule for it can be removed. Open `http://localhost:8000`
  and update any bookmark. Running the frontend dev server by hand still works
  for development and still uses 5173.

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

[#1]: https://github.com/HadeSxGod1337/loregraph/issues/1
[Unreleased]: https://github.com/HadeSxGod1337/loregraph/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.6.0
[0.5.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.5.0
[0.4.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.4.0
[0.3.1]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.3.1
[0.3.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.3.0
[0.2.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.2.0
[0.1.0]: https://github.com/HadeSxGod1337/loregraph/releases/tag/v0.1.0
