#!/usr/bin/env bash
# Loregraph launcher entry point for macOS/Linux: bash start.sh
# Unsupported providers require both --configure-ai and --experimental-providers.
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/start.sh" "$@"
