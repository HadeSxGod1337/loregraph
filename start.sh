#!/usr/bin/env bash
# Loregraph launcher entry point for macOS/Linux: bash start.sh
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/start.sh" "$@"
