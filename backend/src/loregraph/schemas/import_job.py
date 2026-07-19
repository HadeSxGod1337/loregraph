from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from loregraph.schemas.agent import AgentWarning, LoreDraft


class RegistryEntryDraft(BaseModel):
    """One name the model found in a document window — cheap, structured
    output (Haiku, low temperature) from agent/nodes/import_registry.py,
    used to canonicalize naming BEFORE the (pricier) extraction pass so
    windows referring to the same character/faction under slightly
    different names end up linked, not duplicated."""

    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    type: str = Field(description="snake_case entity type, e.g. npc, faction.")


class WindowRegistryDraft(BaseModel):
    entries: list[RegistryEntryDraft] = Field(default_factory=list)


class RegistryEntry(BaseModel):
    """Merged, deduplicated registry entry — a canonical name plus every
    alias seen across all windows, and the existing project entity it
    matches (if any) so extraction/merge links to canon instead of
    duplicating it."""

    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    type: str
    existing_entity_id: str | None = None


class ImportReviewDecision(BaseModel):
    """Resume contract for one page of the bulk-import review (see
    agent/nodes/import_review.py). `approve_all` commits this page AND every
    remaining page without further interrupts — a single deliberate human
    decision, not a backend bypass of the review gate (every page still
    gets a real `commit_slice` write, nothing is skipped)."""

    action: Literal["approve", "reject", "approve_all"]
    # DM edits to THIS page's entities, applied before commit — same
    # "DM edits win" semantics as AgentResumeRequest.draft.
    draft: LoreDraft | None = None


class ImportReviewPayload(BaseModel):
    """Everything the DM sees at one page of the bulk-import review."""

    slice_index: int
    total_slices: int
    draft: LoreDraft
    merge_notes: list[AgentWarning] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


type ImportJobStatus = Literal[
    "planning", "extracting", "awaiting_review", "committing", "committed", "failed"
]


class ImportJobOut(BaseModel):
    job_id: str
    project_id: str
    source_id: str
    source_filename: str
    status: ImportJobStatus
    total_windows: int
    total_slices: int
    current_slice: int
    committed_entity_ids: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    review: ImportReviewPayload | None = None
    created_at: datetime
    updated_at: datetime


class ImportJobStartRequest(BaseModel):
    source_id: str


class ImportEstimateOut(BaseModel):
    """Pre-flight estimate, computed before any LLM call — pure arithmetic,
    shown by the UI so the DM (who pays for their own BYOK key)
    knows roughly what a run
    will cost before starting it."""

    total_windows: int
    registry_calls: int
    extraction_calls: int
    estimated_input_tokens: int
    estimated_output_tokens: int
