from fastapi import APIRouter

from loregraph.api.deps import (
    AttachmentStoreDep,
    EdgeStoreDep,
    EntityStoreDep,
    ProjectStoreDep,
    SettingsDep,
)
from loregraph.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from loregraph.schemas.project_transfer import ProjectExport
from loregraph.services.project_transfer import export_project, import_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(store: ProjectStoreDep) -> list[ProjectOut]:
    return await store.list_projects()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, store: ProjectStoreDep) -> ProjectOut:
    return await store.create(data)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, store: ProjectStoreDep) -> ProjectOut:
    return await store.get(project_id)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str, data: ProjectUpdate, store: ProjectStoreDep
) -> ProjectOut:
    return await store.update(project_id, data)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, store: ProjectStoreDep) -> None:
    await store.delete(project_id)


@router.get("/{project_id}/export", response_model=ProjectExport)
async def export_project_route(
    project_id: str,
    project_store: ProjectStoreDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
    settings: SettingsDep,
) -> ProjectExport:
    return await export_project(
        project_store,
        entity_store,
        edge_store,
        attachment_store,
        settings.attachments_dir,
        project_id,
    )


@router.post("/import", response_model=ProjectOut, status_code=201)
async def import_project_route(
    data: ProjectExport,
    project_store: ProjectStoreDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
    settings: SettingsDep,
) -> ProjectOut:
    return await import_project(
        project_store,
        entity_store,
        edge_store,
        attachment_store,
        settings.attachments_dir,
        data,
    )
