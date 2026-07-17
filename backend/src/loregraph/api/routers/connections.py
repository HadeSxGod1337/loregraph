import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends

from loregraph.api.deps import (
    AttachmentStoreDep,
    ConnectionEntityLinkStoreDep,
    ConnectionStoreDep,
    ConnectorRegistryDep,
    ConnectorRuntimeDep,
    EdgeServiceDep,
    EdgeStoreDep,
    EntityServiceDep,
    EntityStoreDep,
    ProjectStoreDep,
    SettingsDep,
)
from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.protocols import ConnectionProbe, Exporter, Importer
from loregraph.connectors.registry import (
    ConnectorRegistry,
    mask_secrets,
    merge_masked_secrets,
)
from loregraph.exceptions import (
    ConnectionNotFoundError,
    UnsupportedConnectorCapabilityError,
)
from loregraph.schemas.connection import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    ConnectorTypeOut,
    ExportPreview,
    ExportRequest,
    ExportResult,
    ImportRequest,
    ImportResult,
    ProbeResult,
)
from loregraph.storage.protocols import ConnectionStore

logger = logging.getLogger(__name__)

# Registered connector types — project-independent, so a separate router.
types_router = APIRouter(prefix="/connectors", tags=["connections"])

router = APIRouter(prefix="/projects/{project_id}/connections", tags=["connections"])


@types_router.get("", response_model=list[ConnectorTypeOut])
async def list_connector_types(
    registry: ConnectorRegistryDep,
) -> list[ConnectorTypeOut]:
    return registry.list_types()


def _masked(registry: ConnectorRegistry, connection: ConnectionOut) -> ConnectionOut:
    descriptor = registry.get(connection.connector_type)
    return connection.model_copy(
        update={"config": mask_secrets(descriptor.config_model, connection.config)}
    )


async def _get_in_project(
    store: ConnectionStore, project_id: str, connection_id: str
) -> ConnectionOut:
    connection = await store.get(connection_id)
    if connection.project_id != project_id:
        # Same rule as entities: wrong project -> 404, don't confirm the id.
        raise ConnectionNotFoundError(connection_id)
    return connection


@dataclass(frozen=True)
class _ConnectorBuilder:
    """Bundles the per-request deps every export/import/test endpoint needs,
    so each endpoint is one lookup + one capability check instead of ten
    dependency parameters."""

    store: ConnectionStore
    registry: ConnectorRegistry
    context_template: ConnectorContext

    async def build[T](
        self, project_id: str, connection_id: str, capability: type[T], name: str
    ) -> T:
        connection = await _get_in_project(self.store, project_id, connection_id)
        context = ConnectorContext(
            project_id=connection.project_id,
            connection_id=connection.id,
            connection_name=connection.name,
            entity_service=self.context_template.entity_service,
            edge_service=self.context_template.edge_service,
            entity_store=self.context_template.entity_store,
            edge_store=self.context_template.edge_store,
            attachment_store=self.context_template.attachment_store,
            attachments_dir=self.context_template.attachments_dir,
            link_store=self.context_template.link_store,
            runtime=self.context_template.runtime,
        )
        connector = self.registry.create(
            connection.connector_type, connection.config, context
        )
        if not isinstance(connector, capability):
            raise UnsupportedConnectorCapabilityError(connection.connector_type, name)
        return connector


async def get_connector_builder(
    store: ConnectionStoreDep,
    registry: ConnectorRegistryDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
    link_store: ConnectionEntityLinkStoreDep,
    settings: SettingsDep,
    runtime: ConnectorRuntimeDep,
) -> _ConnectorBuilder:
    template = ConnectorContext(
        project_id="",
        connection_id="",
        connection_name="",
        entity_service=entity_service,
        edge_service=edge_service,
        entity_store=entity_store,
        edge_store=edge_store,
        attachment_store=attachment_store,
        attachments_dir=settings.attachments_dir,
        link_store=link_store,
        runtime=runtime,
    )
    return _ConnectorBuilder(store=store, registry=registry, context_template=template)


ConnectorBuilderDep = Annotated[_ConnectorBuilder, Depends(get_connector_builder)]


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    project_id: str,
    store: ConnectionStoreDep,
    registry: ConnectorRegistryDep,
    project_store: ProjectStoreDep,
) -> list[ConnectionOut]:
    await project_store.get(project_id)
    return [_masked(registry, c) for c in await store.list_for_project(project_id)]


@router.post("", response_model=ConnectionOut, status_code=201)
async def create_connection(
    project_id: str,
    data: ConnectionCreate,
    store: ConnectionStoreDep,
    registry: ConnectorRegistryDep,
    project_store: ProjectStoreDep,
) -> ConnectionOut:
    await project_store.get(project_id)
    # Validate type + config shape up front so a broken connection can't be
    # saved (raises UnknownConnectorTypeError / ConnectorConfigInvalidError).
    registry.validate_config(data.connector_type, data.config)
    created = await store.create(project_id, data)
    return _masked(registry, created)


@router.put("/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    project_id: str,
    connection_id: str,
    data: ConnectionUpdate,
    store: ConnectionStoreDep,
    registry: ConnectorRegistryDep,
    runtime: ConnectorRuntimeDep,
) -> ConnectionOut:
    existing = await _get_in_project(store, project_id, connection_id)
    descriptor = registry.get(existing.connector_type)
    merged = data.model_copy(
        update={
            "config": merge_masked_secrets(
                descriptor.config_model, data.config, existing.config
            )
        }
    )
    registry.validate_config(existing.connector_type, merged.config)
    updated = await store.update(connection_id, merged)
    # Config may have changed — a cached long-lived client is now stale.
    await runtime.invalidate(connection_id)
    return _masked(registry, updated)


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    project_id: str,
    connection_id: str,
    store: ConnectionStoreDep,
    runtime: ConnectorRuntimeDep,
) -> None:
    await _get_in_project(store, project_id, connection_id)
    await store.delete(connection_id)
    await runtime.invalidate(connection_id)


@router.post("/{connection_id}/test", response_model=ProbeResult)
async def test_connection(
    project_id: str, connection_id: str, builder: ConnectorBuilderDep
) -> ProbeResult:
    # type-abstract: passing a Protocol class as type[T] is exactly the point
    # here (runtime_checkable isinstance narrowing); mypy can't express it.
    connector = await builder.build(
        project_id,
        connection_id,
        ConnectionProbe,  # type: ignore[type-abstract]
        "probe",
    )
    return await connector.test_connection()


@router.post("/{connection_id}/export/preview", response_model=ExportPreview)
async def preview_export(
    project_id: str,
    connection_id: str,
    request: ExportRequest,
    builder: ConnectorBuilderDep,
) -> ExportPreview:
    connector = await builder.build(
        project_id,
        connection_id,
        Exporter,  # type: ignore[type-abstract]
        "export",
    )
    return await connector.preview_export(request)


@router.post("/{connection_id}/export", response_model=ExportResult)
async def run_export(
    project_id: str,
    connection_id: str,
    request: ExportRequest,
    builder: ConnectorBuilderDep,
) -> ExportResult:
    connector = await builder.build(
        project_id,
        connection_id,
        Exporter,  # type: ignore[type-abstract]
        "export",
    )
    return await connector.export(request)


@router.post("/{connection_id}/import", response_model=ImportResult)
async def run_import(
    project_id: str,
    connection_id: str,
    request: ImportRequest,
    builder: ConnectorBuilderDep,
) -> ImportResult:
    connector = await builder.build(
        project_id,
        connection_id,
        Importer,  # type: ignore[type-abstract]
        "import",
    )
    return await connector.import_data(request)
