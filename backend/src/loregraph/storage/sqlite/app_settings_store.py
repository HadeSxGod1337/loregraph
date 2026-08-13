import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.storage.sqlite.models import AppSettingRow


class SqliteAppSettingsStore:
    """Persisted overrides of `Settings` fields, keyed by field name.

    Knows nothing about which fields are legal — that is the settings
    service's whitelist (config.UI_EDITABLE_FIELDS), applied on both write
    and read so an old or hand-edited row can never widen it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self) -> dict[str, Any]:
        rows = (await self._session.execute(select(AppSettingRow))).scalars().all()
        loaded: dict[str, Any] = {}
        for row in rows:
            try:
                loaded[row.key] = json.loads(row.value_json)
            except json.JSONDecodeError:
                # A corrupted single value must not take the app down: it is
                # dropped, and the env/default value applies instead.
                continue
        return loaded

    async def set_many(self, values: Mapping[str, Any]) -> None:
        now = datetime.now(UTC)
        for key, value in values.items():
            row = await self._session.get(AppSettingRow, key)
            if row is None:
                self._session.add(
                    AppSettingRow(key=key, value_json=json.dumps(value), updated_at=now)
                )
            else:
                row.value_json = json.dumps(value)
                row.updated_at = now
        await self._session.commit()

    async def delete_keys(self, keys: Sequence[str]) -> None:
        key_list = list(keys)
        if not key_list:
            return
        await self._session.execute(
            delete(AppSettingRow).where(AppSettingRow.key.in_(key_list))
        )
        await self._session.commit()
