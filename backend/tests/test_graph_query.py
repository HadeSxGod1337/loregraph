import pytest
from fastapi.testclient import TestClient

FixtureGraph = dict[str, str]


@pytest.fixture
def fixture_graph(client: TestClient, project_id: str) -> FixtureGraph:
    def make(title: str, entity_type: str = "location") -> str:
        entity_id = client.post(
            f"/api/projects/{project_id}/entities",
            json={"type": entity_type, "title": title},
        ).json()["id"]
        assert isinstance(entity_id, str)
        return entity_id

    def link(source: str, target: str, edge_type: str) -> None:
        client.post(
            f"/api/projects/{project_id}/edges",
            json={
                "source_entity_id": source,
                "target_entity_id": target,
                "type": edge_type,
            },
        )

    world = make("World")
    city = make("City")
    tavern = make("Tavern")
    npc_a = make("NPC_A", "npc")
    npc_b = make("NPC_B", "npc")
    faction_x = make("Faction_X", "faction")
    entity_z = make("Entity_Z")

    link(world, city, "contains")
    link(city, tavern, "contains")
    link(tavern, npc_a, "contains")
    link(npc_a, npc_b, "family_of")
    link(npc_a, faction_x, "ally_of")

    a2, b2, c2 = make("A2", "npc"), make("B2", "npc"), make("C2", "npc")
    link(a2, b2, "knows")
    link(b2, c2, "knows")
    link(c2, a2, "knows")

    return {
        "world": world,
        "city": city,
        "tavern": tavern,
        "npc_a": npc_a,
        "npc_b": npc_b,
        "faction_x": faction_x,
        "entity_z": entity_z,
        "a2": a2,
        "b2": b2,
        "c2": c2,
    }


def _node_ids(response_json: dict[str, object]) -> set[str]:
    nodes = response_json["nodes"]
    assert isinstance(nodes, list)
    return {n["id"] for n in nodes}


def test_depth_0_returns_only_root(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": fixture_graph["world"], "depth": 0},
    )
    body = resp.json()
    assert _node_ids(body) == {fixture_graph["world"]}
    assert body["edges"] == []


def test_depth_1_immediate_neighbors_only(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": fixture_graph["world"], "depth": 1},
    )
    assert _node_ids(resp.json()) == {fixture_graph["world"], fixture_graph["city"]}


def test_depth_2_transitive_not_further(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": fixture_graph["world"], "depth": 2},
    )
    assert _node_ids(resp.json()) == {
        fixture_graph["world"],
        fixture_graph["city"],
        fixture_graph["tavern"],
    }


def test_edge_type_filter_excludes_other_types(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={
            "root_id": fixture_graph["npc_a"],
            "depth": 2,
            "edge_type": "family_of",
        },
    )
    ids = _node_ids(resp.json())
    assert fixture_graph["faction_x"] not in ids
    assert fixture_graph["npc_b"] in ids


def test_undirected_traversal_shows_container_from_child(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": fixture_graph["tavern"], "depth": 1},
    )
    assert fixture_graph["city"] in _node_ids(resp.json())


def test_unknown_root_is_404(client: TestClient, project_id: str) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": "missing", "depth": 1},
    )
    assert resp.status_code == 404


def test_root_from_another_project_is_404(client: TestClient, project_id: str) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    other_root = client.post(
        f"/api/projects/{other_project}/entities",
        json={"type": "npc", "title": "Elsewhere"},
    ).json()["id"]

    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": other_root, "depth": 1},
    )
    assert resp.status_code == 404


def test_cyclic_graph_has_no_duplicate_nodes(
    client: TestClient, project_id: str, fixture_graph: FixtureGraph
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/graph/subgraph",
        params={"root_id": fixture_graph["a2"], "depth": 5},
    )
    ids = _node_ids(resp.json())
    assert ids == {fixture_graph["a2"], fixture_graph["b2"], fixture_graph["c2"]}
