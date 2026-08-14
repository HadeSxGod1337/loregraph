"""Single source of truth for everything the agent can do.

A "skill" here follows the Agent Skills pattern (Anthropic, progressive
disclosure): the LLM only ever sees a manifest's `name`/`description` (via
the bound tool schema) — the actual pipeline behind it is opaque to the
model. Two equally valid ways to invoke a skill:

1. Chat: the assistant model calls the tool by name; `route_after_assistant`
   (agent/nodes/assistant.py) looks up the manifest here to decide where to
   route (read tools inline, propose/job skills into their subgraph entry
   node) instead of hardcoding a branch per skill name.
2. Direct run: `POST .../skills/{name}/run` (api/routers/agent.py) validates
   the request body against the manifest's `input_schema` and kicks off the
   same entry node via `AgentState.skill_kickoff` — no LLM call involved,
   for UI-driven triggers (e.g. a button) that shouldn't depend on the
   assistant's judgment to fire correctly.

`kind` determines how a skill executes:
- "read": inline in the `tools` node (agent/nodes/tools.py) — a plain
  function call against the project's stores, no graph branch of its own.
- "propose": a short pipeline ending in one `human_review` interrupt
  (propose_changes) — `entry_node` is where both entry points land.
- "creative": a non-mutating pipeline that generates ideas on the creative
  tier and answers in chat, with NO review and NO write path
  (brainstorm_lore). Has an `entry_node` like a propose skill, but its branch
  ends at END, never at commit — the invariant that keeps brainstormed ideas
  from becoming canon by accident.
- "job": a longer, possibly multi-batch pipeline with its own phases
  (reserved for the bulk-import/generate_bulk skills — not implemented yet).
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

SkillKind = Literal["read", "propose", "job", "creative"]

# Bounds the model is allowed to steer, so they live next to the schemas that
# advertise them rather than inside the executor: a number quoted in a tool
# description and a number enforced in agent/nodes/tools.py must be the same
# number. Purely internal output budgets (how many chars of an entity to
# print) stay in the executor — the model never chooses those.
SEARCH_K_DEFAULT = 8
SEARCH_K_MAX = 20
# Enumeration is capped for prompt cost, but the *count* reported alongside it
# is always exact — a model that cannot tell "8 found" from "8 shown of 640"
# will confidently miscount the world (the bug this tool exists to fix).
LIST_ENTITIES_LIMIT = 200
# Depth 2 already pulls in neighbours-of-neighbours; 3 explodes on a dense
# campaign graph and buries the answer it was asked for.
GRAPH_DEPTH_MAX = 2
# One page of list_relationships. Unlike get_entity_details/get_entity_graph,
# which cap and stop, this tool pages: a hub entity with hundreds of edges is
# retrievable in full by following the cursor, so the number only has to keep a
# single page cheap, not bound the whole answer.
RELATIONSHIPS_PAGE_LIMIT = 40


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str
    input_schema: type[BaseModel]
    kind: SkillKind
    # Node name to enter for "propose"/"job" skills, reached either via
    # route_after_assistant's tool-call dispatch or a direct run's
    # AgentState.skill_kickoff. None for "read" skills (no subgraph — they
    # execute inline in the `tools` node instead).
    entry_node: str | None = None


# --- Tool schemas -----------------------------------------------------------
# These ARE the manifests' input_schema and, bound via chat_model.bind_tools,
# what the assistant model actually sees — the docstring is the tool
# description the LLM reads (progressive disclosure: nothing else about the
# skill's implementation is ever in its context).


class search_lore(BaseModel):
    """Meaning-based AND keyword search over the world's lore. Use it BEFORE
    answering any question about the world. It returns the best matches only,
    never a complete list — to count things or list them exhaustively use
    list_entities, and to see how entities are connected use get_entity_graph.
    """

    query: str = Field(description="What to look for, in the lore's language.")
    entity_type: str | None = Field(
        default=None,
        description="Optional: only return entities of this type, e.g. 'npc' "
        "or 'faction'. Omit unless the game master asked for one kind.",
    )
    limit: int | None = Field(
        default=None,
        description=f"Optional: how many results to return (default "
        f"{SEARCH_K_DEFAULT}, capped at {SEARCH_K_MAX}).",
    )


class get_entity_details(BaseModel):
    """Everything about one entity by its id: all of its fields AND every
    relationship it has, with the ids those relationships are addressed by.
    Ids come from search_lore or list_entities."""

    entity_id: str


class list_entities(BaseModel):
    """Enumerate the world's entities and count them exactly. Use this — not
    search_lore — whenever the answer has to be complete: "how many X are
    there", "list every X", "is there another X". Meaning-based search returns
    a handful of best guesses and can never prove how many of something exist
    or that something does not. Always reports the exact total, even when the
    listing itself is capped."""

    entity_type: str | None = Field(
        default=None,
        description="Optional: only count/list entities of this type, e.g. "
        "'npc'. Omit to cover the whole world.",
    )
    title_contains: str | None = Field(
        default=None,
        description="Optional: only entities whose title contains this text, "
        "case-insensitively. Use it to count namesakes.",
    )


class get_entity_graph(BaseModel):
    """Read an entity's relationship neighborhood — who it is connected to and
    how. Relationships live in the world's graph, SEPARATELY from an entity's
    fields, so this and get_entity_details are the only ways to see them;
    search_lore never returns one. Use it for "is A an enemy of B", "who are
    X's allies", "what does X belong to"."""

    entity_id: str = Field(description="Id of the entity to start from.")
    depth: int = Field(
        default=1,
        description=f"1 = direct connections only, {GRAPH_DEPTH_MAX} = also "
        f"the connections of those. Larger values are clamped.",
    )


