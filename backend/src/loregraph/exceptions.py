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
