#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$REPO_DIR"
exec "$REPO_DIR/.venv/bin/python" -m resolve_mcp