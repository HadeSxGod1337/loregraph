"""The assistant's read tools against real SQLite stores.

These cover the three ways the assistant used to mislead a game master:
denying a relationship that exists (it could not see the edge table at all),
answering "how many X" from a five-result semantic search, and presenting a
capped list as if it were the whole world.
"""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.skills.registry import LIST_ENTITIES_LIMIT
from loregraph.agent.state import AgentState
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, FieldType
from loregraph.schemas.project import ProjectCreate
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore


class FakeEmbedder:
    """Deterministic embeddings without any model download — same rationale
    as test_vector_index.py's FakeEmbedder (duplicated per-file per this
    codebase's convention for small fakes)."""

    model_id = "fake-embedder-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255.0 for b in digest[:16]])
        return vectors


class World:
    """One project's stores plus the tool executor over them, so each test
    reads as "put this in the world, ask the assistant, check the answer"."""

    def __init__(self, session: AsyncSession, project_id: str) -> None:
        self.session = session
        self.project_id = project_id
        self.entities = SqliteEntityStore(session)
        self.edges = SqliteEdgeStore(session)
        # None (the make_graph-style default) unless a test opts in — most of
        # this file's tools have nothing to do with the knowledge base.
        self.knowledge_index: KnowledgeIndex | None = None

    async def entity(self, entity_type: str, title: str, **text_fields: str) -> str:
        entity = await self.entities.create(
            EntityCreate(
                type=entity_type,
                title=title,
                fields=[
                    EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value)
                    for key, value in text_fields.items()
                ],
            ),
            self.project_id,
        )
        return entity.id

    async def edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        label: str | None = None,
    ) -> str:
        edge = await self.edges.create(
            EdgeCreate(
                source_entity_id=source_id,
                target_entity_id=target_id,
                type=edge_type,
                label=label,
            ),
            self.project_id,
        )
        return edge.id

    async def call(self, name: str, args: dict[str, Any]) -> str:
        """Drives the real executor with the vector index absent — every tool
        under test here is a store query, not a similarity search."""
        call = {"name": name, "args": args, "id": "call-1"}
        update = await run_tools(
            AgentState(
                project_id=self.project_id,
                messages=[AIMessage("", tool_calls=[call])],
            ),
            vector_index=None,
            knowledge_index=self.knowledge_index,
            entity_store=self.entities,
            edge_store=self.edges,
        )
        return str(update["messages"][0].content)


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def world(db_session: AsyncSession) -> World:
    project = await SqliteProjectStore(db_session).create(
        ProjectCreate(name="Test world")
    )
    return World(db_session, project.id)


@pytest.mark.asyncio
async def test_entity_details_reports_relationships_absent_from_fields(
    world: World,
) -> None:
    """The regression this whole change exists for: an enemy_of edge stored in
    the graph, mentioned nowhere in either entity's fields."""
    sixwinged = await world.entity("faction", "Шестикрылые")
    eyeless = await world.entity("faction", "Безглазые", leader="Ортус")
    edge_id = await world.edge(sixwinged, eyeless, "enemy_of")

    content = await world.call("get_entity_details", {"entity_id": eyeless})

    assert "enemy_of" in content
    assert "Шестикрылые" in content
    # The edge id is what manage_relationships needs to act on it.
    assert edge_id in content


@pytest.mark.asyncio
async def test_entity_details_says_none_rather_than_staying_silent(
    world: World,
) -> None:
    lonely = await world.entity("npc", "Егор")
    content = await world.call("get_entity_details", {"entity_id": lonely})
    assert "relationships: none recorded" in content


@pytest.mark.asyncio
async def test_entity_details_rejects_other_projects_entity(
    world: World, db_session: AsyncSession
) -> None:
    other_project = await SqliteProjectStore(db_session).create(
        ProjectCreate(name="Other world")
    )
    other = await SqliteEntityStore(db_session).create(
        EntityCreate(type="npc", title="Егор"), other_project.id
    )
    content = await world.call("get_entity_details", {"entity_id": other.id})
    assert content == f"Entity not found: {other.id}"


@pytest.mark.asyncio
async def test_list_entities_counts_namesakes(world: World) -> None:
    """«Сколько егоров в мире» — the question semantic top-k cannot answer."""
    for summary in ("Молодой маг-артефактор", "Старший товарищ", "Правитель"):
        await world.entity("npc", "Егор", summary=summary)
    await world.entity("npc", "Мира Кузнец")

    content = await world.call("list_entities", {"title_contains": "егор"})

    assert content.startswith("3 entities match")
    assert "Мира" not in content


