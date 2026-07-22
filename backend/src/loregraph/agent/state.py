from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from loregraph.schemas.agent import (
    AgentWarning,
    EntityEditDraft,
    LoreDraft,
    SkillKickoff,
)

# Checkpointed state is the app's closest thing to a public contract:
# interrupted graphs live on disk between process restarts.
# v3: conversational thread (messages) replaces the one-shot
# `instruction`; old v2 checkpoints cannot resume — pending drafts reset.
# v4: `warnings` became structured (AgentWarning) instead of free strings, so
# the frontend can translate them — old v3 checkpoints cannot resume either.
# v5: entity_edit_draft + pending_edit_entity_id added for the edit-entity
# pipeline — old v4 checkpoints cannot resume interrupted edit sessions.
STATE_VERSION = 5

# Marker injected into prompts when retrieval found nothing — the model must
# be told explicitly instead of being left to hallucinate connections.
NO_LORE_SENTINEL = (
    "(no existing lore is relevant to this request — "
    "this is a brand-new part of the world)"
)


class AgentState(BaseModel):
    state_version: int = STATE_VERSION

    # Conversation
    project_id: str
    # The checkpointer's thread_id, mirrored into state so nodes can attribute
    # token usage to this session without reaching for the runtime config.
    # Additive with a default (safe for pre-existing checkpoints, like
    # knowledge_context below — STATE_VERSION unchanged).
    thread_id: str = ""
    anchor_entity_id: str | None = None
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)
    # One-shot trigger for a direct (non-chat) skill run — additive field
    # with a default, safe for pre-existing checkpoints (STATE_VERSION
    # unchanged, same precedent as knowledge_context below). Consumed and
    # cleared by the skill's own entry node (see agent/skills/registry.py).
    skill_kickoff: SkillKickoff | None = None

    # Current proposal (reset when a new propose_lore tool call starts)
    pending_brief: str = ""
    revision_feedback: str = ""
    existing_lore: str = ""
    # Reference material from the project's knowledge base (uploaded docs) —
    # additive field with a default, safe for pre-existing checkpoints
    # (STATE_VERSION unchanged, unlike breaking renames). Deliberately kept
    # separate from existing_lore/context_entity_ids: it is never a valid
    # grounded_in target (see prompts/generate_lore.system.md).
    knowledge_context: str = ""
    context_entity_ids: list[str] = Field(default_factory=list)
    # Ids of the relationships shown to the model in existing_lore — the
    # whitelist an update/delete op must address, mirroring what
    # context_entity_ids does for entities. Additive field with a default,
    # safe for pre-existing checkpoints (STATE_VERSION unchanged).
    context_edge_ids: list[str] = Field(default_factory=list)
    known_entity_types: list[str] = Field(default_factory=list)
    available_links: str = ""
    draft: LoreDraft | None = None
    # Edit pipeline: set when the assistant calls edit_entity
    entity_edit_draft: EntityEditDraft | None = None
    pending_edit_entity_id: str = ""
    # Relationship pipeline: the entities manage_relationships was asked to
    # work on — additive field with a default, safe for pre-existing
    # checkpoints (STATE_VERSION unchanged).
    pending_entity_ids: list[str] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)
    # Set by verify_grounding's LLM-as-judge tier (agent/nodes/verify_
    # grounding.py); None when that tier didn't run (no lore to check
    # against, or out of budget) — additive field with a default, safe for
    # pre-existing checkpoints (STATE_VERSION unchanged).
    grounding_hallucination_rate: float | None = None
    attempts: int = 0
    retry_feedback: str = ""
    draft_committed: bool = False

    # Cost accounting (BYOK — the user pays per call)
    input_tokens: int = 0
    output_tokens: int = 0

    # Review outcome; committed ids accumulate over the whole conversation
    decision_action: str | None = None
    committed_entity_ids: list[str] = Field(default_factory=list)

    def over_budget(self, token_budget: int) -> bool:
        return self.input_tokens + self.output_tokens >= token_budget
