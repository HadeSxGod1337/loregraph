#!/usr/bin/env bash
# Loregraph launcher entry point for macOS/Linux: bash start.sh
# Reconfigure AI later with: bash start.sh --configure-ai
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/start.sh" "$@"