@pytest.mark.asyncio
async def test_list_entities_reports_exact_total_when_capped(world: World) -> None:
    total = LIST_ENTITIES_LIMIT + 5
    for index in range(total):
        await world.entity("npc", f"Стражник {index}")

    content = await world.call("list_entities", {})

    assert content.startswith(f"{total} entities match")
    assert f"(showing {LIST_ENTITIES_LIMIT} of {total}" in content
    assert content.count("| npc |") == LIST_ENTITIES_LIMIT


@pytest.mark.asyncio
async def test_list_entities_breaks_down_by_type_when_unfiltered(
    world: World,
) -> None:
    await world.entity("npc", "Егор")
    await world.entity("faction", "Каменные Роки")
    await world.entity("faction", "Безглазые")

    content = await world.call("list_entities", {})

    assert "by type: faction 2, npc 1" in content


@pytest.mark.asyncio
async def test_list_entities_filters_by_type(world: World) -> None:
    await world.entity("npc", "Егор")
    await world.entity("faction", "Безглазые")

    content = await world.call("list_entities", {"entity_type": "faction"})

    assert content.startswith("1 entities match (type='faction')")
    assert "Егор" not in content


@pytest.mark.asyncio
async def test_entity_graph_shows_neighbours_at_depth_one(world: World) -> None:
    emperor = await world.entity("npc", "Император")
    clan = await world.entity("faction", "Каменные Роки")
    await world.edge(emperor, clan, "ally_of", "по договору")

    content = await world.call("get_entity_graph", {"entity_id": emperor})

    assert "ally_of" in content and "Каменные Роки" in content
    assert "(по договору)" in content


@pytest.mark.asyncio
async def test_entity_graph_clamps_depth(world: World) -> None:
    """A depth past the ceiling must still answer, bounded — not error and not
    walk the whole campaign."""
    first = await world.entity("npc", "A")
    second = await world.entity("npc", "B")
    third = await world.entity("npc", "C")
    fourth = await world.entity("npc", "D")
    await world.edge(first, second, "ally_of")
    await world.edge(second, third, "ally_of")
    await world.edge(third, fourth, "ally_of")

    content = await world.call("get_entity_graph", {"entity_id": first, "depth": 9})

    assert "at depth 2" in content
    assert third in content
    assert fourth not in content


@pytest.mark.asyncio
async def test_entity_graph_reports_isolated_entity(world: World) -> None:
    lonely = await world.entity("npc", "Егор")
    content = await world.call("get_entity_graph", {"entity_id": lonely})
    assert "no relationships" in content


@pytest.mark.asyncio
async def test_entity_graph_unknown_entity(world: World) -> None:
    content = await world.call("get_entity_graph", {"entity_id": "nope"})
    assert content == "Entity not found: nope"


@pytest.mark.asyncio
async def test_search_lore_without_vector_index_marks_truncation(
    world: World,
) -> None:
    for index in range(4):
        await world.entity("npc", f"Егор {index}")

    content = await world.call("search_lore", {"query": "Егор", "limit": 2})

    assert "(showing 2 of 4" in content


@pytest.mark.asyncio
async def test_search_lore_filters_by_type(world: World) -> None:
    await world.entity("npc", "Тайный орден Егора")
    await world.entity("faction", "Орден Егора")

    content = await world.call(
        "search_lore", {"query": "Егор", "entity_type": "faction"}
    )

    assert "| faction |" in content
    assert "| npc |" not in content


@pytest.mark.asyncio
async def test_search_lore_annotates_relationship_census(world: World) -> None:
    eyeless = await world.entity("faction", "Безглазые")
    sixwinged = await world.entity("faction", "Шестикрылые")
    ally = await world.entity("npc", "Джин")
    await world.edge(sixwinged, eyeless, "enemy_of")
    await world.edge(ally, eyeless, "ally_of")

    content = await world.call("search_lore", {"query": "Безглазые"})

    assert "[ally_of ×1, enemy_of ×1]" in content


