"""Vercel entry point: the same FastAPI app, no long-running server.

Vercel's Python runtime picks up an ASGI `app` from this module. The repo root
joins sys.path so `src/` and the committed artifacts resolve as they do locally.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    # chromadb talks to sqlite; some managed runtimes ship an older build, so
    # swap in pysqlite3 when it is present (harmless when it is not).
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except (ImportError, KeyError):
    pass

from src.app import app  # noqa: E402, F401
