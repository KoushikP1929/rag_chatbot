"""Vercel entrypoint for the FastAPI preset.

Vercel's Python runtime looks for a module exporting an ASGI ``app`` at a
documented location (app.py, main.py, ... at the project root) and routes
every request to it with the original path, so no rewrites are needed. The
from-scratch bootstrap in src.app (local ``.venv`` import of src.app:app)
is untouched by this file.
"""

import sys

try:
    # chromadb talks to sqlite; some managed runtimes ship an older build, so
    # swap in pysqlite3 when it is present (harmless when it is not).
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except (ImportError, KeyError):
    pass

from src.app import app  # noqa: F401
