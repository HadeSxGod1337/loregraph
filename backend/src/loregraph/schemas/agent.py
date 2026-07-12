from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

type AgentSessionStatus = Literal[
    "idle", "running", "awaiting_review", "committed", "rejected", "failed"
]


class DraftField(BaseModel):
    key: str
    value: str


class DraftEntity(BaseModel):
    """One entity in a generated lore batch. The model chooses `type` itself
    (preferring types already used in the project) — the DM corrects it at
    review if needed."""

    ref: str = Field(
        description="Local id (e.g. 'e1') used to wire relationships inside "
        "this draft before real ids exist."
    )
    type: str = Field(description="snake_case entity type, e.g. npc, faction.")
    title: str
    summary: str = Field(description="One or two sentences capturing the essence.")
    fields: list[DraftField] = Field(default_factory=list)
    grounded_in: list[str] = Field(
        default_factory=list,
        description="Ids from <existing_lore> this entity builds on; empty "
        "means it is a pure invention awaiting DM confirmation.",
    )


class DraftRelationship(BaseModel):
    source_ref: str = Field(description="ref of a draft entity.")
    target_ref: str = Field(
        description="ref of another draft entity, or the id of an existing "
        "entity from <existing_lore>."
    )
    type: str = Field(description="Short snake_case relationship type.")
    reason: str
    grounded_in: list[str] = Field(default_factory=list)


class LoreDraft(BaseModel):
    """What one agent run proposes: a coherent batch of entities plus the web
    of relationships between them (and to existing lore). This is the unit
    the DM reviews — a piece of world, not a single card."""

    entities: list[DraftEntity]
    relationships: list[DraftRelationship] = Field(default_factory=list)


class GroundingReport(BaseModel):
    warnings: list[str] = Field(default_factory=list)


class AgentReviewPayload(BaseModel):
    """Everything the DM sees at the human_review gate."""

    draft: LoreDraft | None
    warnings: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class ChatAttachment(BaseModel):
    """One file attached to a single chat turn — NOT the project's knowledge
    base (services/knowledge_index.py). Lives only inside that turn's
    HumanMessage content; persisted by the LangGraph checkpointer along with
    the rest of the conversation, never chunked or embedded (see
    agent/multimodal.py)."""

    filename: str
    content_type: str
    data_base64: str


class AgentMessageRequest(BaseModel):
    """One user turn in the conversation."""

    text: str
    anchor_entity_id: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)


class AgentResumeRequest(BaseModel):
    action: Literal["approve", "reject", "revise"]
    # Optional DM edits (entities removed, titles changed, relationships
    # dropped) applied before commit — or, for revise, the base the model
    # must preserve; None keeps the agent's version.
    draft: LoreDraft | None = None
    # revise only: what to change.
    feedback: str | None = None


class AgentMessageOut(BaseModel):
    """Transcript entry for the UI (tool plumbing filtered out)."""

    role: Literal["user", "assistant"]
    text: str
    # Filenames only (never the file bytes) — round-tripped through the
    # HumanMessage's additional_kwargs, see agent/runner.py::transcript.
    attachments: list[str] = Field(default_factory=list)


class AgentSessionOut(BaseModel):
    thread_id: str
    project_id: str
    status: AgentSessionStatus
    title: str
    input_tokens: int
    output_tokens: int
    committed_entity_ids: list[str]
    review: AgentReviewPayload | None
    created_at: datetime
    updated_at: datetime


class AgentSessionDetail(AgentSessionOut):
    messages: list[AgentMessageOut] = Field(default_factory=list)


class AgentConfigOut(BaseModel):
    llm_configured: bool
    llm_provider: str
    vector_enabled: bool
