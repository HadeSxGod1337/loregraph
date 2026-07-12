import re
from difflib import SequenceMatcher
from typing import Any

from loregraph.agent.state import AgentState
from loregraph.storage.protocols import EntityStore

# Fuzzy title similarity above which a generated entity counts as a duplicate.
DUPLICATE_TITLE_RATIO = 0.85
# How many times generation may retry over duplicate titles before the
# conflict is surfaced to the DM instead (never an endless loop).
MAX_GENERATION_ATTEMPTS = 2
# Titles shorter than this are too collision-prone for mention detection
# («Al» matches half the dictionary).
MIN_MENTION_TITLE_LENGTH = 3


def _mentions(brief: str, title: str) -> bool:
    """Word-boundary match, not bare substring: «Мира» must not fire on
    «мирами», «123» must not fire on «1230»."""
    if len(title) < MIN_MENTION_TITLE_LENGTH:
        return False
    pattern = r"(?<!\w)" + re.escape(title.casefold()) + r"(?!\w)"
    return re.search(pattern, brief.casefold()) is not None


async def check_duplicates_request(
    state: AgentState, *, entity_store: EntityStore
) -> dict[str, Any]:
    """Pre-generation check: if the instruction literally names an existing
    entity, the DM probably wants to build around it, not clone it."""
    entities = await entity_store.list_entities(state.project_id)
    mentioned = [
        f"The request mentions existing entity «{entity.title}» "
        f"(id {entity.id}, {entity.type}) — the draft should connect to it, "
        f"not duplicate it."
        for entity in entities
        if entity.title and _mentions(state.pending_brief, entity.title)
    ]
    if mentioned:
        return {"warnings": [*state.warnings, *mentioned]}
    return {}


async def check_duplicates_draft(
    state: AgentState, *, entity_store: EntityStore
) -> dict[str, Any]:
    """Post-generation check over the whole batch: the LLM invents titles
    during generation, so name collisions (against existing lore AND inside
    the batch itself) can only be caught here."""
    if state.draft is None or not state.draft.entities:
        return {}
    existing = await entity_store.list_entities(state.project_id)
    collisions: list[str] = []

    for draft_entity in state.draft.entities:
        title = draft_entity.title.casefold()
        for entity in existing:
            if _similar(title, entity.title.casefold()):
                collisions.append(
                    f"«{draft_entity.title}» duplicates existing entity "
                    f"«{entity.title}» (id {entity.id})"
                )

    seen: dict[str, str] = {}
    for draft_entity in state.draft.entities:
        title = draft_entity.title.casefold()
        for seen_title, seen_original in seen.items():
            if _similar(title, seen_title):
                collisions.append(
                    f"The draft contains two near-identical titles: "
                    f"«{seen_original}» and «{draft_entity.title}»"
                )
        seen[title] = draft_entity.title

    if not collisions:
        return {}
    if state.attempts < MAX_GENERATION_ATTEMPTS:
        return {
            "retry_feedback": (
                "Title collisions found: "
                + "; ".join(collisions)
                + ". Regenerate the batch with clearly distinct names and "
                "characters (connect to existing entities via relationships "
                "instead of recreating them)."
            )
        }
    return {
        "warnings": [
            *state.warnings,
            *[f"Possible duplicate: {c} — review carefully." for c in collisions],
        ]
    }


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= DUPLICATE_TITLE_RATIO


def route_after_draft_check(state: AgentState) -> str:
    """Conditional edge: loop back to generation while retry budget remains."""
    if state.retry_feedback and state.attempts < MAX_GENERATION_ATTEMPTS:
        return "retry"
    return "continue"
