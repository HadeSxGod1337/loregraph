from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from loregraph.connectors.context import ConnectorContext
from loregraph.exceptions import ConnectorConfigInvalidError, UnknownConnectorTypeError
from loregraph.schemas.connection import SECRET_MASK_PREFIX, ConnectorTypeOut


@dataclass(frozen=True)
class ConnectorDescriptor:
    """One registered connector type: how to validate its config and build an
    instance. `capabilities` is declared statically so GET /api/connectors
    can list what a type supports without instantiating anything."""

    connector_type: str
    config_model: type[BaseModel]
    factory: Callable[[BaseModel, ConnectorContext], object]
    capabilities: frozenset[str]


class ConnectorRegistry:
    """OCP seam for external tools: a new connector (Notion, Miro…) is a new
    module plus one register() call in main.py — no changes anywhere else."""

    def __init__(self) -> None:
        self._descriptors: dict[str, ConnectorDescriptor] = {}

    def register(self, descriptor: ConnectorDescriptor) -> None:
        self._descriptors[descriptor.connector_type] = descriptor

    def get(self, connector_type: str) -> ConnectorDescriptor:
        descriptor = self._descriptors.get(connector_type)
        if descriptor is None:
            raise UnknownConnectorTypeError(connector_type)
        return descriptor

    def list_types(self) -> list[ConnectorTypeOut]:
        return [
            ConnectorTypeOut(
                connector_type=d.connector_type,
                capabilities=sorted(d.capabilities),
            )
            for d in self._descriptors.values()
        ]

    def validate_config(self, connector_type: str, config: dict[str, Any]) -> BaseModel:
        descriptor = self.get(connector_type)
        try:
            return descriptor.config_model.model_validate(config)
        except ValidationError as e:
            # Field names only — never echo values, they may contain secrets.
            fields = ", ".join(
                ".".join(str(loc) for loc in err["loc"]) or "<root>"
                for err in e.errors()
            )
            raise ConnectorConfigInvalidError(
                connector_type, f"invalid fields: {fields}"
            ) from e

    def create(
        self,
        connector_type: str,
        config: dict[str, Any],
        context: ConnectorContext,
    ) -> object:
        descriptor = self.get(connector_type)
        validated = self.validate_config(connector_type, config)
        return descriptor.factory(validated, context)


def secret_field_names(config_model: type[BaseModel]) -> frozenset[str]:
    names: set[str] = set()
    for name, field in config_model.model_fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and extra.get("secret") is True:
            names.add(name)
    return frozenset(names)


def mask_secrets(
    config_model: type[BaseModel], config: dict[str, Any]
) -> dict[str, Any]:
    """Replace secret values with a mask before the config leaves the API."""
    masked = dict(config)
    for name in secret_field_names(config_model):
        value = masked.get(name)
        if isinstance(value, str) and value:
            masked[name] = SECRET_MASK_PREFIX + value[-4:]
    return masked


def merge_masked_secrets(
    config_model: type[BaseModel],
    new_config: dict[str, Any],
    stored_config: dict[str, Any],
) -> dict[str, Any]:
    """An update that echoes the mask back means 'keep the stored secret'."""
    merged = dict(new_config)
    for name in secret_field_names(config_model):
        value = merged.get(name)
        if isinstance(value, str) and value.startswith(SECRET_MASK_PREFIX):
            stored = stored_config.get(name)
            if stored is not None:
                merged[name] = stored
    return merged
