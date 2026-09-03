"""DuckDB OLAP layer — the analytical engine behind the deep-dive analytics.

Why a second engine at all
--------------------------
SQLite is the right *operational* store here: one file, zero dependencies,
indexed point lookups for the opportunity queue, and a writable path for
logging an activity. It is the wrong tool for the questions on the Deep Dive
page, which are analytical rather than transactional:

    "how fast does a listing's demand decay after it is posted?"
    "which categories are accelerating, on a 4-week moving average?"
    "what share of ad revenue comes from the top 5% of advertisers?"
    "what was a seller's trailing 28-day traction *at the moment* a rep called?"

Those are full scans of the 286k-row metric fact with window frames, ordered
aggregates, quantiles and an as-of join. DuckDB is columnar and vectorised, so
it answers them in tens of milliseconds against SQLite's seconds — and two of
them (`ASOF JOIN`, `quantile_cont`) SQLite cannot express at all.

Where it sits in the pipeline
-----------------------------
DuckDB is a **build-time** engine, exactly like pandas:

    CSV ──► DuckDB star schema ──► six OLAP result sets ──► SQLite `olap_*`
                                                             tables ──► API

The results are tiny (a few hundred rows in total), so materialising them into
the SQLite artefact keeps the serving path stdlib-only and keeps the serverless
bundle small. `olxads.api` never imports this module; `olxads.etl` does.

The warehouse itself (`data/processed/olxads.duckdb`) is kept after the build so
it can be queried directly — `python scripts/build_olap.py --benchmark`, a
notebook, or the DuckDB CLI — but nothing at request time depends on it.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .config import OLAP_DB_PATH, RAW_DIR

__all__ = [
    "OLAP_TABLES",
    "duckdb_version",
    "is_available",
    "build_warehouse",
    "run_queries",
    "materialize",
]

# The tables this module writes into SQLite. `analytics.olap_analytics` reads
# exactly these, so the two lists must stay in step.
OLAP_TABLES = (
    "olap_listing_decay",
    "olap_demand_weekly",
    "olap_category_momentum",
    "olap_revenue_concentration",
    "olap_traction_percentiles",
    "olap_conversion_by_traction",
)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """True when DuckDB can be imported. The build degrades gracefully without it."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return False
    return True


def duckdb_version() -> str | None:
    try:
        import duckdb
    except ImportError:
        return None
    return duckdb.__version__


# ---------------------------------------------------------------------------
# Star schema
# ---------------------------------------------------------------------------

# Facts and dimensions, loaded straight from the CSVs by DuckDB's own reader —
# no pandas in this path, so the warehouse builds from a clean checkout with
# nothing but duckdb installed.
STAR_SCHEMA: dict[str, str] = {
    "dim_seller": "sellers",
    "dim_listing": "listings",
    "fact_listing_metrics": "listing_metrics",
    "fact_campaign": "ad_campaigns",
    "fact_activity": "sales_activities",
}


def build_warehouse(
    raw_dir: Path = RAW_DIR,
    olap_path: Path = OLAP_DB_PATH,
    *,
    sqlite_conn: sqlite3.Connection | None = None,
) -> Any:
    """Create (or replace) the columnar warehouse and return an open connection.

    `seller_scores` is derived by the pandas scoring pipeline and lives in
    SQLite, so it is copied across row-by-row rather than re-derived — 1,500
    rows, and it keeps a single definition of the score.
    """
    import duckdb

    olap_path.parent.mkdir(parents=True, exist_ok=True)
    if olap_path.exists():
        olap_path.unlink()

    con = duckdb.connect(str(olap_path))
    for table, source in STAR_SCHEMA.items():
        csv_path = raw_dir / f"{source}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Missing {csv_path}. Run `python scripts/generate_data.py` first."
            )
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS "
            f"SELECT * FROM read_csv_auto(?, header = true)",
            [str(csv_path)],
        )

    # A conformed date dimension: every analysis below buckets by week, so
    # deriving the calendar once keeps the query text about the business
    # question rather than about date arithmetic.
    con.execute(
        """
        CREATE OR REPLACE TABLE dim_date AS
        SELECT d::DATE                      AS date,
               date_trunc('week', d)::DATE  AS week_start,
               date_trunc('month', d)::DATE AS month_start,
               dayofweek(d)                 AS day_of_week
        FROM (SELECT UNNEST(generate_series(
                  (SELECT MIN(date) FROM fact_listing_metrics),
                  (SELECT MAX(date) FROM fact_listing_metrics),
                  INTERVAL 1 DAY)) AS d)
        """
    )

    if sqlite_conn is not None:
        _copy_from_sqlite(con, sqlite_conn, "seller_scores")

    return con


