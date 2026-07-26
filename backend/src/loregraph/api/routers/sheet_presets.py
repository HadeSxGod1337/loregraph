from fastapi import APIRouter

from loregraph.api.deps import SheetPresetServiceDep
from loregraph.schemas.sheet_preset import SheetPresetCreate, SheetPresetOut

router = APIRouter(
    prefix="/projects/{project_id}/sheet-presets", tags=["sheet-presets"]
)


@router.get("", response_model=list[SheetPresetOut])
async def list_presets(
    project_id: str, service: SheetPresetServiceDep
) -> list[SheetPresetOut]:
    return await service.list_presets(project_id)


@router.post("", response_model=SheetPresetOut, status_code=201)
async def create_preset(
    project_id: str, data: SheetPresetCreate, service: SheetPresetServiceDep
) -> SheetPresetOut:
    return await service.create(project_id, data)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    project_id: str, preset_id: str, service: SheetPresetServiceDep
) -> None:
    await service.delete(project_id, preset_id)
