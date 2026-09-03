"""The DuckDB OLAP layer.

Two things are worth asserting about a second database engine, and neither is
"does DuckDB work":

1. **It does not leak into the serving path.** DuckDB is a build-time engine.
   The API must import and answer without it, exactly as it does without pandas.
2. **It agrees with SQLite where both can express the question.** A faster
   engine that returns different numbers is not an optimisation, it is a second
   source of truth. The decay analysis is checked row-for-row against a plain
   SQLite implementation of the same thing.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import textwrap

import pytest

from olxads import analytics as A
from olxads import olap
from olxads.config import DB_PATH, DEPLOY_DB_PATH, PROJECT_ROOT
from olxads.db import connect

duckdb_required = pytest.mark.skipif(not olap.is_available(), reason="duckdb not installed")


@pytest.fixture(scope="module")
def conn():
    path = DB_PATH if DB_PATH.exists() else DEPLOY_DB_PATH
    if not path.exists():
        pytest.skip("No database built. Run: python run.py --rebuild")
    c = connect(path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Isolation from the serving path
# ---------------------------------------------------------------------------

PROBE = textwrap.dedent(
    """
    import sys

    class BlockDuckDB:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] == "duckdb":
                raise ImportError("BLOCKED: duckdb")
            return None

    sys.meta_path.insert(0, BlockDuckDB())

    import olxads.api        # noqa: F401
    import olxads.analytics  # noqa: F401

    assert "duckdb" not in sys.modules, "duckdb leaked into the serving path"
    print("OK")
    """
)


def test_serving_path_does_not_import_duckdb():
    """The Vercel function ships neither duckdb nor the warehouse."""
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    assert result.returncode == 0, (
        f"The API imported duckdb.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_olap_module_is_optional():
    """`is_available()` is the switch the ETL uses; it must never raise."""
    assert isinstance(olap.is_available(), bool)


def test_catalog_and_table_list_agree():
    """`OLAP_TABLES` names what the catalog produces, and analytics reads that
    same list — a query added to one and not the others is a silent gap."""
    assert set(olap.QUERIES) == set(olap.OLAP_TABLES)
    assert set(A.OLAP_TABLES) == set(olap.OLAP_TABLES)


# ---------------------------------------------------------------------------
# Materialised results
# ---------------------------------------------------------------------------

def test_every_olap_table_is_materialized(conn):
    missing = olap.missing_tables(conn)
    assert not missing, f"missing OLAP tables: {missing} - rebuild with duckdb installed"
    assert A.olap_available(conn)


def test_olap_analytics_shape(conn):
    if not A.olap_available(conn):
        pytest.skip("OLAP tables not built")
    data = A.olap_analytics(conn)

    for key in (
        "listing_decay", "listing_decay_overall", "demand_weekly", "category_momentum",
        "revenue_concentration", "traction_percentiles", "conversion_by_traction",
    ):
        assert data[key], f"{key} is empty"

    assert data["engine"]["name"] == "duckdb"
    assert data["engine"]["fact_rows"] == 286_461


def test_decay_curve_is_monotonically_indexed(conn):
    """Every category's curve is indexed against its own first week, so week 0
    is 100 by construction and nothing exceeds it by much."""
    if not A.olap_available(conn):
        pytest.skip("OLAP tables not built")
    rows = A.olap_analytics(conn)["listing_decay"]
    week_zero = [r for r in rows if r["week_since_post"] == 0]
    assert week_zero
    assert all(r["retention_index"] == 100.0 for r in week_zero)
    assert all(0 <= r["retention_index"] <= 130 for r in rows)


def test_concentration_curve_is_cumulative(conn):
    """A Lorenz curve must be non-decreasing and finish at 100%."""
    if not A.olap_available(conn):
        pytest.skip("OLAP tables not built")
    rows = A.olap_analytics(conn)["revenue_concentration"]
    shares = [r["cum_revenue_pct"] for r in rows]
    assert shares == sorted(shares)
    assert shares[-1] == pytest.approx(100.0, abs=0.01)
    # Ordered by spend descending, so the first slice must be the largest.
    assert rows[0]["spend"] >= rows[-1]["spend"]


def test_percentiles_are_ordered(conn):
    if not A.olap_available(conn):
        pytest.skip("OLAP tables not built")
    for row in A.olap_analytics(conn)["traction_percentiles"]:
        assert row["p10"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p90"], row["category"]
        assert row["non_advertisers_above_median"] <= row["non_advertisers"]


def test_conversion_quintiles_partition_the_activities(conn):
    if not A.olap_available(conn):
        pytest.skip("OLAP tables not built")
    rows = A.olap_analytics(conn)["conversion_by_traction"]
    assert [r["quintile"] for r in rows] == [1, 2, 3, 4, 5]

    conn_total = conn.execute("SELECT COUNT(*) FROM sales_activities").fetchone()[0]
    assert sum(r["activities"] for r in rows) == conn_total

    # NTILE buckets are contiguous: each floor sits at or above the previous ceiling.
    for previous, current in zip(rows, rows[1:]):
        assert current["views_floor"] >= previous["views_ceiling"] - 1


# ---------------------------------------------------------------------------
# Agreement with SQLite
# ---------------------------------------------------------------------------

SQLITE_DECAY = """
WITH aged AS (
    SELECT l.category,
           CAST((julianday(m.date) - julianday(l.created_date)) / 7 AS INTEGER) AS week_since_post,
           m.listing_id, m.views, m.chats_started + m.phone_reveals AS leads
    FROM listing_metrics m
    JOIN listings l ON l.listing_id = m.listing_id
    WHERE m.date >= l.created_date
),
by_week AS (
    SELECT category, week_since_post,
           COUNT(DISTINCT listing_id) AS listings,
           AVG(views) AS avg_daily_views,
           AVG(leads) AS avg_daily_leads
    FROM aged
    WHERE week_since_post BETWEEN 0 AND 11
    GROUP BY category, week_since_post
)
SELECT b.category, b.week_since_post, b.listings,
       ROUND(b.avg_daily_views, 2), ROUND(b.avg_daily_leads, 3),
       ROUND(100.0 * b.avg_daily_views / NULLIF(z.avg_daily_views, 0), 1)
