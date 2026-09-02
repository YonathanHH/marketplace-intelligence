"""Deployment guarantees.

The platform deploys as a small serverless function. Two properties make that
possible, and both are easy to break with an innocent-looking import, so they
are asserted here rather than trusted:

1. The serving path never imports pandas or numpy (~90 MB).
2. The slim deployment database returns the same results as the full one.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from olxads.config import DEPLOY_DB_PATH, PROJECT_ROOT
from olxads.db import connect

PROBE = textwrap.dedent(
    """
    import sys

    class BlockHeavyImports:
        BLOCKED = {"pandas", "numpy"}

        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in self.BLOCKED:
                raise ImportError(f"BLOCKED: {name}")
            return None

    sys.meta_path.insert(0, BlockHeavyImports())

    import olxads.api          # noqa: F401
    import olxads.analytics    # noqa: F401
    import olxads.actions      # noqa: F401
    import olxads.rules        # noqa: F401
    import olxads.runtime      # noqa: F401
    import olxads.db           # noqa: F401

    assert "pandas" not in sys.modules, "pandas leaked into the serving path"
    assert "numpy" not in sys.modules, "numpy leaked into the serving path"
    print("OK")
    """
)


def test_serving_path_has_no_pandas_or_numpy():
    """A serverless bundle with pandas+numpy is ~90 MB heavier and slower to cold start.

    Run in a subprocess because the rest of the suite legitimately imports pandas.
    """
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, (
        "The API serving path imported pandas or numpy.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_rules_module_is_dependency_free():
    """`rules` is shared by the build pipeline and the live write path."""
    source = (PROJECT_ROOT / "olxads" / "rules.py").read_text(encoding="utf-8")
    for banned in ("import pandas", "import numpy", "from pandas", "from numpy"):
        assert banned not in source, f"rules.py must stay import-free ({banned})"


def test_vercel_entrypoint_exposes_an_asgi_app():
    spec = importlib.util.spec_from_file_location(
        "vercel_entry", PROJECT_ROOT / "api" / "index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.app)


@pytest.mark.parametrize("incoming,expected", [
    ("/api/leads", "/api/leads"),          # path preserved by the host
    ("/api/index/leads", "/api/leads"),    # collapsed onto the function route
    ("/api/index", "/api"),                # function route itself
    ("/leads", "/api/leads"),              # prefix stripped by the host
])
def test_entrypoint_normalizes_paths(incoming, expected):
    """Whatever the host does to /api/*, the app must still route."""
    spec = importlib.util.spec_from_file_location(
        "vercel_entry_paths", PROJECT_ROOT / "api" / "index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    seen: dict = {}

    async def fake_app(scope, receive, send):
        seen["path"] = scope["path"]

    wrapper = module.NormalizeApiPath(fake_app)

    import asyncio
    asyncio.run(wrapper({"type": "http", "path": incoming}, None, None))
    assert seen["path"] == expected


def test_deploy_database_is_present_and_small():
    if not DEPLOY_DB_PATH.exists():
        pytest.skip("Deploy DB not built. Run: python run.py --deploy-build")
    size_mb = DEPLOY_DB_PATH.stat().st_size / 1_048_576
    assert size_mb < 60, f"deploy database is {size_mb:.1f} MB - too large to ship comfortably"


def test_deploy_database_serves_identical_analytics():
    """The slim artefact must not change a single reported number."""
    from olxads.config import DB_PATH

    if not (DEPLOY_DB_PATH.exists() and DB_PATH.exists()):
        pytest.skip("Both databases required for the comparison")

    from olxads import analytics as A

    def snapshot(path: Path) -> dict:
        conn = connect(path)
        try:
            return {
                "overview": {k: v for k, v in A.overview(conn).items() if k != "built_at"},
                "marketplace": A.marketplace_analytics(conn),
                "advertising": A.advertising_analytics(conn),
                "pipeline": A.pipeline_analytics(conn),
                "coverage": A.coverage_analytics(conn),
                "leads": A.list_leads(conn, {"page_size": 50}),
            }
        finally:
            conn.close()

    full = json.dumps(snapshot(DB_PATH), sort_keys=True, default=str)
    slim = json.dumps(snapshot(DEPLOY_DB_PATH), sort_keys=True, default=str)
    assert full == slim


def test_deploy_database_has_no_raw_metrics_table():
    if not DEPLOY_DB_PATH.exists():
        pytest.skip("Deploy DB not built")
    conn = connect(DEPLOY_DB_PATH)
    try:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "listing_metrics" not in tables
    assert {"listing_totals", "marketplace_daily", "seller_daily_traction"} <= tables


def test_serverless_copies_database_to_a_writable_location(tmp_path, monkeypatch):
    """Serverless filesystems are read-only apart from the temp dir."""
    import olxads.runtime as runtime

    fake_source = tmp_path / "olxads-deploy.db"
    shutil.copy(DEPLOY_DB_PATH if DEPLOY_DB_PATH.exists() else _any_db(), fake_source)

    monkeypatch.setattr(runtime, "IS_SERVERLESS", True)
    monkeypatch.setattr(runtime, "DB_PATH", tmp_path / "missing.db")
    monkeypatch.setattr(runtime, "DEPLOY_DB_PATH", fake_source)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    runtime.reset_cache()

    resolved = runtime.database_path()
    assert resolved.parent == tmp_path / "tmp"
    assert resolved.exists()

    # The copy must be writable — the log-activity path depends on it.
    conn = connect(resolved)
    conn.execute("CREATE TABLE _writable_probe (x INTEGER)")
    conn.close()

    runtime.reset_cache()


def _any_db() -> Path:
    from olxads.config import DB_PATH
    return DB_PATH
