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
