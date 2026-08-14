"""On-demand retrieval-quality eval — NOT part of the regular pytest/CI run
(CLAUDE.md, "Тестирование промптов": eval-наборы run by request/nightly).

Drives the *real* embedding provider (local FastEmbed by default: offline,
no API key, same model production uses per config.Settings.embedding_model)
and the real ChromaVectorStore against the golden dataset in
golden_retrieval.py, then reports recall@k, nDCG@k (relevance scoring) and
MRR — actual retrieval quality, not a mocked stand-in.

Usage (from backend/):
    uv run python -m evals.run_retrieval_eval
    uv run python -m evals.run_retrieval_eval --model BAAI/bge-small-en-v1.5
"""

import argparse
import asyncio
import shutil
import statistics
import tempfile
from pathlib import Path

from evals.golden_retrieval import GOLDEN_QUERIES, GoldenQuery
from evals.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from loregraph.config import Settings
from loregraph.llm.embeddings import FastEmbedProvider
from loregraph.schemas.entity import EntityOut
from loregraph.services.lore_search import search_lore
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

# Mirrors config.Settings.embedding_model's default — the eval should
# measure what production actually ships with unless told otherwise.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_METRICS = ("recall@k", "ndcg@k", "mrr")


class _CaseEntityStore:
    """The case's own entities, as the EntityStore that search_lore reads.

    The eval drives the *assistant's* retrieval path, not just the vector
    store's: half of what search_lore does (the lexical contour, see
    services/lore_search.py) lives above the store, and a number that skips it
    would not describe what a game master experiences.
    """

    def __init__(self, entities: list[EntityOut]) -> None:
        self._entities = entities

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        return [
            entity
            for entity in self._entities
            if entity.project_id == project_id
            and (entity_type is None or entity.type == entity_type)
        ]


async def _run_case(
    index: VectorIndex, case: GoldenQuery, *, vector_only: bool
) -> dict[str, float]:
    for entity in case.entities:
        await index.index_entity(entity)
    if vector_only:
        chunks = await index.query(case.project_id, case.query, k=case.k)
        retrieved_ids = [chunk.entity_id for chunk in chunks]
    else:
        result = await search_lore(
            vector_index=index,
            entity_store=_CaseEntityStore(case.entities),  # type: ignore[arg-type]
            project_id=case.project_id,
            query=case.query,
            limit=case.k,
        )
        retrieved_ids = [entity.id for entity in result.entities]
    relevant_ids = {
        entity_id for entity_id, grade in case.relevance.items() if grade > 0
    }
    return {
        "recall@k": recall_at_k(retrieved_ids, relevant_ids, case.k),
        "ndcg@k": ndcg_at_k(retrieved_ids, case.relevance, case.k),
        "mrr": reciprocal_rank(retrieved_ids, relevant_ids),
    }


async def run(
    model_name: str, *, vector_only: bool = False
) -> list[tuple[str, dict[str, float]]]:
    # Plain mkdtemp + best-effort rmtree instead of TemporaryDirectory:
    # Chroma's PersistentClient keeps its sqlite/hnsw files memory-mapped for
    # the process lifetime, so on Windows a strict on-exit rmtree (as
    # TemporaryDirectory does) raises PermissionError and discards the
    # report that was already computed.
    tmp = Path(tempfile.mkdtemp(prefix="loregraph-retrieval-eval-"))
    try:
        # The model cache stays OUTSIDE the temp dir that gets torn down: an
        # eval run must not re-download 240 MB every time it is invoked. It
        # uses the app's own location, so a normal install already has it.
        store = ChromaVectorStore(
            tmp / "chroma", FastEmbedProvider(model_name, Settings().models_dir)
        )
        index = VectorIndex(store)
        return [
            (case.case_id, await _run_case(index, case, vector_only=vector_only))
            for case in GOLDEN_QUERIES
        ]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _print_report(model_name: str, rows: list[tuple[str, dict[str, float]]]) -> None:
    width = max(len(case_id) for case_id, _ in rows)
    print(f"embedding_model = {model_name}\n")
    header = f"{'case':<{width}}  " + "  ".join(f"{m:>8}" for m in _METRICS)
    print(header)
    for case_id, scores in rows:
        line = f"{case_id:<{width}}  " + "  ".join(
            f"{scores[m]:>8.2f}" for m in _METRICS
        )
        print(line)
    print()
    for metric in _METRICS:
        mean = statistics.mean(scores[metric] for _, scores in rows)
        print(f"mean {metric} = {mean:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--vector-only",
        action="store_true",
        help="Measure the vector store alone, skipping the lexical contour "
        "search_lore adds on top — useful for attributing a change to one "
        "layer or the other.",
    )
    args = parser.parse_args()
    rows = asyncio.run(run(args.model, vector_only=args.vector_only))
    _print_report(f"{args.model}{' (vector only)' if args.vector_only else ''}", rows)


if __name__ == "__main__":
    main()