# ---------------------------------------------------------------------------
# list_relationships — complete, paged enumeration (the fourth way the
# assistant used to mislead: presenting the first slice of a hub entity's edges
# as if it were the whole neighborhood, with no way to reach the rest).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_relationships_pages_a_high_degree_entity(world: World) -> None:
    """ "Покажи все связи X" on a 70-edge hub must not silently become the first
    40: the total is exact, and a cursor makes the remainder reachable."""
    hub = await world.entity("faction", "Гильдия")
    for index in range(70):
        member = await world.entity("npc", f"Член {index}")
        await world.edge(hub, member, "member_of")

    page1 = await world.call("list_relationships", {"entity_id": hub})
    assert "70 relationship(s)" in page1
    assert "70 outgoing, 0 incoming" in page1
    assert page1.count("[out]") == 40
    assert "cursor=40 for the next page" in page1

    page2 = await world.call("list_relationships", {"entity_id": hub, "cursor": 40})
    assert page2.count("[out]") == 30
    assert "this is all of them" in page2

    # Following the cursor reaches every edge exactly once — the "all
    # relationships" the truncated single page could never deliver.
    shown = {
        line for page in (page1, page2) for line in page.splitlines() if "[out]" in line
    }
    assert len(shown) == 70


@pytest.mark.asyncio
async def test_list_relationships_separates_incoming_and_outgoing(world: World) -> None:
    a = await world.entity("npc", "A")
    b = await world.entity("npc", "B")
    c = await world.entity("npc", "C")
    await world.edge(a, b, "ally_of")  # outgoing from A
    await world.edge(c, a, "enemy_of")  # incoming to A

    content = await world.call("list_relationships", {"entity_id": a})
    assert "1 outgoing, 1 incoming" in content
    assert "[out]" in content and "[in]" in content

    only_in = await world.call(
        "list_relationships", {"entity_id": a, "direction": "incoming"}
    )
    assert "[in]" in only_in and "[out]" not in only_in
    assert "enemy_of" in only_in and "ally_of" not in only_in


@pytest.mark.asyncio
async def test_list_relationships_filters_by_type(world: World) -> None:
    a = await world.entity("npc", "A")
    b = await world.entity("npc", "B")
    c = await world.entity("npc", "C")
    await world.edge(a, b, "ally_of")
    await world.edge(a, c, "enemy_of")

    content = await world.call(
        "list_relationships", {"entity_id": a, "type": "ally_of"}
    )
    assert "ally_of" in content
    assert "enemy_of" not in content
    assert "1 relationship(s)" in content


@pytest.mark.asyncio
async def test_list_relationships_reports_none_for_isolated(world: World) -> None:
    lonely = await world.entity("npc", "Егор")
    content = await world.call("list_relationships", {"entity_id": lonely})
    assert "no relationships" in content


@pytest.mark.asyncio
async def test_list_relationships_unknown_entity(world: World) -> None:
    content = await world.call("list_relationships", {"entity_id": "nope"})
    assert content == "Entity not found: nope"


# ---------------------------------------------------------------------------
# search_knowledge_base — the one tool in this registry with no coverage here
# at all before this P0: every other read tool above is exercised against the
# real executor, but a call to search_knowledge_base was never driven through
# it, so a break in this specific case dispatch would have gone unnoticed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_knowledge_base_returns_matching_chunks(
    world: World, tmp_path: Path
) -> None:
    world.knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )
    await world.knowledge_index.index_source(
        world.project_id,
        "setting-bible",
        ["Город Норвинтер получает всю энергию от Сердца Титана."],
    )

    content = await world.call(
        "search_knowledge_base", {"query": "источник энергии Норвинтера"}
    )

    assert "Сердца Титана" in content


@pytest.mark.asyncio
async def test_search_knowledge_base_reports_no_match_distinctly(
    world: World, tmp_path: Path
) -> None:
    """A configured but empty/irrelevant index must read differently from the
    index being absent entirely (see the next test) — the diagnostic
    distinction the P0 asked for, visible here in the tool result text."""
    world.knowledge_index = KnowledgeIndex(
        ChromaVectorStore(tmp_path / "chroma", FakeEmbedder())
    )

    content = await world.call("search_knowledge_base", {"query": "что угодно"})

    assert content == "No knowledge base documents matched this query."


@pytest.mark.asyncio
async def test_search_knowledge_base_unavailable_without_index(world: World) -> None:
    # world.knowledge_index stays None — embeddings disabled for this deployment.
    content = await world.call("search_knowledge_base", {"query": "что угодно"})
    assert "unavailable" in content
