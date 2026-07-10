import asyncio
import base64
import json
from pathlib import Path

from loregraph.exceptions import InvalidEdgeReferenceError, UnsupportedExportFormatError
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityFieldOut,
    EntityUpdate,
    FieldType,
)
from loregraph.schemas.project import ProjectCreate, ProjectOut
from loregraph.schemas.project_transfer import (
    FORMAT_VERSION,
    ProjectExport,
    ProjectExportAttachment,
    ProjectExportEdge,
    ProjectExportEntity,
)
from loregraph.storage.protocols import (
    AttachmentStore,
    EdgeStore,
    EntityStore,
    ProjectStore,
)


async def export_project(
    project_store: ProjectStore,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    attachment_store: AttachmentStore,
    attachments_dir: Path,
    project_id: str,
) -> ProjectExport:
    """Serialize a project — entities, edges, and every attachment/icon they
    reference (base64-embedded, see project_transfer schema docstring for the
    size/simplicity tradeoff) — into a single portable, re-importable file."""
    project = await project_store.get(project_id)
    entities = await entity_store.list_entities(project_id)
    edges = await edge_store.list_all(project_id)

    export_entities: list[ProjectExportEntity] = []
    export_attachments: list[ProjectExportAttachment] = []
    for entity in entities:
        for attachment in await attachment_store.list_for_entity(entity.id):
            stored_filename = attachment.url.rsplit("/", 1)[-1]
            content = await asyncio.to_thread(
                (attachments_dir / entity.id / stored_filename).read_bytes
            )
            export_attachments.append(
                ProjectExportAttachment(
                    id=attachment.id,
                    entity_id=entity.id,
                    original_filename=attachment.original_filename,
                    stored_filename=stored_filename,
                    content_type=attachment.content_type,
                    data_base64=base64.b64encode(content).decode("ascii"),
                )
            )
        export_entities.append(
            ProjectExportEntity(
                id=entity.id,
                type=entity.type,
                title=entity.title,
                fields=entity.fields,
                icon_attachment_id=entity.icon.attachment_id if entity.icon else None,
            )
        )

    export_edges = [
        ProjectExportEdge(
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            type=edge.type,
            label=edge.label,
        )
        for edge in edges
    ]

    return ProjectExport(
        name=project.name,
        description=project.description,
        entities=export_entities,
        edges=export_edges,
        attachments=export_attachments,
    )


async def import_project(
    project_store: ProjectStore,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    attachment_store: AttachmentStore,
    attachments_dir: Path,
    data: ProjectExport,
) -> ProjectOut:
    """Recreate a project from `export_project`'s output (or a hand-authored
    seed file in the same shape — see seed/demo_project.json). Never reuses
    ids from the file: importing the same file twice, or into an app that
    already has data, must not collide with existing rows."""
    if data.format_version != FORMAT_VERSION:
        raise UnsupportedExportFormatError(data.format_version)

    project = await project_store.create(
        ProjectCreate(name=data.name, description=data.description)
    )

    entity_id_map: dict[str, str] = {}
    for entity in data.entities:
        created_entity = await entity_store.create(
            EntityCreate(
                type=entity.type,
                title=entity.title,
                fields=[
                    EntityFieldIn(**f.model_dump(mode="json")) for f in entity.fields
                ],
            ),
            project.id,
        )
        entity_id_map[entity.id] = created_entity.id

    for edge in data.edges:
        new_source = entity_id_map.get(edge.source_entity_id)
        new_target = entity_id_map.get(edge.target_entity_id)
        if new_source is None or new_target is None:
            raise InvalidEdgeReferenceError(
                edge.source_entity_id or edge.target_entity_id
            )
        await edge_store.create(
            EdgeCreate(
                source_entity_id=new_source,
                target_entity_id=new_target,
                type=edge.type,
                label=edge.label,
            ),
            project.id,
        )

    # old "/files/{entity_id}/{stored_filename}" fragment -> the same, rewritten
    # for the new entity/attachment ids — used below to fix up any rich_text
    # image references that pointed at the pre-import files.
    url_rewrites: dict[str, str] = {}
    attachment_id_map: dict[str, str] = {}
    for attachment in data.attachments:
        new_entity_id = entity_id_map.get(attachment.entity_id)
        if new_entity_id is None:
            continue  # attachment references an entity missing from this export — skip
        content = base64.b64decode(attachment.data_base64)
        created_attachment = await attachment_store.create(
            entity_id=new_entity_id,
            original_filename=attachment.original_filename,
            content_type=attachment.content_type,
            content=content,
        )
        new_stored_filename = created_attachment.url.rsplit("/", 1)[-1]
        old_fragment = f"/files/{attachment.entity_id}/{attachment.stored_filename}"
        new_fragment = f"/files/{new_entity_id}/{new_stored_filename}"
        url_rewrites[old_fragment] = new_fragment
        attachment_id_map[attachment.id] = created_attachment.id

    for entity in data.entities:
        new_id = entity_id_map[entity.id]
        await entity_store.update(
            new_id,
            EntityUpdate(
                type=entity.type,
                title=entity.title,
                fields=_rewrite_field_urls(entity.fields, url_rewrites),
            ),
        )
        if entity.icon_attachment_id is not None:
            new_icon_id = attachment_id_map.get(entity.icon_attachment_id)
            if new_icon_id is not None:
                await entity_store.set_icon(new_id, new_icon_id)

    return project


def _rewrite_field_urls(
    fields: list[EntityFieldOut], url_rewrites: dict[str, str]
) -> list[EntityFieldIn]:
    rewritten: list[EntityFieldIn] = []
    for field in fields:
        data = field.model_dump(mode="json")
        if field.field_type is FieldType.RICH_TEXT and url_rewrites:
            serialized = json.dumps(data["value"])
            for old_fragment, new_fragment in url_rewrites.items():
                serialized = serialized.replace(old_fragment, new_fragment)
            data["value"] = json.loads(serialized)
        rewritten.append(EntityFieldIn(**data))
    return rewritten
