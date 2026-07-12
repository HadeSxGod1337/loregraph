from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from loregraph.agent.events import event_message
from loregraph.agent.state import AgentState
from loregraph.prompts import project_instructions_block, render
from loregraph.storage.protocols import ProjectStore

# Conversation window sent to the LLM: enough for coherent chat, small enough
# to keep per-turn token cost flat as the conversation grows.
MAX_CHAT_WINDOW = 24

BUDGET_EXHAUSTED_REPLY = (
    "Token budget for this conversation is exhausted — start a new session to continue."
)


class search_lore(BaseModel):
    """Semantic search over the world's lore. Use it BEFORE answering any
    question about the world."""

    query: str = Field(description="What to look for, in the lore's language.")


class get_entity_details(BaseModel):
    """Full details of one entity by its id (ids come from search_lore)."""

    entity_id: str


class search_knowledge_base(BaseModel):
    """Semantic search over the project's uploaded reference documents
    (rulebooks, setting bibles) — NOT world canon. Use it when the game
    master's question is about rules or reference material rather than the
    world's own established facts (that's search_lore)."""

    query: str = Field(description="What to look for, in the document's language.")


class propose_lore(BaseModel):
    """Draft new world content (entities + relationships) for the game
    master's review. The only way to create anything."""

    brief: str = Field(
        description="Concise self-contained description of what to create, "
        "carrying all relevant user constraints (scale, tone, connections)."
    )


ASSISTANT_TOOLS: list[type[BaseModel]] = [
    search_lore,
    get_entity_details,
    search_knowledge_base,
    propose_lore,
]


def chat_window(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Last N messages, never starting with an orphaned ToolMessage (a tool
    result without its tool call is a provider-side 400)."""
    window = list(messages[-MAX_CHAT_WINDOW:])
    while window and isinstance(window[0], ToolMessage):
        window.pop(0)
    return window


async def assistant(
    state: AgentState,
    *,
    chat_model: BaseChatModel,
    token_budget: int,
    project_store: ProjectStore,
) -> dict[str, Any]:
    """The conversational brain: answers from retrieved lore, asks clarifying
    questions, and calls propose_lore to draft content. Deliberately has no
    write access — creation always routes through the review pipeline."""
    if state.over_budget(token_budget):
        return {
            "messages": [
                event_message(BUDGET_EXHAUSTED_REPLY, "budget_exhausted_reply")
            ]
        }

    # Fetched fresh each turn (not cached in AgentState) so edits to the
    # project's instructions take effect on the very next message, and so
    # the persisted checkpoint schema never has to carry project settings.
    project = await project_store.get(state.project_id)
    model = chat_model.bind_tools(ASSISTANT_TOOLS)
    response = await model.ainvoke(
        [
            SystemMessage(
                render(
                    "assistant.system.md",
                    project_instructions_block=project_instructions_block(
                        project.agent_instructions
                    ),
                )
            ),
            *chat_window(state.messages),
        ]
    )
    usage = cast(dict[str, int], response.usage_metadata or {})
    return {
        "messages": [response],
        "input_tokens": state.input_tokens + usage.get("input_tokens", 0),
        "output_tokens": state.output_tokens + usage.get("output_tokens", 0),
    }


def route_after_assistant(state: AgentState) -> str:
    """tools → run read tools; propose → start the draft pipeline;
    end → the turn is a plain reply (answer or clarifying question)."""
    last = state.messages[-1] if state.messages else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return "end"
    if any(call["name"] == "propose_lore" for call in last.tool_calls):
        return "propose"
    return "tools"


def begin_proposal(state: AgentState) -> dict[str, Any]:
    """Accept the propose_lore call: answer it (providers require a tool
    result for every tool call) and reset per-proposal state."""
    last = state.messages[-1]
    assert isinstance(last, AIMessage)
    tool_messages = [
        ToolMessage(
            "Draft pipeline started; the result goes to the game master's review.",
            tool_call_id=call["id"] or "",
        )
        for call in last.tool_calls
    ]
    brief = next(
        str(call["args"].get("brief", ""))
        for call in last.tool_calls
        if call["name"] == "propose_lore"
    )
    return {
        "messages": tool_messages,
        "pending_brief": brief,
        "revision_feedback": "",
        "draft": None,
        "warnings": [],
        "attempts": 0,
        "retry_feedback": "",
        "draft_committed": False,
        "decision_action": None,
    }
