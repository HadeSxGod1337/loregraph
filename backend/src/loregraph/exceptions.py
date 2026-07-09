class CampaignError(Exception):
    """Base class for all domain errors raised by loregraph."""


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
