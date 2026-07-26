from fastapi import APIRouter

from loregraph.api.deps import EntityServiceDep, EntityTemplateServiceDep
from loregraph.schemas.entity import EntityCreate, EntityOut
from loregraph.schemas.entity_template import (
    EntityTemplateCreate,
    EntityTemplateOut,
    EntityTemplateUpdate,
    TemplateInstantiate,
)
from loregraph.services.entity_template_service import template_to_fields

router = APIRouter(prefix="/projects/{project_id}/templates", tags=["templates"])


@router.get("", response_model=list[EntityTemplateOut])
async def list_templates(
    project_id: str, service: EntityTemplateServiceDep
) -> list[EntityTemplateOut]:
    return await service.list_templates(project_id)


@router.post("", response_model=EntityTemplateOut, status_code=201)
async def create_template(
    project_id: str,
    data: EntityTemplateCreate,
    service: EntityTemplateServiceDep,
) -> EntityTemplateOut:
    return await service.create(project_id, data)


@router.get("/{template_id}", response_model=EntityTemplateOut)
async def get_template(
    project_id: str, template_id: str, service: EntityTemplateServiceDep
) -> EntityTemplateOut:
    return await service.get_for_project(project_id, template_id)


@router.put("/{template_id}", response_model=EntityTemplateOut)
async def update_template(
    project_id: str,
    template_id: str,
    data: EntityTemplateUpdate,
    service: EntityTemplateServiceDep,
) -> EntityTemplateOut:
    return await service.update(project_id, template_id, data)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    project_id: str, template_id: str, service: EntityTemplateServiceDep
) -> None:
    await service.delete(project_id, template_id)


@router.post("/{template_id}/instantiate", response_model=EntityOut, status_code=201)
async def instantiate_template(
    project_id: str,
    template_id: str,
    data: TemplateInstantiate,
    template_service: EntityTemplateServiceDep,
    entity_service: EntityServiceDep,
) -> EntityOut:
    """Create a new entity pre-filled from a template. Fields come from the
    template's defaults; the entity flows through EntityService — the single
    write path shared with the REST editor, the agent and MCP."""
    template = await template_service.get_for_project(project_id, template_id)
    create = EntityCreate(
        type=template.entity_type,
        title=data.title,
        fields=template_to_fields(template),
        template_id=template.id,
    )
    return await entity_service.create(create, project_id)
