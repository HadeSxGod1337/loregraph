from langchain_core.messages import AIMessage, HumanMessage

from loregraph.agent.runner import transcript
from loregraph.agent.state import AgentState


def test_transcript_round_trips_attachment_filenames() -> None:
    state = AgentState(
        project_id="p1",
        messages=[
            HumanMessage(
                content=[
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "mime_type": "image/png", "base64": "..."},
                ],
                additional_kwargs={"attachment_filenames": ["portrait.png"]},
            ),
            AIMessage("It's a portrait."),
        ],
    )
    out = transcript(state)
    assert out[0].role == "user"
    assert out[0].text == "What is this?"
    assert out[0].attachments == ["portrait.png"]
    assert out[1].role == "assistant"
    assert out[1].attachments == []


def test_transcript_plain_text_message_has_no_attachments() -> None:
    state = AgentState(
        project_id="p1",
        messages=[HumanMessage("Hello")],
    )
    out = transcript(state)
    assert out[0].attachments == []


def test_transcript_hides_inlined_text_attachment_dump() -> None:
    """Regression: a text-like attachment (.json/.md/...) is inlined into the
    message content as its own {"type": "text"} block for the model (see
    agent/multimodal.py) — the transcript must show what the DM actually
    typed, not that block concatenated onto it."""
    state = AgentState(
        project_id="p1",
        messages=[
            HumanMessage(
                content=[
                    {"type": "text", "text": "Add my character"},
                    {
                        "type": "text",
                        "text": '<attached_file name="sheet.json">\n'
                        '{"hero": "Voss"}\n</attached_file>',
                    },
                ],
                additional_kwargs={
                    "attachment_filenames": ["sheet.json"],
                    "user_text": "Add my character",
                },
            )
        ],
    )
    out = transcript(state)
    assert out[0].text == "Add my character"
    assert "attached_file" not in out[0].text
    assert out[0].attachments == ["sheet.json"]
