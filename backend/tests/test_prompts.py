from loregraph.prompts import project_instructions_block, render


def test_project_instructions_block_empty_for_none() -> None:
    assert project_instructions_block(None) == ""


def test_project_instructions_block_empty_for_blank_string() -> None:
    assert project_instructions_block("") == ""


def test_project_instructions_block_wraps_text() -> None:
    block = project_instructions_block("Write NPC bios in second person.")
    assert "<project_instructions" in block
    assert "Write NPC bios in second person." in block
    assert "</project_instructions>" in block


def test_assistant_system_prompt_includes_instructions_block() -> None:
    rendered = render(
        "assistant.system.md",
        project_instructions_block=project_instructions_block("Dark, gothic tone."),
    )
    assert "Dark, gothic tone." in rendered


def test_assistant_system_prompt_omits_block_when_absent() -> None:
    rendered = render(
        "assistant.system.md",
        project_instructions_block=project_instructions_block(None),
    )
    assert "<project_instructions" not in rendered


def test_generate_lore_system_prompt_includes_instructions_block() -> None:
    rendered = render(
        "generate_lore.system.md",
        project_instructions_block=project_instructions_block(
            'Always add a "plot hook" field.'
        ),
    )
    assert 'Always add a "plot hook" field.' in rendered


def test_generate_lore_system_prompt_omits_block_when_absent() -> None:
    rendered = render(
        "generate_lore.system.md",
        project_instructions_block=project_instructions_block(None),
    )
    assert "<project_instructions" not in rendered
