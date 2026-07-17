from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from loregraph.schemas.entity import FieldType

type AgentSessionStatus = Literal[
    "idle", "running", "awaiting_review", "committed", "rejected", "failed"
]


class DraftField(BaseModel):
    key: str
    value: str
    field_type: FieldType = FieldType.TEXT


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


class EntityEditDraft(BaseModel):
    """What the agent proposes when editing an existing entity. Contains the
    full new state of the entity so the DM can review it as a diff against
    the current version before any write happens."""

    entity_id: str = Field(description="Id of the entity being edited.")
    type: str
    title: str
    summary: str
    fields: list[DraftField] = Field(default_factory=list)
    edit_reason: str = Field(
        description="One-sentence explanation of what changed and why."
    )


class GroundingReport(BaseModel):
    """LLM-as-judge output. `warnings` is free text in the lore's language,
    not a UI string — wrapped into AgentWarning(code="llm_text") before it
    reaches the review payload. `claims_checked`/`claims_flagged` are the
    structured counterpart (CLAUDE.md, "Структурированный вывод, не парсинг
    текста"): verify_grounding.py turns them into a numeric hallucination
    rate instead of only a free-text list, so the guard's quality can be
    tracked/regressed over time, not just read per-run.
    See agent/nodes/verify_grounding.py."""

    claims_checked: int = Field(
        default=0,
        description="Total number of claims in the draft about EXISTING "
        "world elements that were checked against existing_lore.",
    )
    claims_flagged: int = Field(
        default=0,
        description="How many of claims_checked are NOT supported by "
        "existing_lore — must equal the number of warnings below.",
    )
    warnings: list[str] = Field(default_factory=list)


class AgentWarning(BaseModel):
    """A structured, machine-translatable warning.

    The backend never composes UI copy (see docs/agent_architecture.md,
    "Языки") — nodes emit a `code` + `params`, and the frontend's i18n
    catalog (warnings.<code>) owns the sentence. `code == "llm_text"` is the
    one exception: it carries free text from an LLM judge in `params.text`,
    already in the conversation's own language, rendered as-is."""

    code: str
    params: dict[str, str] = Field(default_factory=dict)


class AgentReviewPayload(BaseModel):
    """Everything the DM sees at the human_review gate."""

    draft: LoreDraft | None
    entity_edit_draft: "EntityEditDraft | None" = None
    warnings: list[AgentWarning] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    # Numeric counterpart to `warnings`' llm_text entries — None when the
    # LLM-as-judge grounding tier didn't run (see agent/nodes/verify_
    # grounding.py, agent/state.py's grounding_hallucination_rate).
    grounding_hallucination_rate: float | None = None

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_legacy_string_warnings(cls, value: object) -> object:
        """Sessions committed before warnings became structured persisted
        plain strings in the registry's review_json column — coerce them on
        read instead of failing to load old rows."""
        if isinstance(value, list):
            return [
                {"code": "llm_text", "params": {"text": item}}
                if isinstance(item, str)
                else item
                for item in value
            ]
        return value


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
    # Set only for deterministic, backend-composed messages (commit acks,
    # budget-exhausted notices — see agent/events.py). `text` is still the
    # canonical English content the model reads back on later turns; when
    # `event_code` is set, the frontend renders the localized version
    # instead. None for the model's own natural-language replies, which
    # already follow the conversation's language per the system prompt.
    event_code: str | None = None
    event_params: dict[str, str] = Field(default_factory=dict)


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