class list_relationships(BaseModel):
    """List ALL of one entity's relationships, page by page — the tool for
    "show me every connection X has" when it has more than a handful.
    get_entity_graph and get_entity_details show only the first slice of a busy
    entity's edges and stop; this one reports the EXACT total, separates
    incoming from outgoing, and hands back a `next_cursor` so the rest can
    actually be fetched. To read them all, keep calling it with the cursor from
    the previous page until it says there are no more. Filter by direction or
    type to narrow a large graph."""

    entity_id: str = Field(description="Id of the entity whose relationships to list.")
    direction: str | None = Field(
        default=None,
        description="Optional: 'incoming' (edges pointing AT this entity), "
        "'outgoing' (edges FROM it), or omit for both.",
    )
    type: str | None = Field(
        default=None,
        description="Optional: only relationships of this snake_case type, "
        "e.g. 'ally_of'. Omit for every type.",
    )
    cursor: int | None = Field(
        default=None,
        description="Pass the next_cursor from a previous page to continue; "
        "omit for the first page.",
    )


class search_knowledge_base(BaseModel):
    """Semantic search over the project's uploaded reference documents
    (rulebooks, setting bibles) — NOT world canon. Use it when the game
    master's question is about rules or reference material rather than the
    world's own established facts (that's search_lore)."""

    query: str = Field(description="What to look for, in the document's language.")


class propose_changes(BaseModel):
    """Propose ANY change to the world for the game master's review — the only
    way to change anything, and the one tool for all of it. In a single
    proposal you can create new entities, edit entities that already exist
    (add/rewrite/remove their fields, rename them), and add, change or remove
    relationships. You never choose between "create" and "edit" up front: you
    describe what the game master wants and name the existing entities it
    concerns, and the review pipeline works out the rest.

    Use it whenever the game master asks to add, invent, fill in, rewrite,
    improve, connect, or unlink anything. "Придумай кто такой этот Егор и
    добавь ему поля" about an Егор who already exists is this tool with his id
    in target_entity_ids — an EDIT, not a new character.

    Reading is separate: look things up with search_lore / list_entities /
    get_entity_details FIRST to get real ids, then call this. You have no
    direct write access; every proposal goes through the game master's
    review, and nothing is ever deleted without their approval."""

    brief: str = Field(
        description="Self-contained description of what the game master wants "
        "changed, carrying every relevant constraint (scale, tone, which "
        "fields, which connections). If it builds on existing entities, say "
        "so — the pipeline reads their full current state."
    )
    target_entity_ids: list[str] = Field(
        default_factory=list,
        description="Real ids of entities that ALREADY exist and are the "
        "subject of this change — the ones to edit, or to connect. Get them "
        "from search_lore / list_entities / get_entity_details first. Leave "
        "empty only when the request is purely about brand-new content.",
    )


class brainstorm_lore(BaseModel):
    """Brainstorm creative possibilities for the world WITHOUT changing
    anything. Use it when the game master wants ideas, options, or inspiration
    rather than a concrete edit: "придумай врага для Ордена", "накидай пять
    идей для локации", "как развить этот конфликт", "предложи повороты",
    "surprise me". You invent freely here — that is the whole point — but the
    result is a set of OPTIONS shown in chat, not canon: nothing is written.

    Two things separate this from propose_changes:
    - This never touches the world. propose_changes creates/edits/links things
      (through the game master's review). If the request ALSO says to add,
      create, record, or enter the result — "…и добавь", "…и создай его",
      "запиши", "внеси в мир" — that is a mutation: use propose_changes, not
      this. Mutation intent always wins.
    - Look up relevant canon FIRST (search_lore / get_entity_details /
      get_entity_graph) when the ideas should build on something that exists
      ("враг для Ордена Серебряного Пламени" → resolve the Order, brainstorm
      against its goals/allies/enemies), and pass those ids in
      target_entity_ids. Never answer "there is no enemy in canon" — the game
      master asked you to invent one."""

    topic: str = Field(
        description="What to brainstorm, in the game master's language — the "
        "creative prompt, carrying any constraints they gave (tone, kind, "
        "scale)."
    )
    target_entity_ids: list[str] = Field(
        default_factory=list,
        description="Ids of existing entities the ideas should build on or "
        "play against (an Order to invent an enemy for, a location to develop). "
        "Get them from a read tool first; empty for a blank-slate prompt.",
    )
    count: int | None = Field(
        default=None,
        description="How many ideas, when the game master named a number "
        "('пять идей' → 5). Omit to let you choose a useful few.",
    )


