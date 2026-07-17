"""YAML frontmatter compose/parse for Obsidian notes."""

from typing import Any

import yaml

from loregraph.exceptions import ExternalDataParseError

_DELIMITER = "---"


def compose_note(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(
        frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    return f"{_DELIMITER}\n{yaml_text}\n{_DELIMITER}\n\n{body.strip()}\n"


def parse_note(text: str, source: str) -> tuple[dict[str, Any], str]:
    """Split a note into (frontmatter dict, markdown body). A note without
    frontmatter is valid — returns ({}, body). Malformed YAML raises
    ExternalDataParseError so the importer can report it per file."""
    stripped = text.lstrip("﻿")
    if not stripped.startswith(_DELIMITER):
        return {}, stripped
    lines = stripped.split("\n")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            closing = index
            break
    if closing is None:
        return {}, stripped
    yaml_text = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :])
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ExternalDataParseError(source, f"invalid YAML frontmatter: {e}") from e
    if data is None:
        return {}, body
    if not isinstance(data, dict):
        raise ExternalDataParseError(source, "frontmatter is not a mapping")
    return data, body
