import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from loregraph.api.deps import (
    KnowledgeIndexDep,
    KnowledgeSourceStoreDep,
    ProjectStoreDep,
)
from loregraph.schemas.knowledge import KnowledgeSourceOut
from loregraph.services.knowledge_ingest import ingest_source

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])

# Local self-hosted tool, no upload proxy in front of it — cap file size here
# so one oversized upload can't stall ingestion or blow up the Chroma index.
MAX_KNOWLEDGE_FILE_BYTES = 50 * 1024 * 1024


@router.post(
    "/projects/{project_id}/knowledge",
    response_model=KnowledgeSourceOut,
    status_code=201,
)
async def upload_knowledge_source(
    project_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    project_store: ProjectStoreDep,
    source_store: KnowledgeSourceStoreDep,
    knowledge_index: KnowledgeIndexDep,
) -> KnowledgeSourceOut:
    await project_store.get(project_id)  # 404 for unknown projects, not an
    # unhandled FK-constraint IntegrityError from the insert below.
    content = await file.read()
    if len(content) > MAX_KNOWLEDGE_FILE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File exceeds the {MAX_KNOWLEDGE_FILE_BYTES // (1024 * 1024)}MB "
                "limit for knowledge base uploads."
            ),
        )
    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    source = await source_store.create(
        project_id=project_id,
        original_filename=filename,
        content_type=content_type,
        content=content,
    )
    # Response goes out with status="pending" immediately; ingestion runs
    # after it (see services/knowledge_ingest.py) — the UI polls the list
    # endpoint for status instead of blocking the upload on parsing/indexing.
    background_tasks.add_task(
        ingest_source,
        source.id,
        project_id,
        content,
        content_type,
        filename,
        source_store=source_store,
        knowledge_index=knowledge_index,
    )
    return source


@router.get("/projects/{project_id}/knowledge", response_model=list[KnowledgeSourceOut])
async def list_knowledge_sources(
    project_id: str, store: KnowledgeSourceStoreDep
) -> list[KnowledgeSourceOut]:
    return await store.list_for_project(project_id)


@router.delete("/knowledge/{source_id}", status_code=204)
async def delete_knowledge_source(
    source_id: str,
    store: KnowledgeSourceStoreDep,
    knowledge_index: KnowledgeIndexDep,
) -> None:
    source = await store.get(source_id)
    await store.delete(source_id)
    if knowledge_index is not None:
        try:
            await knowledge_index.remove_source(
                source.project_id, source_id, source.chunk_count
            )
        except Exception:
            logger.warning(
                "Vector de-indexing failed for knowledge source %s; "
                "orphaned chunks will remain until the project is reindexed.",
                source_id,
                exc_info=True,
            )
