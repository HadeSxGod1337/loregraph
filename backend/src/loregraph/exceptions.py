import re


def error_code(exc: Exception) -> str:
    """Stable machine-readable code derived from the exception class name,
    e.g. ProjectNotFoundError -> "project_not_found"."""
    name = type(exc).__name__.removesuffix("Error")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class CampaignError(Exception):
    """Base class for all domain errors raised by loregraph."""


class ProjectNotFoundError(CampaignError):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project not found: {project_id}")
        self.project_id = project_id


class CrossProjectEdgeError(CampaignError):
    def __init__(self, source_entity_id: str, target_entity_id: str) -> None:
        super().__init__(
            f"Edge endpoints belong to different projects: "
            f"{source_entity_id}, {target_entity_id}"
        )
        self.source_entity_id = source_entity_id
        self.target_entity_id = target_entity_id


class EntityNotFoundError(CampaignError):
    def __init__(self, entity_id: str) -> None:
        super().__init__(f"Entity not found: {entity_id}")
        self.entity_id = entity_id


class EdgeNotFoundError(CampaignError):
    def __init__(self, edge_id: str) -> None:
        super().__init__(f"Edge not found: {edge_id}")
        self.edge_id = edge_id


class AttachmentNotFoundError(CampaignError):
    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"Attachment not found: {attachment_id}")
        self.attachment_id = attachment_id


class InvalidEdgeReferenceError(CampaignError):
    def __init__(self, entity_id: str) -> None:
        super().__init__(f"Edge references a nonexistent entity: {entity_id}")
        self.entity_id = entity_id


class InvalidIconReferenceError(CampaignError):
    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"Attachment does not belong to this entity: {attachment_id}")
        self.attachment_id = attachment_id


class UnsupportedExportFormatError(CampaignError):
    def __init__(self, format_version: int) -> None:
        super().__init__(f"Unsupported project export format_version: {format_version}")
        self.format_version = format_version


class ConfigurationError(CampaignError):
    """Agent layer is misconfigured (e.g. provider selected without an API key).

    Deliberately never includes secret values in the message."""


class RetrievalError(CampaignError):
    """Vector or graph retrieval failed; generation must not proceed ungrounded."""


class GenerationError(CampaignError):
    """LLM did not produce a valid result within the allowed retry attempts."""


class AgentSessionNotFoundError(CampaignError):
    def __init__(self, thread_id: str) -> None:
        super().__init__(f"Agent session not found: {thread_id}")
        self.thread_id = thread_id


class DuplicateEntityError(CampaignError):
    def __init__(self, title: str, existing_entity_id: str) -> None:
        super().__init__(
            f"Entity duplicates an existing one: {title!r} "
            f"(existing id: {existing_entity_id})"
        )
        self.title = title
        self.existing_entity_id = existing_entity_id


class KnowledgeSourceNotFoundError(CampaignError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"Knowledge source not found: {source_id}")
        self.source_id = source_id


class UnsupportedDocumentTypeError(CampaignError):
    def __init__(self, filename: str) -> None:
        super().__init__(f"Unsupported document type for knowledge base: {filename}")
        self.filename = filename


class DocumentParsingError(CampaignError):
    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(f"Failed to parse document {filename!r}: {reason}")
        self.filename = filename
        self.reason = reason


class UnsupportedAttachmentTypeError(CampaignError):
    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(f"Unsupported chat attachment {filename!r}: {reason}")
        self.filename = filename
        self.reason = reason


class ChatAttachmentLimitExceededError(CampaignError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Chat attachment limit exceeded: {reason}")
        self.reason = reason


class AwaitingReviewConflictError(CampaignError):
    """Raised when a chat message arrives while a draft is paused at review."""

    def __init__(self) -> None:
        super().__init__(
            "A draft is awaiting review — approve, reject or request changes "
            "before sending new messages."
        )


class ImportJobNotFoundError(CampaignError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Import job not found: {job_id}")
        self.job_id = job_id


class ImportJobNotIdleError(CampaignError):
    """Raised when a new import job is requested for a project that already
    has one in progress — one active bulk import per project at a time."""

    def __init__(self, job_id: str, status: str) -> None:
        super().__init__(
            f"An import job is already in progress for this project "
            f"({job_id}, status: {status})."
        )
        self.job_id = job_id
        self.status = status


class ImportJobNotAwaitingReviewError(CampaignError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Import job is not awaiting review (status: {status}).")
        self.status = status


class KnowledgeSourceNotReadyError(CampaignError):
    def __init__(self, source_id: str, status: str) -> None:
        super().__init__(
            f"Knowledge source {source_id} is not ready for import (status: {status})."
        )
        self.source_id = source_id
        self.status = status


class UnknownSkillError(CampaignError):
    """Raised when a direct skill run (see agent/skills/registry.py) names a
    skill that either doesn't exist or has no entry_node (a "read" skill —
    those only ever run inline inside a chat turn's tool-call loop, never as
    a standalone run)."""

    def __init__(self, skill_name: str) -> None:
        super().__init__(f"Unknown or non-runnable skill: {skill_name}")
        self.skill_name = skill_name


class SkillInputInvalidError(CampaignError):
    def __init__(self, skill_name: str, reason: str) -> None:
        super().__init__(f"Invalid input for skill {skill_name!r}: {reason}")
        self.skill_name = skill_name
        self.reason = reason


class NotAwaitingReviewError(CampaignError):
    """Raised when a review decision arrives for a session that isn't paused
    at the human_review gate."""

    def __init__(self, status: str) -> None:
        super().__init__(f"Session is not awaiting review (status: {status}).")
        self.status = status


class ConnectorError(CampaignError):
    """Base class for external-tool connector errors (Obsidian, Foundry, …)."""


class ConnectionNotFoundError(ConnectorError):
    def __init__(self, connection_id: str) -> None:
        super().__init__(f"Connection not found: {connection_id}")
        self.connection_id = connection_id


class UnknownConnectorTypeError(ConnectorError):
    def __init__(self, connector_type: str) -> None:
        super().__init__(f"Unknown connector type: {connector_type}")
        self.connector_type = connector_type


class ConnectorConfigInvalidError(ConnectorError):
    """Connection config failed validation against the connector's config
    model. Deliberately never includes config values in the message — they
    may contain secrets."""

    def __init__(self, connector_type: str, reason: str) -> None:
        super().__init__(f"Invalid {connector_type} connection config: {reason}")
        self.connector_type = connector_type
        self.reason = reason


class UnsupportedConnectorCapabilityError(ConnectorError):
    def __init__(self, connector_type: str, capability: str) -> None:
        super().__init__(
            f"Connector {connector_type!r} does not support {capability!r}"
        )
        self.connector_type = connector_type
        self.capability = capability


class ConnectorUnavailableError(ConnectorError):
    """The external tool is unreachable (Foundry off, vault path missing,
    LSS not responding). Callers on the agent path must degrade, not fail."""

    def __init__(self, connection_name: str, reason: str) -> None:
        super().__init__(f"Connection {connection_name!r} unavailable: {reason}")
        self.connection_name = connection_name
        self.reason = reason


class ExternalDataParseError(ConnectorError):
    """External data didn't match the expected shape (LSS JSON, frontmatter…)."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"Failed to parse external data from {source}: {reason}")
        self.source = source
        self.reason = reason


class ExportConflictError(ConnectorError):
    def __init__(self, target: str, reason: str) -> None:
        super().__init__(f"Export conflict at {target!r}: {reason}")
        self.target = target
        self.reason = reason
