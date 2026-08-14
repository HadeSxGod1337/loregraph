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
from collections.abc import Callable, Iterable

from loregraph.config import Settings
from loregraph.llm.embeddings import EmbeddingProvider, get_embedding_provider
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.vectorstore.protocols import IndexHealth, VectorStore

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
        self._index_stale: bool = False
        self._apply(settings, build_embedder(settings))

    def build_embedder(self, settings: Settings) -> EmbeddingProvider | None:
        """Construct an embedder for candidate settings without installing it.

        The settings router uses this to find out whether a configuration is
        even buildable before it persists anything — and then hands the result
        back to `rebuild`, so the object is built exactly once.
        """
        return self._build_embedder(settings)

    async def detect_stale_index(self, project_ids: Iterable[str]) -> bool:
        """Ask the store whether anything it persisted is now unreadable.

        Called once at startup, because the condition is invisible otherwise:
        the embedding model id folds in the fastembed package version
        (llm/embeddings.py), so an ordinary dependency upgrade silently
        invalidates every collection — and the repair path only ever ran when
        the user changed a setting. Left undetected, the first search after an
        upgrade quietly returns nothing and the world looks empty.
        """
        store = self._store
        if not isinstance(store, IndexHealth):
            return False

        def _any_stale() -> bool:
            return any(store.collection_is_stale(pid) for pid in project_ids)

        self._index_stale = await asyncio.to_thread(_any_stale)
        if self._index_stale:
            logger.warning(
                "Stored vectors were built by a different configuration — a "
                "reindex is required before search will find anything."
            )
        return self._index_stale

    @property
    def index_stale(self) -> bool:
        """True when a reindex is needed and has not run yet."""
        return self._index_stale

    def mark_index_fresh(self) -> None:
        """Called once a reindex has rebuilt the collections."""
        self._index_stale = False

    def _apply(self, settings: Settings, embedder: EmbeddingProvider | None) -> None:
        store = self._build_vector_store(settings, embedder)
        self._embedder = embedder
        self._store = store
        # A rebuild's own staleness is already reported by `rebuild`'s return
        # value, which the settings router turns into an automatic reindex —
        # this flag only carries the condition nobody asked about.
        self._index_stale = False
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
