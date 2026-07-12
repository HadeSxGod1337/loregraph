from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from loregraph.schemas.agent import LoreDraft

# Checkpointed state is the app's closest thing to a public contract
# (CLAUDE.md, "Схема состояния"): interrupted graphs live on disk between
# process restarts. v3: conversational thread (messages) replaces the one-shot
# `instruction`; old v2 checkpoints cannot resume — pending drafts reset.
STATE_VERSION = 3

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
    anchor_entity_id: str | None = None
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)

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
    known_entity_types: list[str] = Field(default_factory=list)
    draft: LoreDraft | None = None
    warnings: list[str] = Field(default_factory=list)
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
