from fastapi.testclient import TestClient

from loregraph.connectors.longstoryshort import parser
from loregraph.schemas.entity import FieldType
from loregraph.services.entity_template_service import template_to_fields
from loregraph.templates import builtin_templates

# --- unit: instantiation --------------------------------------------------


def _character() -> object:
    return next(t for t in builtin_templates() if t.id == "builtin_character")


def test_template_to_fields_fills_type_appropriate_defaults() -> None:
    fields = {f.key: f for f in template_to_fields(_character())}  # type: ignore[arg-type]
    assert fields["str"].field_type is FieldType.NUMBER
    assert fields["str"].value == 0
    assert fields["backstory"].field_type is FieldType.RICH_TEXT
    assert fields["backstory"].value == {
        "type": "doc",
        "content": [{"type": "paragraph"}],
    }
    assert fields["class"].value == ""
    # show_on_card carries through from the field def
    assert fields["class"].show_on_card is True


def test_template_to_fields_deep_copies_mutable_defaults() -> None:
    first = {f.key: f for f in template_to_fields(_character())}  # type: ignore[arg-type]
    second = {f.key: f for f in template_to_fields(_character())}  # type: ignore[arg-type]
    first["backstory"].value["content"].append({"type": "paragraph"})
    # Mutating one instance must not leak into another instantiation.
    assert len(second["backstory"].value["content"]) == 1


def test_character_template_covers_lss_importer_keys() -> None:
    expected = (
        set(parser._TEXT_FIELDS)
        | set(parser._NUMBER_FIELDS)
        | set(parser._ABILITY_KEYS)
        | set(parser._NATIVE_TEXT_BLOCKS)
        | {parser.CHARACTER_SHEET_URL_KEY}
    )
    keys = {f.key for f in _character().field_defs}  # type: ignore[attr-defined]
    assert expected <= keys


def test_builtins_all_validate() -> None:
    # Construction runs the layout validator; a bad field_key/widget would raise.
    assert [t.id for t in builtin_templates()] == [
        "builtin_character",
        "builtin_npc",
        "builtin_location",
        "builtin_faction",
    ]


# --- API: listing & instantiation ----------------------------------------


def test_list_returns_builtins_for_fresh_project(
    client: TestClient, project_id: str
) -> None:
    resp = client.get(f"/api/projects/{project_id}/templates")
    assert resp.status_code == 200
    body = resp.json()
    ids = {t["id"] for t in body}
    assert {"builtin_character", "builtin_npc", "builtin_location"} <= ids
    assert all(t["is_builtin"] for t in body)


def test_instantiate_builtin_creates_prefilled_entity(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/templates/builtin_character/instantiate",
        json={"title": "Чез"},
    )
    assert resp.status_code == 201
    entity = resp.json()
    assert entity["type"] == "party_member"
    assert entity["title"] == "Чез"
    keys = {f["key"] for f in entity["fields"]}
    assert {"str", "backstory", "character_sheet_url"} <= keys


def test_instantiate_binds_template_id(client: TestClient, project_id: str) -> None:
    entity = client.post(
        f"/api/projects/{project_id}/templates/builtin_character/instantiate",
        json={"title": "Чез"},
    ).json()
    assert entity["template_id"] == "builtin_character"


def test_update_sets_and_clears_template_id(
    client: TestClient, project_id: str
) -> None:
    created = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Mira"},
    ).json()
    assert created["template_id"] is None

    bound = client.put(
        f"/api/projects/{project_id}/entities/{created['id']}",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [],
            "template_id": "builtin_npc",
        },
    ).json()
    assert bound["template_id"] == "builtin_npc"

    cleared = client.put(
        f"/api/projects/{project_id}/entities/{created['id']}",
        json={"type": "npc", "title": "Mira", "fields": [], "template_id": None},
    ).json()
    assert cleared["template_id"] is None


def test_instantiate_unknown_template_404(client: TestClient, project_id: str) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/templates/nope/instantiate",
        json={"title": "X"},
    )
    assert resp.status_code == 404


# --- API: user templates CRUD --------------------------------------------

_USER_TEMPLATE = {
    "name": "Мой NPC",
    "entity_type": "npc",
    "field_defs": [{"key": "role", "field_type": "text", "label": "Роль"}],
    "layout": {
        "regions": [
            {
                "name": "Шапка",
                "kind": "band",
                "blocks": [{"widget": "plain", "field_key": "role"}],
            }
        ]
    },
}


