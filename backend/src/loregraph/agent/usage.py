from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.usage import UsageEvent
from loregraph.storage.protocols import UsageStore


async def record_usage(
    store: UsageStore | None,
    *,
    project_id: str,
    thread_id: str,
    node: str,
    model: str,
    usage: LLMCallUsage,
) -> None:
    """Persist one LLM call's usage for observability (per-node/model/project
    breakdown, incl. cache tokens).

    Separate from the budget accounting that each node keeps in AgentState:
    the budget needs a running total in state, this is the durable per-call
    trail. A no-op when the store is absent (embeddings-style degrade / tests)."""
    if store is None:
        return
    await store.record(
        UsageEvent(
            project_id=project_id,
            thread_id=thread_id,
            node=node,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
        )
    )
