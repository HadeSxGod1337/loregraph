from typing import cast

from pydantic import BaseModel

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.foundry.connector import FoundryConfig, FoundryConnector
from loregraph.connectors.longstoryshort.connector import LssConfig, LssConnector
from loregraph.connectors.mcp.connector import GenericMcpConnector, McpConfig
from loregraph.connectors.obsidian.connector import ObsidianConfig, ObsidianConnector
from loregraph.connectors.protocols import (
    CAPABILITY_EXPORT,
    CAPABILITY_IMPORT,
    CAPABILITY_INGEST,
    CAPABILITY_LIVE,
    CAPABILITY_MCP_TOOLS,
)
from loregraph.connectors.registry import ConnectorDescriptor, ConnectorRegistry
from loregraph.plugins.discovery import load_plugin_hooks


def _obsidian_factory(config: BaseModel, context: ConnectorContext) -> object:
    return ObsidianConnector(cast(ObsidianConfig, config), context)


def _foundry_factory(config: BaseModel, context: ConnectorContext) -> object:
    return FoundryConnector(cast(FoundryConfig, config), context)


def _lss_factory(config: BaseModel, context: ConnectorContext) -> object:
    return LssConnector(cast(LssConfig, config), context)


def _mcp_factory(config: BaseModel, context: ConnectorContext) -> object:
    return GenericMcpConnector(cast(McpConfig, config), context)


def build_default_registry() -> ConnectorRegistry:
    """Composition point for connector types. A new connector = a new module
    under loregraph.connectors.* plus one register() call here."""
    registry = ConnectorRegistry()
    registry.register(
        ConnectorDescriptor(
            connector_type="obsidian",
            config_model=ObsidianConfig,
            factory=_obsidian_factory,
            capabilities=frozenset(
                {CAPABILITY_EXPORT, CAPABILITY_IMPORT, CAPABILITY_INGEST}
            ),
        )
    )
    registry.register(
        ConnectorDescriptor(
            connector_type="foundry",
            config_model=FoundryConfig,
            factory=_foundry_factory,
            capabilities=frozenset(
                {
                    CAPABILITY_EXPORT,
                    CAPABILITY_IMPORT,
                    CAPABILITY_LIVE,
                    CAPABILITY_INGEST,
                }
            ),
        )
    )
    registry.register(
        ConnectorDescriptor(
            connector_type="longstoryshort",
            config_model=LssConfig,
            factory=_lss_factory,
            capabilities=frozenset({CAPABILITY_IMPORT, CAPABILITY_LIVE}),
        )
    )
    registry.register(
        ConnectorDescriptor(
            connector_type="mcp",
            config_model=McpConfig,
            factory=_mcp_factory,
            capabilities=frozenset({CAPABILITY_MCP_TOOLS}),
        )
    )
    # Optional installed plugin package (e.g. a private extension) registers
    # additional connector types here — absence of a plugin is not an error.
    for register_plugin in load_plugin_hooks("loregraph.plugins.connectors"):
        register_plugin(registry)
    return registry
