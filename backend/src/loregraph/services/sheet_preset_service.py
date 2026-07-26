from loregraph.exceptions import BuiltinPresetReadOnlyError, SheetPresetNotFoundError
from loregraph.schemas.sheet_preset import SheetPresetCreate, SheetPresetOut
from loregraph.storage.protocols import SheetPresetStore
from loregraph.templates import builtin_presets


class SheetPresetService:
    """Merges built-in presets (defined in code) with a project's own saved
    presets behind one interface — same shape as EntityTemplateService.
    Built-ins are read-only: create/delete only ever touch project presets
    (there is no update; a preset is a small immutable bundle, re-create it
    to change it)."""

    def __init__(self, store: SheetPresetStore) -> None:
        self._store = store
        self._builtins = {p.id: p for p in builtin_presets()}

    async def list_presets(self, project_id: str) -> list[SheetPresetOut]:
        user_presets = await self._store.list_for_project(project_id)
        return [*self._builtins.values(), *user_presets]

    async def get_for_project(self, project_id: str, preset_id: str) -> SheetPresetOut:
        builtin = self._builtins.get(preset_id)
        if builtin is not None:
            return builtin
        preset = await self._store.get(preset_id)
        if preset.project_id != project_id:
            raise SheetPresetNotFoundError(preset_id)
        return preset

    async def create(self, project_id: str, data: SheetPresetCreate) -> SheetPresetOut:
        return await self._store.create(project_id, data)

    async def delete(self, project_id: str, preset_id: str) -> None:
        if preset_id in self._builtins:
            raise BuiltinPresetReadOnlyError(preset_id)
        await self.get_for_project(project_id, preset_id)
        await self._store.delete(preset_id)
