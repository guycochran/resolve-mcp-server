"""Compatibility launcher: python src/server.py or python -m src.server."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_mcp.server import main, mcp  # noqa: E402,F401

if __name__ == "__main__":
    main()