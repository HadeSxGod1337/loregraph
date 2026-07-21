from typing import Literal

from pydantic import BaseModel, Field

from loregraph.schemas.agent import (
    AgentWarning,
    DraftEntity,
    DraftRelationship,
    LoreDraft,
)
from loregraph.schemas.import_job import RegistryEntry

# Checkpointed state, same rationale as agent/state.py's AgentState: an
# interrupted import job lives on disk between process restarts (same
# AsyncSqliteSaver instance, a different thread_id namespace — see
# agent/import_runner.py). Deliberately NOT part of AgentState: this is a
# map-reduce job, not a chat turn, and would otherwise permanently bloat
# every conversational checkpoint with fields only bulk-import ever uses.
IMPORT_STATE_VERSION = 1


class WindowSpec(BaseModel):
    index: int
    text: str


class WindowExtraction(BaseModel):
    index: int
    draft: LoreDraft
    input_tokens: int = 0
    output_tokens: int = 0


class ImportState(BaseModel):
    state_version: int = IMPORT_STATE_VERSION

    project_id: str
    # "knowledge": source_id is a KnowledgeSource id (uploaded file).
    # "connection": source_id is a connection id whose connector implements
    # IngestSource (migrate an external project into the graph). source_id /
    # source_filename stay generic ref/label so no DB column had to change.
    source_kind: Literal["knowledge", "connection"] = "knowledge"
    source_id: str
    source_filename: str
    # Mirrors the checkpointer's thread_id, same rationale as AgentState's
    # own thread_id field: nodes can publish progress events (see
    # agent/nodes/import_registry.py, import_extract.py) without reaching
    # into the runtime config.
    job_id: str = ""

    # Set once by plan_windows; each window is re-derived text (not the KB's
    # own embedding-sized chunks — see agent/nodes/import_plan.py).
    windows: list[WindowSpec] = Field(default_factory=list)
    known_entity_types: list[str] = Field(default_factory=list)
    # Set once by build_registry (agent/nodes/import_registry.py).
    registry: list[RegistryEntry] = Field(default_factory=list)
    # Set once by extract_windows (agent/nodes/import_extract.py).
    extractions: list[WindowExtraction] = Field(default_factory=list)

    # Set once by merge_extractions (agent/nodes/import_merge.py):
    # deduplicated entities (paginate_review slices these into review_slices
    # right after) plus relationships, held separately and committed in one
    # final pass after every entity page is resolved (see
    # agent/nodes/import_commit.py's commit_relationships), not per-page —
    # a relationship may point at an entity from a page that hasn't
    # committed yet, which only ref_to_id (populated as pages commit) can
    # resolve.
    merged_entities: list[DraftEntity] = Field(default_factory=list)
    merge_notes: list[AgentWarning] = Field(default_factory=list)
    pending_relationships: list[DraftRelationship] = Field(default_factory=list)

    # Review/commit progress.
    review_slices: list[LoreDraft] = Field(default_factory=list)
    current_slice: int = 0
    decision_action: Literal["approve", "reject", "approve_all"] | None = None
    warnings: list[AgentWarning] = Field(default_factory=list)
    # ref (e.g. "m3") -> real committed entity id, accumulated across pages
    # so a later page's (or the final relationship pass's) references to an
    # earlier page's entity still resolve after that entity already has a
    # real id (see agent/nodes/import_commit.py).
    ref_to_id: dict[str, str] = Field(default_factory=dict)
    committed_entity_ids: list[str] = Field(default_factory=list)

    input_tokens: int = 0
    output_tokens: int = 0

    def over_budget(self, token_budget: int) -> bool:
        return self.input_tokens + self.output_tokens >= token_budget
