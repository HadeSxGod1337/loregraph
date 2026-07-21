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
  (propose_lore, edit_entity) — `entry_node` is where both entry points
  land.
- "job": a longer, possibly multi-batch pipeline with its own phases
  (reserved for the bulk-import/generate_bulk skills — not implemented yet).
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

SkillKind = Literal["read", "propose", "job"]


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
    """Semantic search over the world's lore. Use it BEFORE answering any
    question about the world."""

    query: str = Field(description="What to look for, in the lore's language.")


class get_entity_details(BaseModel):
    """Full details of one entity by its id (ids come from search_lore)."""

    entity_id: str


class search_knowledge_base(BaseModel):
    """Semantic search over the project's uploaded reference documents
    (rulebooks, setting bibles) — NOT world canon. Use it when the game
    master's question is about rules or reference material rather than the
    world's own established facts (that's search_lore)."""

    query: str = Field(description="What to look for, in the document's language.")


class propose_lore(BaseModel):
    """Draft new world content (entities + relationships) for the game
    master's review. The only way to create anything."""

    brief: str = Field(
        description="Concise self-contained description of what to create, "
        "carrying all relevant user constraints (scale, tone, connections)."
    )


class edit_entity(BaseModel):
    """Propose edits to an existing entity for the game master's review.
    Always call get_entity_details first to read the current state.
    The only way to modify world content. Never promise changes without
    calling this tool."""

    entity_id: str = Field(description="Id of the entity to edit.")
    brief: str = Field(
        description="Concise description of what to change and why, "
        "carrying all user constraints."
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
            name="propose_lore",
            description=propose_lore.__doc__ or "",
            input_schema=propose_lore,
            kind="propose",
            entry_node="begin_proposal",
        ),
        SkillManifest(
            name="edit_entity",
            description=edit_entity.__doc__ or "",
            input_schema=edit_entity,
            kind="propose",
            entry_node="begin_edit",
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

# Base tool set bound on every chat turn — order matches the pre-registry
# ASSISTANT_TOOLS list (agent/nodes/assistant.py) so prompt/cache behavior is
# unchanged. query_external_source is deliberately excluded: it is only
# bound when the project actually has live connections (see
# agent/nodes/assistant.py::assistant), a runtime/project concern this
# module doesn't know about.
_BASE_CHAT_TOOL_NAMES = (
    "search_lore",
    "get_entity_details",
    "search_knowledge_base",
    "propose_lore",
    "edit_entity",
)


def base_chat_tool_schemas() -> list[type[BaseModel]]:
    return [SKILLS[name].input_schema for name in _BASE_CHAT_TOOL_NAMES]


def entry_node_for(tool_call_name: str) -> str | None:
    """Node to route into for a "propose"/"job" skill invoked by name (a
    chat tool call or a direct skill_kickoff) — None for read skills/unknown
    names, meaning "not a dispatchable skill, handle as a read tool"."""
    manifest = SKILLS.get(tool_call_name)
    if manifest is not None and manifest.kind in ("propose", "job"):
        return manifest.entry_node
    return None
