"""The creative, non-mutating pipeline: brainstorm ideas and answer in chat.

This is the third assistant mode alongside "answer a fact" (read tools) and
"change the world" (propose_changes). A request for POSSIBILITIES — "придумай
врага для Ордена", "накидай пять идей" — routes here, NOT into the write
pipeline. The distinction is the whole point of the feature: suggesting an idea
must never make it canon. This node has no write access, no human_review, and
no edge to commit; its only outputs are a tool acknowledgement and a normal
assistant message carrying the ideas. Turning an idea into world content is a
separate propose_changes the game master asks for afterwards.

Ideas are generated on the creative (generation) tier through the injected
StructuredGenerator, not the cheap assistant model — brainstorming is exactly
the task that tier exists for. Existing canon is pulled in first, so the ideas
build on and play against what is really there (see prompts/brainstorm.*).
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from loregraph.agent.events import event_message
from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import BrainstormResult
from loregraph.schemas.entity import EntityOut
from loregraph.services.lore_format import relationship_line
from loregraph.services.lore_search import search_lore
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import (
    EdgeStore,
    EntityStore,
    ProjectStore,
    UsageStore,
)

logger = logging.getLogger(__name__)

NODE = "brainstorm"

# Related canon pulled in as background inspiration for the topic — enough to
# spark connections, not so much the prompt drowns in unrelated lore.
BRAINSTORM_SEARCH_K = 6
# Relationships per target shown to the creative tier. A hub entity's whole
# neighborhood would swamp the prompt; this is plenty to see who it fights,
# serves and stands near — the leverage an invented enemy should press on.
BRAINSTORM_TARGET_EDGES = 30
LORE_TEXT_LIMIT = 600  # chars per background entity — context, not a dump
DEFAULT_IDEA_COUNT_HINT = "3–5"

# Reuse the assistant's budget-exhausted event code so the frontend localizes
# it identically; the English text is only the model's own history fallback.
BUDGET_EXHAUSTED_TEXT = (
    "Token budget for this conversation is exhausted — start a new session to continue."
)

CHAT_ACK = "Brainstorm complete — ideas delivered in the reply below."


async def brainstorm(
    state: AgentState,
    *,
    creative: StructuredGenerator,
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_store: ProjectStore,
    token_budget: int,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """Generate creative options for the game master and answer in chat.

    Reached from a brainstorm_lore chat tool call (route_after_assistant) or a
    direct skill_kickoff. Deliberately terminal: the graph routes this node
    straight to END, so no ideas can leak into canon without a separate,
    explicit propose_changes."""
    topic, target_ids, count, tool_messages = _read_trigger(state)
    reset: dict[str, Any] = {"skill_kickoff": None}

    if state.over_budget(token_budget):
        return {
            "messages": [
                *tool_messages,
                event_message(BUDGET_EXHAUSTED_TEXT, "budget_exhausted_reply"),
            ],
            **reset,
        }

    existing_lore, targets_block = await _gather_material(
        topic,
        target_ids,
        vector_index=vector_index,
        entity_store=entity_store,
        edge_store=edge_store,
        project_id=state.project_id,
    )
    project = await project_store.get(state.project_id)
    result = await creative.generate(
        BrainstormResult,
        system=render(
            "brainstorm.system.md",
            project_instructions_block=project_instructions_block(
                project.agent_instructions
            ),
        ),
        cached_prefix=render(
            "brainstorm.user.md",
            existing_lore=existing_lore,
            targets=targets_block
            or "(none — this is a blank-slate prompt with no named entity)",
            topic=topic,
            count=str(count) if count else DEFAULT_IDEA_COUNT_HINT,
        ),
        user="",
    )
    await record_usage(
        usage_store,
        project_id=state.project_id,
        thread_id=state.thread_id,
        node=NODE,
        model=model_name,
        usage=result.usage,
    )
    return {
        "messages": [*tool_messages, _render_ideas(result.value)],
        "input_tokens": state.input_tokens + result.usage.input_tokens,
        "output_tokens": state.output_tokens + result.usage.output_tokens,
        **reset,
    }


def _read_trigger(
    state: AgentState,
) -> tuple[str, list[str], int | None, list[ToolMessage]]:
    """Topic, target ids, requested count, and the ToolMessages that answer the
    triggering tool call(s). A direct skill_kickoff has no tool call to answer,
    so its message list is empty."""
    if state.skill_kickoff is not None:
        data = state.skill_kickoff.input
        return (
            str(data.get("topic", "")),
            _str_list(data.get("target_entity_ids", [])),
            _optional_count(data.get("count")),
            [],
        )
    last = state.messages[-1]
    assert isinstance(last, AIMessage)
    call = next(c for c in last.tool_calls if c["name"] == "brainstorm_lore")
    return (
        str(call["args"].get("topic", "")),
        _str_list(call["args"].get("target_entity_ids", [])),
        _optional_count(call["args"].get("count")),
        _brainstorm_tool_results(last),
    )


def _brainstorm_tool_results(message: AIMessage) -> list[ToolMessage]:
    """One ToolMessage per tool call the model made this turn — every call needs
    an answer or the provider 400s next turn. The first brainstorm_lore is
    acknowledged; a second one (or any stray call routing reached this node
    with) is told it did not run, so the model reissues it rather than assuming
    a result it never got."""
    results: list[ToolMessage] = []
    acked = False
    for call in message.tool_calls:
        call_id = call["id"] or ""
        if call["name"] == "brainstorm_lore" and not acked:
            acked = True
            results.append(ToolMessage(CHAT_ACK, tool_call_id=call_id))
        else:
            results.append(
                ToolMessage(
                    f"'{call['name']}' was not run this turn (one brainstorm "
                    "runs per turn). Call it again if you still need it.",
                    tool_call_id=call_id,
                )
            )
    return results


async def _gather_material(
    topic: str,
    target_ids: list[str],
    *,
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_id: str,
) -> tuple[str, str]:
    """Related canon for the creative tier: the named targets in full plus
    their relationships (who they fight, serve, stand near), and a handful of
    topic-relevant entities as background inspiration.

    Never fails the run: a search that finds nothing yields NO_LORE_SENTINEL,
    not an exception — the whole mode is about inventing where lore is thin."""
    targets = [
        entity
        for entity in await entity_store.get_many(target_ids)
        if entity.project_id == project_id
    ]
    target_id_set = {entity.id for entity in targets}

    search = await search_lore(
        vector_index=vector_index,
        entity_store=entity_store,
        project_id=project_id,
        query=topic,
        limit=BRAINSTORM_SEARCH_K,
    )
    background = [e for e in search.entities if e.id not in target_id_set]

    lore_lines = await _relationship_context(entity_store, edge_store, targets)
    lore_lines.extend(_background_line(entity) for entity in background)

    existing_lore = "\n".join(lore_lines) if lore_lines else NO_LORE_SENTINEL
    targets_block = "\n".join(_target_line(entity) for entity in targets)
    return existing_lore, targets_block


async def _relationship_context(
    entity_store: EntityStore, edge_store: EdgeStore, targets: list[EntityOut]
) -> list[str]:
    """The targets' relationships, rendered with neighbour titles resolved in a
    single batched lookup — entity_store and edge_store share one AsyncSession,
    which forbids concurrent use, so the per-target reads run sequentially."""
    seen: set[str] = set()
    edges = []
    for target in targets:
        for edge in (await edge_store.list_for_entity(target.id))[
            :BRAINSTORM_TARGET_EDGES
        ]:
            if edge.id not in seen:
                seen.add(edge.id)
                edges.append(edge)
    if not edges:
        return []
    neighbour_ids = {
        end for edge in edges for end in (edge.source_entity_id, edge.target_entity_id)
    }
    neighbours = await entity_store.get_many(sorted(neighbour_ids))
    title_by_id = {entity.id: entity.title for entity in neighbours} | {
        target.id: target.title for target in targets
    }
    return [relationship_line(edge, title_by_id) for edge in edges]


def _target_line(entity: EntityOut) -> str:
    return (
        f'<entity id="{entity.id}" type="{entity.type}">'
        f"{entity_to_text(entity)}</entity>"
    )


def _background_line(entity: EntityOut) -> str:
    text = entity_to_text(entity)
    if len(text) > LORE_TEXT_LIMIT:
        text = text[:LORE_TEXT_LIMIT] + "…"
    return f'<entity id="{entity.id}" type="{entity.type}">{text}</entity>'


def _render_ideas(result: BrainstormResult) -> AIMessage:
    """The creative result as a normal assistant chat message. Language-neutral
    structure (markdown, no fixed connective words) so the model's own language
    choice — Russian ideas for a Russian request — carries through untouched."""
    if not result.ideas:
        # The tier returned nothing usable — be honest, never fabricate ideas
        # to fill the gap. The frontend localizes this via the event code.
        return event_message(
            result.note or "No ideas this time — try rephrasing the request.",
            "brainstorm_empty",
        )
    blocks: list[str] = []
    for idea in result.ideas:
        parts = [f"**{idea.title}**", idea.concept, idea.hook]
        blocks.append("\n\n".join(part for part in parts if part.strip()))
    text = "\n\n---\n\n".join(blocks)
    if result.note.strip():
        text = f"{text}\n\n{result.note}"
    return AIMessage(text)


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


def _optional_count(value: Any) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass; never a count
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None
