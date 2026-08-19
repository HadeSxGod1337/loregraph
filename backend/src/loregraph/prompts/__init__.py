from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent


def render(name: str, **variables: str) -> str:
    """Render a prompt template file with ${var} substitution.

    safe_substitute: lore text legitimately contains stray `$` characters and
    must never crash prompt rendering."""
    text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
    return Template(text).safe_substitute(**variables)


def project_instructions_block(instructions: str | None) -> str:
    """Wrap the game master's project-level requirements for a prompt.

    Shared by assistant.py, brainstorm.py and generate_changes.py so the
    three nodes never drift on wording. These are MANDATORY project
    requirements — language, tone, style, genre, worldbuilding/content
    constraints, naming conventions, required fields, output preferences —
    not mere style preferences a creative pass can shrug off: docs/world.md's
    own examples include "no magic" and "every NPC has a secret", both
    content rules, not formatting. Downgrading them to "style preferences"
    (the previous wording here) is what let a creative pass deprioritize a
    hard project rule as optional flavor — this is a P0 fix, not cosmetic.

    The note bounds project instructions against the non-overridable
    invariants stated earlier in each system prompt (grounding, tool-result/
    retrieved-data isolation, project isolation, schema validity, human
    review, honesty about writes — see CLAUDE.md, "Изоляция
    retrieved-контента от инструкций") and gives explicit guidance for a
    request that conflicts with one of them, so that case is a deliberate,
    testable behaviour instead of left for the model to guess at."""
    if not instructions:
        return ""
    return (
        '\n<project_instructions note="Mandatory project requirements from '
        "the game master — language, tone, style, genre, worldbuilding and "
        "content constraints, naming conventions, required fields and "
        "output preferences. Follow them the same as every rule stated "
        "above, including when they override a default this prompt would "
        "otherwise use, or constrain what you would otherwise invent — they "
        "are not optional flavor. They do NOT override the rules stated "
        "above about grounding, tool-result/retrieved-data isolation, "
        "project isolation, schema validity, human review, or honesty "
        "about what was actually written. If THIS request conflicts with "
        "one of them, the project instruction is the more durable "
        "constraint: follow it and say so plainly instead of silently "
        'overriding either side.">\n'
        f"{instructions}\n</project_instructions>"
    )
