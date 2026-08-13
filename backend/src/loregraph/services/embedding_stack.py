"""The embedding half of the app's configuration, as a rebuildable unit.

Chat models are built per request from the current settings, so changing one
takes effect on the next call by itself. Embeddings can't work that way: the
provider, the Chroma client and both indexes are long-lived objects created
once at startup. This holder owns that little object graph so a settings
change can swap it out at runtime, and everything downstream keeps reading
`vector_index` / `knowledge_index` through it instead of capturing them.

Switching to a model whose `model_id` differs invalidates every stored vector
(embeddings from two models are not comparable — see
storage/vectorstore/chroma_store.py), which is why `rebuild` reports whether
the id changed: that is exactly the condition for requiring a reindex.
"""

import asyncio
import logging
from collections.abc import Callable

from loregraph.config import Settings
from loregraph.llm.embeddings import EmbeddingProvider, get_embedding_provider
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.vectorstore.protocols import VectorStore

logger = logging.getLogger(__name__)

type VectorStoreBuilder = Callable[
    [Settings, EmbeddingProvider | None], VectorStore | None
]
type EmbedderBuilder = Callable[[Settings], EmbeddingProvider | None]


class EmbeddingStack:
    """Embedder + vector store + the two indexes over it, swappable at runtime.

    `knowledge_index` deliberately shares the *same* VectorStore instance as
    `vector_index` (different collection namespace, see
    services/knowledge_index.py) — not a second Chroma client on the same
    directory.
    """

    def __init__(
        self,
        settings: Settings,
        build_vector_store: VectorStoreBuilder,
        build_embedder: EmbedderBuilder = get_embedding_provider,
    ) -> None:
        self._build_vector_store = build_vector_store
        self._build_embedder = build_embedder
        self._lock = asyncio.Lock()
        self._apply(settings, build_embedder(settings))

    def build_embedder(self, settings: Settings) -> EmbeddingProvider | None:
        """Construct an embedder for candidate settings without installing it.

        The settings router uses this to find out whether a configuration is
        even buildable before it persists anything — and then hands the result
        back to `rebuild`, so the object is built exactly once.
        """
        return self._build_embedder(settings)

    def _apply(self, settings: Settings, embedder: EmbeddingProvider | None) -> None:
        store = self._build_vector_store(settings, embedder)
        self._embedder = embedder
        self._store = store
        # None all the way down when embeddings are off: every consumer of
        # these already treats None as "vector layer unavailable, degrade".
        self._vector_index = VectorIndex(store) if store is not None else None
        self._knowledge_index = KnowledgeIndex(store) if store is not None else None

    @property
    def embedder(self) -> EmbeddingProvider | None:
        return self._embedder

    @property
    def model_id(self) -> str | None:
        return self._embedder.model_id if self._embedder is not None else None

    @property
    def vector_index(self) -> VectorIndex | None:
        return self._vector_index

    @property
    def knowledge_index(self) -> KnowledgeIndex | None:
        return self._knowledge_index

    async def rebuild(
        self, settings: Settings, embedder: EmbeddingProvider | None = None
    ) -> bool:
        """Rebuild from `settings`; returns True when the embedding model id
        changed, i.e. when the stored vectors are now stale.

        `embedder` may be passed in when the caller already built one to
        validate the new settings — building it twice would be wasteful and,
        for a local model, would mean two loads of the same file.
        """
        async with self._lock:
            previous_model_id = self.model_id
            self._apply(
                settings,
                embedder if embedder is not None else self._build_embedder(settings),
            )
            changed = previous_model_id != self.model_id
            logger.info(
                "Embedding stack rebuilt: %s -> %s%s",
                previous_model_id,
                self.model_id,
                " (reindex required)" if changed else "",
            )
            return changed

    async def warmup(self) -> None:
        """Load (and on first run download) the embedding model, so the first
        agent request doesn't stall on it. Failure is logged, never fatal —
        the model is retried lazily on first real use."""
        embedder = self._embedder
        if embedder is None:
            return
        try:
            logger.info(
                "Warming up embedding model %s (first run downloads it once)…",
                embedder.model_id,
            )
            await embedder.embed(["warmup"])
            logger.info("Embedding model %s is ready", embedder.model_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Embedding model warmup failed — it will be retried lazily on "
                "first use (vector indexing degrades to a logged warning).",
                exc_info=True,
            )
