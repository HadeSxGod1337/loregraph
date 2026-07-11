from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent


def render(name: str, **variables: str) -> str:
    """Render a prompt template file with ${var} substitution.

    safe_substitute: lore text legitimately contains stray `$` characters and
    must never crash prompt rendering."""
    text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
    return Template(text).safe_substitute(**variables)
