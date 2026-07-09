from fastapi import APIRouter, UploadFile

from loregraph.api.deps import AttachmentStoreDep, EntityStoreDep
from loregraph.exceptions import EntityNotFoundError
from loregraph.schemas.attachment import AttachmentOut

router = APIRouter(tags=["attachments"])


@router.post(
    "/entities/{entity_id}/attachments",
    response_model=AttachmentOut,
    status_code=201,
)
async def upload_attachment(
    entity_id: str,
    file: UploadFile,
    attachment_store: AttachmentStoreDep,
    entity_store: EntityStoreDep,
) -> AttachmentOut:
    if not await entity_store.exists(entity_id):
        raise EntityNotFoundError(entity_id)
    content = await file.read()
    return await attachment_store.create(
        entity_id=entity_id,
        original_filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )


@router.get("/entities/{entity_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    entity_id: str, store: AttachmentStoreDep
) -> list[AttachmentOut]:
    return await store.list_for_entity(entity_id)


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: str, store: AttachmentStoreDep) -> None:
    await store.delete(attachment_id)