def _copy_from_sqlite(con: Any, sqlite_conn: sqlite3.Connection, table: str) -> None:
    """Mirror a SQLite table into DuckDB, preserving column names and order.

    Deliberately uses stdlib `sqlite3` rather than DuckDB's `sqlite_scanner`
    extension: that extension is downloaded on first use, and a build should not
    need network access.
    """
    cur = sqlite_conn.execute(f"SELECT * FROM {table}")
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()

    con.execute(f"DROP TABLE IF EXISTS {table}")
    # Let DuckDB infer types from a typed sample, then load the rest.
    con.execute(
        f"CREATE TABLE {table} ({', '.join(_sqlite_column_ddl(sqlite_conn, table))})"
    )
    if rows:
        placeholders = ", ".join("?" for _ in columns)
        con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


_SQLITE_TO_DUCK = {"INTEGER": "BIGINT", "REAL": "DOUBLE", "TEXT": "VARCHAR", "": "VARCHAR"}


def _sqlite_column_ddl(conn: sqlite3.Connection, table: str) -> list[str]:
    out = []
    for row in conn.execute(f"PRAGMA table_info({table})").fetchall():
        name, decl = row[1], (row[2] or "").upper()
        out.append(f'"{name}" {_SQLITE_TO_DUCK.get(decl, "VARCHAR")}')
    return out


# ---------------------------------------------------------------------------
# The query catalog
#
# Each entry is one analytical question. They are kept as literal SQL rather
# than built up in Python because the SQL *is* the analysis — it should be
# readable, and runnable unchanged in the DuckDB CLI against the same warehouse.
# ---------------------------------------------------------------------------

