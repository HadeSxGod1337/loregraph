"""The settings API: what it exposes, what it refuses, and what it never
lets out — API keys in particular."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from loregraph.schemas.app_settings import SECRET_MASK_PREFIX


def _fields(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/settings")
    assert response.status_code == 200
    fields: dict[str, Any] = response.json()["fields"]
    return fields


def test_get_reports_value_and_source(client: TestClient) -> None:
    fields = _fields(client)

    # The conftest fixture passes llm_provider explicitly, so it counts as
    # env-supplied; a field nobody set is a default.
    assert fields["llm_provider"]["value"] == "anthropic"
    assert fields["llm_provider"]["source"] == "env"
    assert fields["llm_model_generation"]["source"] == "default"


def test_launch_only_settings_are_reported_read_only(client: TestClient) -> None:
    body = client.get("/api/settings").json()

    assert body["launch_only"]["trust_loopback"] is True
    # …and are not part of the editable field map.
    assert "trust_loopback" not in body["fields"]


def test_model_change_applies_without_a_restart(
    client: TestClient, app: FastAPI
) -> None:
    response = client.put(
        "/api/settings", json={"values": {"llm_model_generation": "some-new-model"}}
    )
    assert response.status_code == 200

    # The next request builds its chat model from this, so a changed model is
    # live immediately (see api/deps.get_settings).
    assert app.state.settings_provider.current.llm_model_generation == "some-new-model"
    assert _fields(client)["llm_model_generation"]["source"] == "db"


def test_change_survives_a_restart(client: TestClient, app: FastAPI) -> None:
    client.put("/api/settings", json={"values": {"llm_model_assistant": "persisted"}})

    # Same app object, fresh lifespan: overrides are re-read from the database.
    with TestClient(app, client=("127.0.0.1", 50000)) as restarted:
        assert (
            restarted.get("/api/settings").json()["fields"]["llm_model_assistant"][
                "value"
            ]
            == "persisted"
        )


def test_api_key_is_masked_and_never_returned(client: TestClient) -> None:
    secret = "sk-ant-supersecretvalue1234"
    client.put("/api/settings", json={"values": {"anthropic_api_key": secret}})

    body = client.get("/api/settings").text
    assert secret not in body

    field = _fields(client)["anthropic_api_key"]
    assert field["is_set"] is True
    assert field["value"] == f"{SECRET_MASK_PREFIX}1234"
    assert field["secret"] is True


def test_echoing_the_mask_back_keeps_the_stored_key(
    client: TestClient, app: FastAPI
) -> None:
    secret = "sk-ant-supersecretvalue1234"
    client.put("/api/settings", json={"values": {"anthropic_api_key": secret}})

    # What the form sends back when the user edited some other field.
    client.put(
        "/api/settings",
        json={
            "values": {
                "anthropic_api_key": f"{SECRET_MASK_PREFIX}1234",
                "llm_model_assistant": "other-model",
            }
        },
    )

    assert app.state.settings_provider.current.anthropic_api_key == secret


def test_emptying_a_key_clears_it(client: TestClient, app: FastAPI) -> None:
    client.put("/api/settings", json={"values": {"anthropic_api_key": "sk-ant-xyz"}})
    client.put("/api/settings", json={"values": {"anthropic_api_key": ""}})

    assert app.state.settings_provider.current.anthropic_api_key is None
    assert _fields(client)["anthropic_api_key"]["is_set"] is False


def test_llm_configured_flag_follows_the_key(client: TestClient) -> None:
    assert client.get("/api/settings").json()["llm_configured"] is False

    client.put("/api/settings", json={"values": {"anthropic_api_key": "sk-ant-xyz"}})

    assert client.get("/api/settings").json()["llm_configured"] is True


def test_non_editable_field_is_refused(client: TestClient, app: FastAPI) -> None:
    response = client.put("/api/settings", json={"values": {"trust_loopback": False}})

    assert response.status_code == 422
    assert response.json()["code"] == "settings_field_unknown"
    assert app.state.settings_provider.current.trust_loopback is True


def test_invalid_value_is_refused(client: TestClient) -> None:
    response = client.put("/api/settings", json={"values": {"llm_provider": "nope"}})

    assert response.status_code == 422
    assert response.json()["code"] == "settings_field_invalid"


def test_reset_returns_the_field_to_its_env_value(
    client: TestClient, app: FastAPI
) -> None:
    client.put("/api/settings", json={"values": {"llm_provider": "openai"}})
    assert app.state.settings_provider.current.llm_provider == "openai"

    response = client.delete("/api/settings/llm_provider")

    assert response.status_code == 200
    assert app.state.settings_provider.current.llm_provider == "anthropic"
    assert _fields(client)["llm_provider"]["source"] == "env"


def test_reset_of_a_non_editable_field_is_refused(client: TestClient) -> None:
    assert client.delete("/api/settings/trust_loopback").status_code == 422


def test_catalog_describes_providers_generically(client: TestClient) -> None:
    catalog = client.get("/api/settings/catalog").json()

    by_id = {provider["id"]: provider for provider in catalog["providers"]}
    assert by_id["anthropic"]["api_key_field"] == "anthropic_api_key"
    assert by_id["ollama"]["api_key_field"] is None
    assert by_id["ollama_cloud"]["api_key_field"] == "ollama_cloud_api_key"
    assert by_id["ollama_cloud"]["supports_model_listing"] is True
    assert by_id["anthropic"]["default_models"]["generation"]
    assert catalog["model_tiers"] == ["assistant", "extraction", "generation"]
    embedding_ids = {p["id"] for p in catalog["embedding_providers"]}
    assert {"local", "disabled"} <= embedding_ids


def test_embedding_change_with_embeddings_off_needs_no_reindex(
    client: TestClient,
) -> None:
    # The fixture app runs with embeddings disabled: changing which model a
    # (currently unused) provider would use changes no vectors.
    response = client.put(
        "/api/settings",
        json={"values": {"openai_embedding_model": "text-embedding-3-large"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reindex_required"] is False
    assert body["reindex_started"] is False
    assert body["settings"]["embeddings_enabled"] is False


def test_tracing_change_is_reported_as_needing_a_restart(client: TestClient) -> None:
    response = client.put(
        "/api/settings", json={"values": {"langsmith_project": "campaign-traces"}}
    )

    assert response.json()["restart_required_fields"] == ["langsmith_project"]


def test_reindex_is_refused_while_embeddings_are_disabled(client: TestClient) -> None:
    response = client.post("/api/settings/reindex")

    assert response.status_code == 409
    assert response.json()["code"] == "configuration"


def test_reindex_status_starts_idle(client: TestClient) -> None:
    assert client.get("/api/settings/reindex").json()["state"] == "idle"


def test_embedding_provider_without_its_key_is_refused_atomically(
    client: TestClient, app: FastAPI
) -> None:
    # Selecting a provider whose key is missing must fail before anything is
    # stored — otherwise the app would be left with no vector layer at all.
    response = client.put(
        "/api/settings", json={"values": {"embedding_provider": "openai"}}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "configuration"
    assert app.state.settings_provider.current.embedding_provider == "disabled"
    assert client.get("/api/settings").json()["fields"]["embedding_provider"][
        "source"
    ] in ("env", "default")
