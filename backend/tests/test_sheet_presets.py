from fastapi.testclient import TestClient

from loregraph.templates import builtin_presets

# --- unit: builtins --------------------------------------------------------


def test_builtin_presets_all_validate() -> None:
    # Construction runs SheetPresetBase's section validator; a bad
    # field_key/widget/formula would raise.
    assert [p.id for p in builtin_presets()] == [
        "preset_ability_skills",
        "preset_resource",
        "preset_checklist",
    ]


def test_ability_skills_preset_derives_everything_from_one_editable_score() -> None:
    preset = next(p for p in builtin_presets() if p.id == "preset_ability_skills")
    score, *derived = preset.section.blocks
    # The single editable input — dropping it strands every formula below on
    # a score nobody can type in.
    assert score.widget == "stat_modifier"
    assert score.field_key == "dex"
    assert all(block.widget == "computed" for block in derived)
    assert all(block.formula for block in derived)


# --- API: listing -----------------------------------------------------------


def test_list_returns_builtin_presets_for_fresh_project(
    client: TestClient, project_id: str
) -> None:
    resp = client.get(f"/api/projects/{project_id}/sheet-presets")
    assert resp.status_code == 200
    body = resp.json()
    ids = {p["id"] for p in body}
    assert {"preset_ability_skills", "preset_resource", "preset_checklist"} <= ids
    assert all(p["is_builtin"] for p in body)


# --- API: user presets CRUD -------------------------------------------------

_USER_PRESET = {
    "name": "Мой пресет",
    "field_defs": [{"key": "note", "field_type": "text", "label": "Заметка"}],
    "section": {
        "title": "Заметки",
        "blocks": [{"widget": "plain", "field_key": "note"}],
    },
}


def test_create_and_delete_user_preset(client: TestClient, project_id: str) -> None:
    created = client.post(
        f"/api/projects/{project_id}/sheet-presets", json=_USER_PRESET
    )
    assert created.status_code == 201
    body = created.json()
    assert body["is_builtin"] is False
    preset_id = body["id"]

    listed = client.get(f"/api/projects/{project_id}/sheet-presets").json()
    assert preset_id in {p["id"] for p in listed}

    assert (
        client.delete(
            f"/api/projects/{project_id}/sheet-presets/{preset_id}"
        ).status_code
        == 204
    )
    listed_after = client.get(f"/api/projects/{project_id}/sheet-presets").json()
    assert preset_id not in {p["id"] for p in listed_after}


def test_deleting_builtin_preset_is_conflict(
    client: TestClient, project_id: str
) -> None:
    resp = client.delete(
        f"/api/projects/{project_id}/sheet-presets/preset_ability_skills"
    )
    assert resp.status_code == 409


def test_create_preset_rejects_unknown_field_reference(
    client: TestClient, project_id: str
) -> None:
    bad = {
        "name": "Bad",
        "field_defs": [{"key": "note", "field_type": "text"}],
        "section": {
            "title": "Заметки",
            "blocks": [{"widget": "plain", "field_key": "missing"}],
        },
    }
    resp = client.post(f"/api/projects/{project_id}/sheet-presets", json=bad)
    assert resp.status_code == 422
