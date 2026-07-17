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
from loregraph.llm.embeddings import FastEmbedProvider
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

# Mirrors config.Settings.embedding_model's default — the eval should
# measure what production actually ships with unless told otherwise.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_METRICS = ("recall@k", "ndcg@k", "mrr")


async def _run_case(index: VectorIndex, case: GoldenQuery) -> dict[str, float]:
    for entity in case.entities:
        await index.index_entity(entity)
    results = await index.query(case.project_id, case.query, k=case.k)
    retrieved_ids = [chunk.entity_id for chunk in results]
    relevant_ids = {
        entity_id for entity_id, grade in case.relevance.items() if grade > 0
    }
    return {
        "recall@k": recall_at_k(retrieved_ids, relevant_ids, case.k),
        "ndcg@k": ndcg_at_k(retrieved_ids, case.relevance, case.k),
        "mrr": reciprocal_rank(retrieved_ids, relevant_ids),
    }


async def run(model_name: str) -> list[tuple[str, dict[str, float]]]:
    # Plain mkdtemp + best-effort rmtree instead of TemporaryDirectory:
    # Chroma's PersistentClient keeps its sqlite/hnsw files memory-mapped for
    # the process lifetime, so on Windows a strict on-exit rmtree (as
    # TemporaryDirectory does) raises PermissionError and discards the
    # report that was already computed.
    tmp = Path(tempfile.mkdtemp(prefix="loregraph-retrieval-eval-"))
    try:
        store = ChromaVectorStore(tmp / "chroma", FastEmbedProvider(model_name))
        index = VectorIndex(store)
        return [
            (case.case_id, await _run_case(index, case)) for case in GOLDEN_QUERIES
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
    args = parser.parse_args()
    rows = asyncio.run(run(args.model))
    _print_report(args.model, rows)


if __name__ == "__main__":
    main()