QUERIES: dict[str, str] = {
    # -----------------------------------------------------------------------
    # 1. How fast does a listing's demand decay after posting?
    #
    # The commercial case for bump-up and search-boost products lives here: if
    # organic reach collapses after week 1, paid re-promotion is not an upsell,
    # it is a fix. Needs the full 286k-row fact joined to listing age, then a
    # window to index each curve against its own first week.
    # -----------------------------------------------------------------------
    "olap_listing_decay": """
        WITH aged AS (
            SELECT l.category,
                   -- `//` is integer division; DuckDB's `/` is always float,
                   -- and CAST(float AS INTEGER) rounds rather than truncates,
                   -- which would silently shift every bucket by half a week.
                   date_diff('day', l.created_date, m.date) // 7 AS week_since_post,
                   m.listing_id,
                   m.views,
                   m.chats_started + m.phone_reveals AS leads
            FROM fact_listing_metrics m
            JOIN dim_listing l USING (listing_id)
            WHERE m.date >= l.created_date
        ),
        by_week AS (
            SELECT category,
                   week_since_post,
                   COUNT(DISTINCT listing_id) AS listings,
                   AVG(views) AS avg_daily_views,
                   AVG(leads) AS avg_daily_leads
            FROM aged
            WHERE week_since_post BETWEEN 0 AND 11
            GROUP BY ALL
        )
        SELECT category,
               week_since_post,
               listings,
               ROUND(avg_daily_views, 2) AS avg_daily_views,
               ROUND(avg_daily_leads, 3) AS avg_daily_leads,
               ROUND(100.0 * avg_daily_views / NULLIF(
                   first_value(avg_daily_views) OVER (
                       PARTITION BY category ORDER BY week_since_post
                   ), 0), 1) AS retention_index
        FROM by_week
        ORDER BY category, week_since_post
    """,

    # -----------------------------------------------------------------------
    # 2. Weekly demand per category with a 4-week moving average.
    #
    # A raw weekly series is too noisy to steer a territory plan; the trailing
    # frame smooths it, and LAG gives the week-on-week delta in the same pass.
    # -----------------------------------------------------------------------
    "olap_demand_weekly": """
        WITH weekly AS (
            SELECT l.category,
                   date_trunc('week', m.date)::DATE AS week,
                   SUM(m.views) AS views,
                   SUM(m.chats_started + m.phone_reveals) AS leads
            FROM fact_listing_metrics m
            JOIN dim_listing l USING (listing_id)
            GROUP BY ALL
        ),
        framed AS (
            SELECT category, week, views, leads,
                   AVG(views) OVER (
                       PARTITION BY category ORDER BY week
                       ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                   ) AS views_4w_avg,
                   LAG(views) OVER (PARTITION BY category ORDER BY week) AS prev_views
            FROM weekly
        )
        SELECT category,
               strftime(week, '%Y-%m-%d') AS week,
               views,
               leads,
               ROUND(views_4w_avg, 0) AS views_4w_avg,
               ROUND(100.0 * (views - prev_views) / NULLIF(prev_views, 0), 2) AS wow_pct
        FROM framed
        -- The first and last calendar weeks are partial, so their totals are
        -- not comparable to a full week; drop them rather than show a false dip.
        WHERE week > (SELECT MIN(week) FROM weekly)
          AND week < (SELECT MAX(week) FROM weekly)
        ORDER BY category, week
    """,

    # -----------------------------------------------------------------------
    # 3. Which categories are accelerating? Last 4 complete weeks vs. the 4
    #    before them, ranked. This is the summary a territory review opens with.
    # -----------------------------------------------------------------------
    "olap_category_momentum": """
        WITH weekly AS (
            SELECT l.category,
                   date_trunc('week', m.date)::DATE AS week,
                   SUM(m.views) AS views,
                   SUM(m.chats_started + m.phone_reveals) AS leads
            FROM fact_listing_metrics m
            JOIN dim_listing l USING (listing_id)
            GROUP BY ALL
        ),
        complete AS (
            SELECT * FROM weekly
            WHERE week > (SELECT MIN(week) FROM weekly)
              AND week < (SELECT MAX(week) FROM weekly)
        ),
        indexed AS (
            SELECT *,
                   dense_rank() OVER (ORDER BY week DESC) AS weeks_ago
            FROM complete
        )
        SELECT category,
               SUM(CASE WHEN weeks_ago <= 4 THEN views ELSE 0 END) AS recent_views,
               SUM(CASE WHEN weeks_ago BETWEEN 5 AND 8 THEN views ELSE 0 END) AS prior_views,
               SUM(CASE WHEN weeks_ago <= 4 THEN leads ELSE 0 END) AS recent_leads,
               ROUND(100.0 * (
                   SUM(CASE WHEN weeks_ago <= 4 THEN views ELSE 0 END)
                   - SUM(CASE WHEN weeks_ago BETWEEN 5 AND 8 THEN views ELSE 0 END)
               ) / NULLIF(SUM(CASE WHEN weeks_ago BETWEEN 5 AND 8 THEN views ELSE 0 END), 0), 2)
                   AS momentum_pct
        FROM indexed
        WHERE weeks_ago <= 8
        GROUP BY ALL
        ORDER BY momentum_pct DESC
    """,

    # -----------------------------------------------------------------------
    # 4. Revenue concentration (Lorenz curve): advertisers ordered by spend,
    #    bucketed into 5% slices, against cumulative share of revenue.
    #
    # Answers "how exposed is the book to its largest accounts?" — a running
    # ordered aggregate, which is exactly what a columnar engine is built for.
    # -----------------------------------------------------------------------
    "olap_revenue_concentration": """
        WITH advertisers AS (
            SELECT seller_id, SUM(spend_idr) AS spend
            FROM fact_campaign
            GROUP BY ALL
            HAVING SUM(spend_idr) > 0
        ),
        ranked AS (
            SELECT seller_id,
                   spend,
                   ROW_NUMBER() OVER (ORDER BY spend DESC, seller_id) AS rn,
                   COUNT(*) OVER () AS n,
                   SUM(spend) OVER (ORDER BY spend DESC, seller_id
                                    ROWS UNBOUNDED PRECEDING) AS cum_spend,
                   SUM(spend) OVER () AS total_spend
            FROM advertisers
        )
        SELECT CAST(CEIL(rn * 20.0 / n) AS INTEGER) * 5 AS advertiser_pct,
               COUNT(*) AS advertisers,
               SUM(spend) AS spend,
               ROUND(100.0 * MAX(cum_spend) / MAX(total_spend), 2) AS cum_revenue_pct
        FROM ranked
        GROUP BY ALL
        ORDER BY advertiser_pct
    """,

    # -----------------------------------------------------------------------
    # 5. Distribution of organic demand per category, split by whether the
    #    seller advertises.
    #
    # The product's whole premise is that plenty of non-advertisers are not
    # weaker than advertisers — they are simply unsold-to. A median-vs-median
    # comparison per category either supports that or kills it. `quantile_cont`
    # with a FILTER clause does it in one pass; SQLite has no percentile at all.
    # -----------------------------------------------------------------------
    "olap_traction_percentiles": """
        WITH per_category AS (
            SELECT primary_category AS category,
                   quantile_cont(total_views, 0.50) FILTER (WHERE has_ads = 1)
                       AS advertiser_median
            FROM seller_scores
            GROUP BY ALL
        )
        SELECT s.primary_category AS category,
               COUNT(*) AS sellers,
               ROUND(quantile_cont(s.total_views, 0.10), 0) AS p10,
               ROUND(quantile_cont(s.total_views, 0.25), 0) AS p25,
               ROUND(quantile_cont(s.total_views, 0.50), 0) AS p50,
               ROUND(quantile_cont(s.total_views, 0.75), 0) AS p75,
               ROUND(quantile_cont(s.total_views, 0.90), 0) AS p90,
               ROUND(quantile_cont(s.total_views, 0.50) FILTER (WHERE s.has_ads = 1), 0)
                   AS median_advertiser,
               ROUND(quantile_cont(s.total_views, 0.50) FILTER (WHERE s.has_ads = 0), 0)
                   AS median_non_advertiser,
               COUNT(*) FILTER (WHERE s.has_ads = 0) AS non_advertisers,
               -- The headline: non-advertisers already out-performing the
               -- typical *paying* seller in their own category. These are the
               -- accounts the queue exists to surface.
               COUNT(*) FILTER (
                   WHERE s.has_ads = 0 AND s.total_views > p.advertiser_median
               ) AS non_advertisers_above_median,
               ROUND(SUM(s.monthly_spend_headroom) FILTER (
                   WHERE s.has_ads = 0 AND s.total_views > p.advertiser_median
               ), 0) AS headroom_above_median
        FROM seller_scores s
        JOIN per_category p ON p.category = s.primary_category
        GROUP BY ALL
        ORDER BY p50 DESC
    """,

    # -----------------------------------------------------------------------
    # 6. Did outreach land on sellers who had demand *at the time of the call*?
    #
    # The scores are computed as of today, so grading past outreach against them
    # is hindsight. This reconstructs each seller's trailing 28-day traction on
    # every date, then uses an ASOF JOIN to attach the value in force on the day
    # the rep actually called — the correct point-in-time join, and one SQLite
    # cannot express.
    #
    # If conversion climbs with pre-call traction, the model is ranking on a
    # signal the sales floor has already been rewarded for, historically.
    # -----------------------------------------------------------------------
    "olap_conversion_by_traction": """
        WITH daily AS (
            SELECT l.seller_id, m.date, SUM(m.views) AS views
            FROM fact_listing_metrics m
            JOIN dim_listing l USING (listing_id)
            GROUP BY ALL
        ),
        rolling AS (
            SELECT seller_id,
                   date,
                   SUM(views) OVER (
                       PARTITION BY seller_id ORDER BY date
                       RANGE BETWEEN INTERVAL 27 DAYS PRECEDING AND CURRENT ROW
                   ) AS views_28d
            FROM daily
        ),
        at_call AS (
            SELECT a.activity_id,
                   a.outcome,
                   COALESCE(t.views_28d, 0) AS views_at_call
            FROM fact_activity a
            ASOF LEFT JOIN rolling t
              ON a.seller_id = t.seller_id
             AND a.activity_date >= t.date
        ),
        bucketed AS (
            -- activity_id is a tiebreaker, not decoration: hundreds of calls
            -- landed on sellers with the same trailing views, and NTILE splits
            -- ties arbitrarily, so without it two builds of the same data
            -- produce different quintile boundaries.
            SELECT *, NTILE(5) OVER (ORDER BY views_at_call, activity_id) AS quintile
            FROM at_call
        )
        SELECT quintile,
               COUNT(*) AS activities,
               MIN(views_at_call) AS views_floor,
               MAX(views_at_call) AS views_ceiling,
               ROUND(AVG(views_at_call), 0) AS avg_views_at_call,
               COUNT(*) FILTER (WHERE outcome = 'converted') AS conversions,
               ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'converted') / COUNT(*), 2)
                   AS conversion_rate_pct,
               ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'no_response') / COUNT(*), 2)
                   AS no_response_pct
        FROM bucketed
        GROUP BY ALL
        ORDER BY quintile
    """,
}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_queries(con: Any, names: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """Run the catalog and return `{name: {columns, rows, elapsed_ms}}`."""
    selected = list(names) if names is not None else list(QUERIES)
    results: dict[str, dict[str, Any]] = {}
    for name in selected:
        started = time.perf_counter()
        cur = con.execute(QUERIES[name])
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        results[name] = {
            "columns": columns,
            "rows": rows,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    return results


def _materialize(conn: sqlite3.Connection, table: str, columns: list[str], rows: list[tuple]) -> None:
    """Replace a SQLite table with a result set. Everything lands as-is; the
    values are already plain SQL scalars coming out of DuckDB."""
    quoted = ", ".join('"' + c + '"' for c in columns)
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE TABLE {table} ({quoted})")
    if rows:
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {table} VALUES ({placeholders})",
            [tuple(_to_sqlite(v) for v in row) for row in rows],
        )


def _to_sqlite(value: Any) -> Any:
    """DuckDB hands back `date`/`Decimal` objects that sqlite3 cannot bind."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    if isinstance(value, (int, float, str, bytes)) or value is None:
        return value
    return float(value) if hasattr(value, "__float__") else str(value)


def materialize(
    sqlite_conn: sqlite3.Connection,
    raw_dir: Path = RAW_DIR,
    olap_path: Path = OLAP_DB_PATH,
) -> dict[str, Any]:
    """Build the warehouse, run the catalog, and write the results into SQLite.

    Returns a build report. Raises ImportError if DuckDB is not installed —
    callers that want the build to survive without it should check
    `is_available()` first.
    """
    if not is_available():
        raise ImportError(
            "duckdb is not installed. Install it with `pip install -r requirements-dev.txt`."
        )

    started = time.perf_counter()
    con = build_warehouse(raw_dir, olap_path, sqlite_conn=sqlite_conn)
    try:
        fact_rows = con.execute("SELECT COUNT(*) FROM fact_listing_metrics").fetchone()[0]
        results = run_queries(con)
        for name, result in results.items():
            _materialize(sqlite_conn, name, result["columns"], result["rows"])
    finally:
        con.close()

    sqlite_conn.commit()
    return {
        "engine": "duckdb",
        "duckdb_version": duckdb_version(),
        "fact_rows_scanned": fact_rows,
        "warehouse": str(olap_path),
        "warehouse_mb": round(olap_path.stat().st_size / 1_048_576, 1),
        "tables": {name: len(r["rows"]) for name, r in results.items()},
        "query_ms": {name: r["elapsed_ms"] for name, r in results.items()},
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def missing_tables(conn: sqlite3.Connection) -> list[str]:
    """Which `olap_*` tables a database is missing — used by the API to give a
    useful 503 instead of an opaque `no such table`."""
    present = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'olap_%'"
        ).fetchall()
    }
    return [t for t in OLAP_TABLES if t not in present]


def main() -> None:
    import argparse

    from .config import DB_PATH

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database to write results into")
    parser.add_argument("--raw", default=str(RAW_DIR), help="directory holding the 5 CSVs")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        report = materialize(conn, Path(args.raw))
    finally:
        conn.close()

    print(f"DuckDB {report['duckdb_version']} · {report['fact_rows_scanned']:,} fact rows")
    for name, rows in report["tables"].items():
        print(f"  {name:<30} {rows:>5,} rows  ({report['query_ms'][name]:>6.1f} ms)")
    print(f"\nWarehouse: {report['warehouse']} ({report['warehouse_mb']} MB)")
    print(f"Total: {report['total_ms']:.0f} ms")


if __name__ == "__main__":
    main()
