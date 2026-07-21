"""Source abstraction for the bulk-import pipeline.

The registry→extract→merge→review→commit pipeline (agent/import_graph.py) is
generic over text windows; only the very first node needs to know WHERE the
text comes from. This resolver is that seam: it turns either an uploaded
knowledge-base file OR a connection whose connector implements IngestSource
(migrate an external project into the graph) into plain-text documents. The
rest of the pipeline is unchanged and source-agnostic.

Kept DIP-clean: this module depends only on the IngestSource abstraction
(connectors/protocols.py); the concrete connection→IngestSource resolution
(connector registry, context) is injected as a callable from the
composition layer (api/deps.py), never imported here.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loregraph.connectors.protocols import IngestSource
from loregraph.services.document_ingest import extract_text
from loregraph.storage.protocols import KnowledgeSourceStore

# (project_id, connection_id) -> a connector that yields text documents.
# Injected from api/deps.py so the agent layer never imports the connector
# registry/implementations.
ConnectionIngestFactory = Callable[[str, str], Awaitable[IngestSource]]


@dataclass(frozen=True)
class SourceDocument:
    """One document to window and extract from. `ref` is provenance (KB
    source id, or an external record id); `title` is human-facing."""

    ref: str
    title: str
    text: str


class ImportSourceResolver:
    def __init__(
        self,
        knowledge_source_store: KnowledgeSourceStore,
        connection_ingest_factory: ConnectionIngestFactory,
    ) -> None:
        self._knowledge = knowledge_source_store
        self._connection_ingest = connection_ingest_factory

    async def load_documents(
        self, source_kind: str, source_id: str, project_id: str
    ) -> list[SourceDocument]:
        if source_kind == "connection":
            return await self._load_connection(project_id, source_id)
        return await self._load_knowledge(source_id)

    async def _load_knowledge(self, source_id: str) -> list[SourceDocument]:
        source = await self._knowledge.get(source_id)
        content = await self._knowledge.read_content(source_id)
        text = await asyncio.to_thread(
            extract_text, content, source.content_type, source.original_filename
        )
        return [
            SourceDocument(
                ref=source_id, title=source.original_filename, text=text
            )
        ]

    async def _load_connection(
        self, project_id: str, connection_id: str
    ) -> list[SourceDocument]:
        ingest = await self._connection_ingest(project_id, connection_id)
        documents = await ingest.ingest_documents()
        return [
            SourceDocument(ref=doc.external_id, title=doc.title, text=doc.text)
            for doc in documents
            if doc.text.strip()
        ]
