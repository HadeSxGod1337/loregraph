"""Patch semantics: an edit that names only some fields must leave everything
it did not name byte-for-byte intact.

This is the store-level guarantee the agent's edit path depends on. Before
`patch`, the agent edited through `EntityUpdate` (a whole-row replace) while
reading the entity as flat text — so `template_id`, attachment fields, and the
per-field `show_on_card` / `visible_to_players` flags were silently wiped on
every agent edit. These tests pin that they no longer can be.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.schemas.entity import (
    AttachmentRef,
    EntityCreate,
    EntityFieldIn,
    EntityPatch,
    FieldType,
)
from loregraph.schemas.project import ProjectCreate
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


@pytest_asyncio.fixture
async def store_and_project(
    tmp_path: Path,
) -> AsyncGenerator[tuple[SqliteEntityStore, str], None]:
    engine = create_engine_for(tmp_path / "patch.sqlite3")
    await init_db(engine)
    session: AsyncSession = make_session_factory(engine)()
    project = await SqliteProjectStore(session).create(ProjectCreate(name="P"))
    try:
        yield SqliteEntityStore(session), project.id
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_patch_preserves_template_id(
    store_and_project: tuple[SqliteEntityStore, str],
) -> None:
    store, project_id = store_and_project
    created = await store.create(
        EntityCreate(type="npc", title="Егор", template_id="tmpl_hero"),
        project_id,
    )

    patched = await store.patch(
        created.id,
        EntityPatch(
            set_fields=[
                EntityFieldIn(key="role", field_type=FieldType.TEXT, value="маг")
            ]
        ),
    )

    assert patched.template_id == "tmpl_hero"


@pytest.mark.asyncio
async def test_patch_keeps_untouched_field_flags(
    store_and_project: tuple[SqliteEntityStore, str],
) -> None:
    store, project_id = store_and_project
    created = await store.create(
        EntityCreate(
            type="npc",
            title="Егор",
            fields=[
                EntityFieldIn(
                    key="secret",
                    field_type=FieldType.TEXT,
                    value="hidden",
                    visible_to_players=False,
                ),
                EntityFieldIn(
                    key="motto",
                    field_type=FieldType.TEXT,
                    value="onward",
                    show_on_card=True,
                    visible_to_players=True,
                ),
            ],
        ),
        project_id,
    )

    # Edit only `secret`; `motto` is not named at all.
    patched = await store.patch(
        created.id,
        EntityPatch(
            set_fields=[
                EntityFieldIn(key="secret", field_type=FieldType.TEXT, value="revealed")
            ]
        ),
    )

    by_key = {f.key: f for f in patched.fields}
    # Untouched field keeps its flags verbatim.
    assert by_key["motto"].value == "onward"
    assert by_key["motto"].show_on_card is True
    assert by_key["motto"].visible_to_players is True
    # Edited field's value changed but its player visibility was NOT reset to
    # the schema default — the editor never expressed an opinion about it.
    assert by_key["secret"].value == "revealed"
    assert by_key["secret"].visible_to_players is False


@pytest.mark.asyncio
async def test_patch_preserves_attachment_field(
    store_and_project: tuple[SqliteEntityStore, str],
) -> None:
    store, project_id = store_and_project
    attachment = AttachmentRef(attachment_id="att_1", url="/files/att_1")
    created = await store.create(
        EntityCreate(
            type="npc",
            title="Егор",
            fields=[
                EntityFieldIn(
                    key="portrait",
                    field_type=FieldType.ATTACHMENT,
                    value=attachment.model_dump(),
                ),
                EntityFieldIn(key="bio", field_type=FieldType.TEXT, value="old"),
            ],
        ),
        project_id,
    )

    patched = await store.patch(
        created.id,
        EntityPatch(
            set_fields=[
                EntityFieldIn(key="bio", field_type=FieldType.TEXT, value="new")
            ]
        ),
    )

    by_key = {f.key: f for f in patched.fields}
    assert by_key["portrait"].field_type == FieldType.ATTACHMENT
    assert by_key["bio"].value == "new"


@pytest.mark.asyncio
async def test_patch_upserts_and_removes_only_named_keys(
    store_and_project: tuple[SqliteEntityStore, str],
) -> None:
    store, project_id = store_and_project
    created = await store.create(
        EntityCreate(
            type="npc",
            title="Егор",
            fields=[
                EntityFieldIn(key="a", field_type=FieldType.TEXT, value="1"),
                EntityFieldIn(key="b", field_type=FieldType.TEXT, value="2"),
            ],
        ),
        project_id,
    )

    patched = await store.patch(
        created.id,
        EntityPatch(
            set_fields=[
                EntityFieldIn(key="b", field_type=FieldType.TEXT, value="22"),
                EntityFieldIn(key="c", field_type=FieldType.TEXT, value="3"),
            ],
            remove_field_keys=["a"],
        ),
    )

    by_key = {f.key: f.value for f in patched.fields}
    assert "a" not in by_key  # explicitly removed
    assert by_key["b"] == "22"  # updated in place
    assert by_key["c"] == "3"  # appended


@pytest.mark.asyncio
async def test_patch_updates_title_and_type_when_named(
    store_and_project: tuple[SqliteEntityStore, str],
) -> None:
    store, project_id = store_and_project
    created = await store.create(EntityCreate(type="npc", title="Егор"), project_id)

    unchanged = await store.patch(created.id, EntityPatch())
    assert unchanged.title == "Егор"
    assert unchanged.type == "npc"

    renamed = await store.patch(created.id, EntityPatch(title="Егор Тень"))
    assert renamed.title == "Егор Тень"
    assert renamed.type == "npc"  # not named → unchanged
