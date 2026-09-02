"""SQLite access layer.

The platform reads from a SQLite database built by `olxads.etl` out of the
generated CSVs. SQLite keeps the whole thing dependency-light and portable —
clone the repo, run one command, get a working app — while still giving real
indexed SQL for the ~300k-row metrics table.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from .config import DB_PATH

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


def connect(db_path: Path | str = DB_PATH, *, read_only: bool = False) -> sqlite3.Connection:
    """Open a connection with row access by column name and FKs enforced."""
    path = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: Path | str = DB_PATH, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path, read_only=read_only)
    try:
        yield conn
        if not read_only:
            conn.commit()
    finally:
        conn.close()


def query(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return plain dicts (JSON-serializable straight out)."""
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def query_one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = query(conn, sql, params)
    return rows[0] if rows else None


def query_df(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> "pd.DataFrame":
    """Analysis helper (notebooks, scripts). pandas is imported lazily so the
    serving runtime never has to ship it."""
    import pandas as pd

    return pd.read_sql_query(sql, conn, params=params)


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None
