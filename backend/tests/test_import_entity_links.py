from fastapi.testclient import TestClient


def test_import_remaps_entity_link_ids(client: TestClient) -> None:
    """entityLink nodes inside rich text must point at the freshly created
    entity ids after import — import never reuses ids from the file."""
    export = {
        "format_version": 1,
        "name": "Linked World",
        "description": None,
        "entities": [
            {
                "id": "old-mira",
                "type": "npc",
                "title": "Мира",
                "fields": [],
                "icon_attachment_id": None,
            },
            {
                "id": "old-guild",
                "type": "faction",
                "title": "Гильдия",
                "fields": [
                    {
                        "key": "notes",
                        "field_type": "rich_text",
                        "value": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "entityLink",
                                            "attrs": {
                                                "entityId": "old-mira",
                                                "label": "Мира",
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                        "show_on_card": False,
                    }
                ],
                "icon_attachment_id": None,
            },
        ],
        "edges": [],
        "attachments": [],
    }
    resp = client.post("/api/projects/import", json=export)
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    entities = client.get(f"/api/projects/{project_id}/entities").json()
    by_title = {e["title"]: e for e in entities}
    new_mira_id = by_title["Мира"]["id"]
    assert new_mira_id != "old-mira"

    link_node = by_title["Гильдия"]["fields"][0]["value"]["content"][0]["content"][0]
    assert link_node["type"] == "entityLink"
    assert link_node["attrs"]["entityId"] == new_mira_id
    assert link_node["attrs"]["label"] == "Мира"
