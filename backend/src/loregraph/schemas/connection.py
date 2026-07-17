from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# Sentinel prefix used when masking secret config values in API responses.
# An update request that sends a value starting with this prefix means
# "keep the stored secret" (the client echoed the mask back).
SECRET_MASK_PREFIX = "••••"


class ConnectorTypeOut(BaseModel):
    """A registered connector type and what it can do — drives the
    'Add connection' UI without hardcoding types on the frontend."""

    connector_type: str
    capabilities: list[str]


class ConnectionCreate(BaseModel):
    connector_type: str
    name: str
    config: dict[str, Any] = {}
    use_for_grounding: bool = False
    auto_push_after_commit: bool = False


class ConnectionUpdate(BaseModel):
    name: str
    config: dict[str, Any] = {}
    use_for_grounding: bool = False
    auto_push_after_commit: bool = False


class ConnectionOut(BaseModel):
    id: str
    project_id: str
    connector_type: str
    name: str
    # Raw stored config internally; the router masks secret fields before
    # this model ever leaves the API (see api/routers/connections.py).
    config: dict[str, Any]
    use_for_grounding: bool
    auto_push_after_commit: bool
    created_at: datetime
    updated_at: datetime


class ConnectionEntityLinkOut(BaseModel):
    """Provenance row: which external document/record an entity maps to in a
    given connection — lets a second export update instead of duplicate, and
    a re-import dedupe instead of clone."""

    id: str
    connection_id: str
    entity_id: str
    external_id: str
    external_kind: str
    last_synced_at: datetime


class ExportRequest(BaseModel):
    # None = whole project.
    entity_ids: list[str] | None = None


class ExportPreviewItem(BaseModel):
    entity_id: str
    title: str
    action: Literal["create", "update", "skip"]
    # Where it will land: vault-relative path, Foundry document name, etc.
    target: str
    # Rendered payload (e.g. the .md text) when cheap to produce — the DM
    # sees exactly what will be written before confirming.
    rendered: str | None = None


class ExportPreview(BaseModel):
    items: list[ExportPreviewItem]


class ItemError(BaseModel):
    """Per-item failure inside an export/import run. `code` is machine-
    readable (frontend translates); `detail` is an English diagnostic."""

    ref: str
    code: str
    detail: str


class ExportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ItemError] = []


class ImportRequest(BaseModel):
    """Connector-specific payload, validated by the connector's own
    import-payload model (e.g. LSS: {share_url} or {raw_json}; Obsidian:
    empty — it reads the configured vault)."""

    payload: dict[str, Any] = {}


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ItemError] = []


class ProbeResult(BaseModel):
    ok: bool
    # Machine code for the frontend i18n catalog, e.g. "vault_ok",
    # "vault_path_missing", "foundry_unreachable".
    detail_code: str
    # Small facts worth showing verbatim (world title, vault path…).
    info: dict[str, str] = {}