def test_create_update_delete_user_template(
    client: TestClient, project_id: str
) -> None:
    created = client.post(f"/api/projects/{project_id}/templates", json=_USER_TEMPLATE)
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert created.json()["is_builtin"] is False

    listed = client.get(f"/api/projects/{project_id}/templates").json()
    assert template_id in {t["id"] for t in listed}

    updated = client.put(
        f"/api/projects/{project_id}/templates/{template_id}",
        json={**_USER_TEMPLATE, "name": "NPC v2"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "NPC v2"

    assert (
        client.delete(f"/api/projects/{project_id}/templates/{template_id}").status_code
        == 204
    )
    assert (
        client.get(f"/api/projects/{project_id}/templates/{template_id}").status_code
        == 404
    )


def test_editing_builtin_is_conflict(client: TestClient, project_id: str) -> None:
    resp = client.put(
        f"/api/projects/{project_id}/templates/builtin_character",
        json=_USER_TEMPLATE,
    )
    assert resp.status_code == 409


def test_deleting_builtin_is_conflict(client: TestClient, project_id: str) -> None:
    resp = client.delete(f"/api/projects/{project_id}/templates/builtin_character")
    assert resp.status_code == 409


def test_template_from_another_project_is_404(
    client: TestClient, project_id: str
) -> None:
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    template_id = client.post(
        f"/api/projects/{project_id}/templates", json=_USER_TEMPLATE
    ).json()["id"]
    resp = client.get(f"/api/projects/{other}/templates/{template_id}")
    assert resp.status_code == 404


# --- API: layout validation ----------------------------------------------


def test_create_rejects_unknown_field_reference(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "entity_type": "npc",
        "field_defs": [{"key": "role", "field_type": "text"}],
        "layout": {
            "regions": [
                {
                    "name": "Шапка",
                    "kind": "band",
                    "blocks": [{"widget": "plain", "field_key": "missing"}],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=bad)
    assert resp.status_code == 422


def test_create_rejects_incompatible_widget(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "entity_type": "npc",
        "field_defs": [{"key": "role", "field_type": "text"}],
        # rich_text widget cannot render a TEXT field
        "layout": {
            "regions": [
                {
                    "name": "Шапка",
                    "kind": "band",
                    "blocks": [{"widget": "rich_text", "field_key": "role"}],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=bad)
    assert resp.status_code == 422


def test_create_rejects_computed_widget_without_formula(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "entity_type": "npc",
        "field_defs": [{"key": "str", "field_type": "number"}],
        "layout": {
            "regions": [
                {
                    "name": "Шапка",
                    "kind": "band",
                    "blocks": [{"widget": "computed", "label": "Атлетика"}],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=bad)
    assert resp.status_code == 422


def test_create_rejects_computed_widget_with_unknown_dependency(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "entity_type": "npc",
        "field_defs": [{"key": "str", "field_type": "number"}],
        "layout": {
            "regions": [
                {
                    "name": "Шапка",
                    "kind": "band",
                    "blocks": [
                        {
                            "widget": "computed",
                            "label": "Атлетика",
                            "formula": "floor((str - 10) / 2) + missing_field",
                        }
                    ],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=bad)
    assert resp.status_code == 422


def test_create_accepts_valid_computed_widget(
    client: TestClient, project_id: str
) -> None:
    ok = {
        "name": "Good",
        "entity_type": "npc",
        "field_defs": [{"key": "str", "field_type": "number"}],
        "layout": {
            "regions": [
                {
                    "name": "Шапка",
                    "kind": "band",
                    "blocks": [
                        {
                            "widget": "computed",
                            "label": "Атлетика",
                            "formula": "floor((str - 10) / 2)",
                        }
                    ],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=ok)
    assert resp.status_code == 201


def test_create_rejects_region_shape_mismatching_kind(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "entity_type": "npc",
        "field_defs": [],
        "layout": {
            "regions": [
                {
                    "name": "Bad region",
                    "kind": "columns",
                    "blocks": [{"widget": "heading", "label": "oops"}],
                }
            ]
        },
    }
    resp = client.post(f"/api/projects/{project_id}/templates", json=bad)
    assert resp.status_code == 422