FROM by_week b
JOIN by_week z ON z.category = b.category AND z.week_since_post = 0
ORDER BY b.category, b.week_since_post
"""


@duckdb_required
def test_duckdb_decay_matches_a_plain_sqlite_implementation(tmp_path):
    """The whole justification for the second engine is speed, not different
    numbers. Run the same analysis both ways and compare row-for-row."""
    if not DB_PATH.exists():
        pytest.skip("Full database (with raw listing_metrics) required")

    sqlite_conn = sqlite3.connect(DB_PATH)
    try:
        expected = sqlite_conn.execute(SQLITE_DECAY).fetchall()
    finally:
        sqlite_conn.close()

    con = olap.build_warehouse(olap_path=tmp_path / "probe.duckdb")
    try:
        actual = con.execute(olap.QUERIES["olap_listing_decay"]).fetchall()
    finally:
        con.close()

    assert len(actual) == len(expected)
    for got, want in zip(actual, expected):
        assert got == pytest.approx(want, rel=1e-6) if isinstance(got, float) else got == want


@duckdb_required
def test_warehouse_loads_the_full_star_schema(tmp_path):
    con = olap.build_warehouse(olap_path=tmp_path / "star.duckdb")
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        assert set(olap.STAR_SCHEMA) <= tables
        assert "dim_date" in tables
        assert con.execute("SELECT COUNT(*) FROM fact_listing_metrics").fetchone()[0] == 286_461
    finally:
        con.close()


@duckdb_required
def test_materialize_is_idempotent(tmp_path):
    """Rebuilding over an existing database must replace, not append."""
    if not DB_PATH.exists():
        pytest.skip("Full database required")

    import shutil

    target = tmp_path / "copy.db"
    shutil.copy(DB_PATH, target)
    conn = sqlite3.connect(target)
    try:
        olap.materialize(conn, olap_path=tmp_path / "w1.duckdb")
        first = conn.execute("SELECT COUNT(*) FROM olap_listing_decay").fetchone()[0]
        olap.materialize(conn, olap_path=tmp_path / "w2.duckdb")
        second = conn.execute("SELECT COUNT(*) FROM olap_listing_decay").fetchone()[0]
    finally:
        conn.close()
    assert first == second


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------

def test_olap_endpoint(api_client):
    response = api_client.get("/api/analytics/olap")
    if response.status_code == 503:
        pytest.skip("Database built without duckdb")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"]["name"] == "duckdb"
    assert body["headlines"]["retention_week1"] is not None


def test_engines_endpoint(api_client):
    body = api_client.get("/api/engines").json()
    assert body["serving"]["engine"] == "sqlite"
    assert body["analytical"]["engine"] in ("duckdb", "none")