class import_document(BaseModel):
    """Bulk-import an uploaded knowledge-base document into the world
    graph: walks the whole document in parallel windows, canonicalizes
    names before extraction, deduplicates against existing canon, and
    presents the result for page-by-page review. NOT chat-dispatchable in
    this version — always triggered directly (see api/routers/
    import_jobs.py, agent/import_runner.py) from a UI button, deliberately
    not left to the assistant's judgment to decide when to fire. Kept in
    this registry anyway so it is documented alongside every other skill,
    per the "single source of truth" rationale in this module's docstring.
    """

    source_id: str = Field(description="Id of a ready knowledge-base source.")


class query_external_source(BaseModel):
    """Query live data from an external tool connected to this project
    (Foundry VTT world, LongStoryShort character sheets…). Use it when the
    game master asks about the CURRENT state of their external tools (actor
    stats, journals, party HP) — that data lives outside the world's lore."""

    source: str = Field(
        description="Connection name, exactly as listed in <external_sources>."
    )
    query: str = Field(description="What to look for.")
    kind: str | None = Field(
        default=None,
        description="Optional data kind: actors | journals | items | "
        "compendium. 'items' is this world's own item library (armor, "
        "weapons, loot in the sidebar) — NOT 'compendium', which is the "
        "reference rulebook item database.",
    )


# --- Registry -----------------------------------------------------------

SKILLS: dict[str, SkillManifest] = {
    manifest.name: manifest
    for manifest in (
        SkillManifest(
            name="search_lore",
            description=search_lore.__doc__ or "",
            input_schema=search_lore,
            kind="read",
        ),
        SkillManifest(
            name="get_entity_details",
            description=get_entity_details.__doc__ or "",
            input_schema=get_entity_details,
            kind="read",
        ),
        SkillManifest(
            name="list_entities",
            description=list_entities.__doc__ or "",
            input_schema=list_entities,
            kind="read",
        ),
        SkillManifest(
            name="get_entity_graph",
            description=get_entity_graph.__doc__ or "",
            input_schema=get_entity_graph,
            kind="read",
        ),
        SkillManifest(
            name="list_relationships",
            description=list_relationships.__doc__ or "",
            input_schema=list_relationships,
            kind="read",
        ),
        SkillManifest(
            name="search_knowledge_base",
            description=search_knowledge_base.__doc__ or "",
            input_schema=search_knowledge_base,
            kind="read",
        ),
        SkillManifest(
            name="query_external_source",
            description=query_external_source.__doc__ or "",
            input_schema=query_external_source,
            kind="read",
        ),
        SkillManifest(
            name="propose_changes",
            description=propose_changes.__doc__ or "",
            input_schema=propose_changes,
            kind="propose",
            entry_node="begin_changes",
        ),
        SkillManifest(
            name="brainstorm_lore",
            description=brainstorm_lore.__doc__ or "",
            input_schema=brainstorm_lore,
            kind="creative",
            entry_node="brainstorm",
        ),
        SkillManifest(
            name="import_document",
            description=import_document.__doc__ or "",
            input_schema=import_document,
            kind="job",
            # No entry_node: this runs on its own compiled graph
            # (agent/import_graph.py), not build_agent_graph's AgentState
            # graph — see this class's docstring.
            entry_node=None,
        ),
    )
}

# Base tool set bound on every chat turn. The leading names keep the
# pre-registry ASSISTANT_TOOLS order so the cached prompt prefix is unchanged;
# genuinely new capabilities (list_relationships, brainstorm_lore) are appended
# rather than interleaved, so they extend the tool set without moving the
# stable prefix. query_external_source is deliberately excluded: it is only
# bound when the project actually has live connections (see
# agent/nodes/assistant.py::assistant), a runtime/project concern this
# module doesn't know about.
_BASE_CHAT_TOOL_NAMES = (
    "search_lore",
    "get_entity_details",
    "search_knowledge_base",
    "propose_changes",
    "list_entities",
    "get_entity_graph",
    "list_relationships",
    "brainstorm_lore",
)


def base_chat_tool_schemas() -> list[type[BaseModel]]:
    return [SKILLS[name].input_schema for name in _BASE_CHAT_TOOL_NAMES]


def pipeline_entry_node(tool_call_name: str) -> str | None:
    """Node to route into for a skill that runs on its OWN subgraph branch
    rather than inline in the `tools` node — the write pipeline
    (propose_changes) and the creative one (brainstorm_lore), reached by a chat
    tool call or a direct skill_kickoff. None for read skills/unknown names,
    meaning "not a branching skill, handle it as a read tool"."""
    manifest = SKILLS.get(tool_call_name)
    if manifest is not None and manifest.kind in ("propose", "job", "creative"):
        return manifest.entry_node
    return None


def is_write_skill(tool_call_name: str) -> bool:
    """True only for skills that MUTATE canon (through review) — the write
    pipeline. brainstorm_lore is a branching skill (it has an entry node) but
    NOT a write one: it never reaches human_review or commit, so the "only one
    proposal per turn" rule must not apply to it."""
    manifest = SKILLS.get(tool_call_name)
    return manifest is not None and manifest.kind in ("propose", "job")
