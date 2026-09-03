"""Shared fixtures.

The API tests need a client bound to a *disposable* copy of the built database,
because logging an activity is a real write. Building that copy once per module
is the expensive part, so it lives here and both test modules reuse it.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from olxads.config import DB_PATH, DEPLOY_DB_PATH


@pytest.fixture(scope="module")
def api_client(tmp_path_factory) -> TestClient:
    source = DB_PATH if DB_PATH.exists() else DEPLOY_DB_PATH
    if not source.exists():
        pytest.skip("Database not built. Run: python run.py --rebuild")

    tmp_db = tmp_path_factory.mktemp("db") / "test.db"
    shutil.copy(source, tmp_db)

    from olxads import api as api_module

    def override_conn():
        conn = sqlite3.connect(tmp_db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    api_module.app.dependency_overrides[api_module.get_conn] = override_conn
    yield TestClient(api_module.app)
    api_module.app.dependency_overrides.clear()
