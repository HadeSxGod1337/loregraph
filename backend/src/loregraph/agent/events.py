from langchain_core.messages import AIMessage


def event_message(text: str, code: str, **params: str) -> AIMessage:
    """A deterministic, backend-composed chat message — zero extra LLM
    tokens. `text` is the canonical English content, kept in the model's own
    conversation history so later turns have context regardless of UI
    language. `code`/`params` let the frontend render a localized version
    (events.<code> in its i18n catalog) instead of the literal English text.

    Same convention as HumanMessage's `attachment_filenames` in
    additional_kwargs (see agent/multimodal.py) — round-tripped by
    agent/runner.py::transcript, never sent back to the LLM as structured
    data."""
    return AIMessage(
        text, additional_kwargs={"event": {"code": code, "params": params}}
    )
