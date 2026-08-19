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


def test_propose_changes_system_prompt_includes_instructions_block() -> None:
    rendered = render(
        "propose_changes.system.md",
        project_instructions_block=project_instructions_block(
            'Always add a "plot hook" field.'
        ),
    )
    assert 'Always add a "plot hook" field.' in rendered


def test_propose_changes_system_prompt_omits_block_when_absent() -> None:
    rendered = render(
        "propose_changes.system.md",
        project_instructions_block=project_instructions_block(None),
    )
    assert "<project_instructions" not in rendered


# ---------------------------------------------------------------------------
# Semantic contract (P0 fix): project instructions are mandatory project
# requirements — world/content constraints, naming, required fields, language
# — never mere "style/format preferences" a creative pass can shrug off. These
# are supplementary wording guards; the real proof that the fix changes actual
# behavior is invocation-level (tests/test_project_instructions.py), since
# neither of these two checks alone would catch a broken delivery pipeline.
# ---------------------------------------------------------------------------


def test_project_instructions_block_is_not_downgraded_to_style_only() -> None:
    """The bug: instructions were physically delivered but wrapped as 'game
    master's style/format preferences', which is false for a world/content
    constraint like "no magic" (see docs/world.md's own examples) — that
    framing is what let a creative pass treat a hard project rule as optional
    flavor. Guards against reintroducing that specific mischaracterization."""
    block = project_instructions_block("Никакой магии.")
    assert "style/format preferences" not in block


def test_project_instructions_block_states_mandatory_contract_and_boundary() -> None:
    """The note must (a) call instructions mandatory/binding rather than
    optional, (b) still state the Level-1 boundary they cannot cross (human
    review remains the actual enforcement point for that boundary), and (c)
    give explicit guidance for the case where the current request conflicts
    with one of them, instead of leaving that ambiguous."""
    block = project_instructions_block("Никакой магии.").lower()
    assert "mandatory" in block
    assert "human review" in block
    assert "conflict" in block
