#!/usr/bin/env bash
# Loregraph uninstaller entry point for macOS/Linux: bash uninstall.sh
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/uninstall.sh" "$@"
