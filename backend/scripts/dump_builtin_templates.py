"""Dump the built-in templates and sheet presets to JSON for the browser demo.

The GitHub Pages demo has no backend: `frontend/src/api/demo/backend.ts` fakes
one in memory. Built-ins are defined in Python (templates/builtins.py,
templates/presets.py), so the demo needs a snapshot of them — and a snapshot
that is generated, not hand-copied, since a template the DM sees in the demo
must be the same sheet they get after installing.

Regenerate after changing a built-in:

    cd backend && uv run python scripts/dump_builtin_templates.py
"""

import json
from pathlib import Path

from loregraph.templates import builtin_presets, builtin_templates

OUTPUT_PATH = (
    Path(__file__).parent.parent.parent
    / "frontend"
    / "src"
    / "api"
    / "demo"
    / "builtins.json"
)


def main() -> None:
    payload = {
        "templates": [t.model_dump(mode="json") for t in builtin_templates()],
        "sheet_presets": [p.model_dump(mode="json") for p in builtin_presets()],
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"Wrote {len(payload['templates'])} templates and "
        f"{len(payload['sheet_presets'])} presets to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
