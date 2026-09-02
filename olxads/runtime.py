"""Runtime database resolution, including read-only serverless hosts.

Local development uses the full database (raw metrics included). A deployment
ships the slim artefact built with `--deploy`, which contains the same
aggregates and therefore returns identical results.

Serverless filesystems (Vercel, Lambda) are read-only except for the temp
directory. Since logging an activity writes to SQLite, the database is copied
into the writable temp dir once per instance. Those writes are real but
instance-local: they survive within a warm instance and disappear on a cold
start, which is the right trade-off for a public demo.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .config import DB_PATH, DEPLOY_DB_PATH, IS_SERVERLESS

_resolved: Path | None = None


def source_database_path() -> Path:
    """The database shipped with the code, before any runtime copying."""
    if DB_PATH.exists():
        return DB_PATH
    return DEPLOY_DB_PATH


def database_path() -> Path:
    """The path the API should actually open. Cached per process."""
    global _resolved
    if _resolved is not None:
        return _resolved

    source = source_database_path()
    if IS_SERVERLESS and source.exists():
        writable = Path(tempfile.gettempdir()) / "olxads.db"
        if not writable.exists():
            shutil.copy(source, writable)
        source = writable

    _resolved = source
    return source


def reset_cache() -> None:
    """Test hook — forget the resolved path."""
    global _resolved
    _resolved = None
