"""A sheet has to survive being moved to another machine.

An entity carries only a `template_id`; the layout itself lives in a project
template row. Export used to leave those rows behind, so an imported campaign
kept ids pointing at nothing and every custom sheet quietly collapsed into a
plain field list.
"""

from fastapi.testclient import TestClient

_USER_TEMPLATE = {
    "name": "Мой NPC",
    "entity_type": "npc",
    "field_defs": [
        {"key": "role", "field_type": "text", "label": "Роль"},
        {"key": "str", "field_type": "number", "label": "Сила"},
    ],
    "layout": {
        "regions": [
            {
                "name": "Шапка",
                "kind": "band",
                "blocks": [
                    {"widget": "plain", "field_key": "role"},
                    {
                        "widget": "stat_modifier",
                        "field_key": "str",
                        "config": {"mod_formula": "floor((value - 10) / 2)"},
                    },
                ],
            }
        ]
    },
}

_USER_PRESET = {
    "name": "Мой блок",
    "field_defs": [{"key": "morale", "field_type": "number", "label": "Мораль"}],
    "section": {
        "title": "Состояние",
        "columns": 1,
        "blocks": [{"widget": "dots", "field_key": "morale", "config": {"max": 5}}],
    },
}


def _bind(client: TestClient, project_id: str, template_id: str | None) -> None:
    """Create one entity bound to `template_id` (or to nothing)."""
    entity = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "role", "field_type": "text", "value": "кузнец"}],
            "template_id": template_id,
        },
    )
    assert entity.status_code == 201


def test_user_template_travels_and_entities_rebind(
    client: TestClient, project_id: str
) -> None:
    source_template_id = client.post(
        f"/api/projects/{project_id}/templates", json=_USER_TEMPLATE
    ).json()["id"]
    _bind(client, project_id, source_template_id)

    export = client.get(f"/api/projects/{project_id}/export").json()
    imported_id = client.post("/api/projects/import", json=export).json()["id"]

    templates = client.get(f"/api/projects/{imported_id}/templates").json()
    moved = next(t for t in templates if t["name"] == "Мой NPC")
    # A fresh id, like every other imported row — importing the same file twice
    # must not collide.
    assert moved["id"] != source_template_id
    assert moved["project_id"] == imported_id
    assert moved["is_builtin"] is False
    # The layout is what makes it a sheet rather than a field list.
    blocks = moved["layout"]["regions"][0]["blocks"]
    assert [b["widget"] for b in blocks] == ["plain", "stat_modifier"]
    assert blocks[1]["config"]["mod_formula"] == "floor((value - 10) / 2)"

    entities = client.get(f"/api/projects/{imported_id}/entities").json()
    mira = next(e for e in entities if e["title"] == "Mira")
    # Rebound to the moved template, not left pointing at the source id.
    assert mira["template_id"] == moved["id"]


def test_builtin_binding_survives_unchanged(
    client: TestClient, project_id: str
) -> None:
    """Built-ins are code, not rows: the same id exists in every install, so it
    must be passed through rather than remapped or dropped."""
    _bind(client, project_id, "builtin_character")

    export = client.get(f"/api/projects/{project_id}/export").json()
    # Nothing to carry — a built-in is not a project template.
    assert export["templates"] == []

    imported_id = client.post("/api/projects/import", json=export).json()["id"]
    entities = client.get(f"/api/projects/{imported_id}/entities").json()
    assert next(e for e in entities)["template_id"] == "builtin_character"


def test_user_preset_travels(client: TestClient, project_id: str) -> None:
    client.post(f"/api/projects/{project_id}/sheet-presets", json=_USER_PRESET)

    export = client.get(f"/api/projects/{project_id}/export").json()
    imported_id = client.post("/api/projects/import", json=export).json()["id"]

    presets = client.get(f"/api/projects/{imported_id}/sheet-presets").json()
    moved = next(p for p in presets if p["name"] == "Мой блок")
    assert moved["is_builtin"] is False
    assert moved["section"]["blocks"][0]["field_key"] == "morale"


def test_export_without_templates_key_imports(
    client: TestClient, project_id: str
) -> None:
    """A file written before templates were exported: the keys are simply
    absent, and it must still import (with whatever bindings it carried)."""
    _bind(client, project_id, None)
    export = client.get(f"/api/projects/{project_id}/export").json()
    del export["templates"]
    del export["sheet_presets"]

    resp = client.post("/api/projects/import", json=export)
    assert resp.status_code == 201
    entities = client.get(f"/api/projects/{resp.json()['id']}/entities").json()
    assert next(e for e in entities)["template_id"] is None


def test_unknown_template_id_degrades_to_plain_fields(
    client: TestClient, project_id: str
) -> None:
    """An id the file never carried (a template deleted before export, a
    hand-edited file) is left as written — the entity renders as a plain field
    list rather than the import failing."""
    _bind(client, project_id, None)
    export = client.get(f"/api/projects/{project_id}/export").json()
    export["entities"][0]["template_id"] = "no_such_template"

    resp = client.post("/api/projects/import", json=export)
    assert resp.status_code == 201
    entities = client.get(f"/api/projects/{resp.json()['id']}/entities").json()
    assert next(e for e in entities)["template_id"] == "no_such_template"
