#!/usr/bin/env python
"""Build the DuckDB warehouse and (optionally) benchmark it against SQLite.

    python scripts/build_olap.py              # build the warehouse + refresh olap_* tables
    python scripts/build_olap.py --benchmark  # ...and time the same query on both engines

The benchmark exists to keep the second engine honest. Adding a database is a
real cost — another dependency, another artefact, another thing to explain — so
the justification should be a measurement, not an assertion. It runs the demand
decay analysis (a full scan of the 286k-row metric fact joined to listing age,
with a window function over each category) on SQLite and on DuckDB and reports
both wall times and whether the two agree row-for-row.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from olxads import olap  # noqa: E402
from olxads.config import DB_PATH, OLAP_DB_PATH, RAW_DIR  # noqa: E402

# The same analysis as olap.QUERIES["olap_listing_decay"], expressed in the
# SQLite dialect: no `date_diff`, no `first_value` over a grouped set without a
# second pass, so it needs a self-join to normalise each curve.
SQLITE_DECAY = """
WITH aged AS (
    SELECT l.category,
           CAST((julianday(m.date) - julianday(l.created_date)) / 7 AS INTEGER) AS week_since_post,
           m.listing_id,
           m.views,
           m.chats_started + m.phone_reveals AS leads
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
SELECT b.category,
       b.week_since_post,
       b.listings,
       ROUND(b.avg_daily_views, 2) AS avg_daily_views,
       ROUND(b.avg_daily_leads, 3) AS avg_daily_leads,
       ROUND(100.0 * b.avg_daily_views / NULLIF(z.avg_daily_views, 0), 1) AS retention_index
FROM by_week b
JOIN by_week z ON z.category = b.category AND z.week_since_post = 0
ORDER BY b.category, b.week_since_post
"""


def time_it(fn) -> tuple[float, list]:
    started = time.perf_counter()
    rows = fn()
    return (time.perf_counter() - started) * 1000, rows


def benchmark(db_path: Path, olap_path: Path) -> None:
    import duckdb

    conn = sqlite3.connect(db_path)
    try:
        has_raw = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='listing_metrics'"
        ).fetchone()
        if not has_raw:
            print(
                "SQLite side skipped: this database has no raw listing_metrics table.\n"
                "(That is exactly the point — the deploy artefact drops it, and the\n"
                " decay analysis is only possible because DuckDB computed it first.)"
            )
            return
        sqlite_ms, sqlite_rows = time_it(lambda: conn.execute(SQLITE_DECAY).fetchall())
    finally:
        conn.close()

    duck = duckdb.connect(str(olap_path), read_only=True)
    try:
        duck_ms, duck_rows = time_it(
            lambda: duck.execute(olap.QUERIES["olap_listing_decay"]).fetchall()
        )
    finally:
        duck.close()

    print(f"\n{'':<10}{'engine':<12}{'rows':>8}{'wall time':>14}")
    print(f"{'':<10}{'-' * 34}")
    print(f"{'':<10}{'sqlite':<12}{len(sqlite_rows):>8}{sqlite_ms:>11.1f} ms")
    print(f"{'':<10}{'duckdb':<12}{len(duck_rows):>8}{duck_ms:>11.1f} ms")
    if duck_ms > 0:
        print(f"\n{'':<10}DuckDB is {sqlite_ms / duck_ms:.1f}x faster on the same analysis.")

    # Same numbers, or the speed is worthless.
    normalized = [tuple(round(v, 3) if isinstance(v, float) else v for v in r) for r in sqlite_rows]
    duck_norm = [tuple(round(v, 3) if isinstance(v, float) else v for v in r) for r in duck_rows]
    print(f"{'':<10}Results identical: {normalized == duck_norm}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database to write results into")
    parser.add_argument("--raw", default=str(RAW_DIR), help="directory holding the 5 CSVs")
    parser.add_argument("--benchmark", action="store_true", help="time DuckDB against SQLite afterwards")
    args = parser.parse_args()

    if not olap.is_available():
        raise SystemExit(
            "duckdb is not installed.\n  pip install -r requirements-dev.txt"
        )

    conn = sqlite3.connect(args.db)
    try:
        report = olap.materialize(conn, Path(args.raw), OLAP_DB_PATH)
    finally:
        conn.close()

    print(f"DuckDB {report['duckdb_version']} - {report['fact_rows_scanned']:,} fact rows scanned")
    for table, rows in report["tables"].items():
        print(f"  {table:<30} {rows:>5,} rows  ({report['query_ms'][table]:>6.1f} ms)")
    print(f"\nWarehouse: {report['warehouse']} ({report['warehouse_mb']} MB)")

    if args.benchmark:
        benchmark(Path(args.db), OLAP_DB_PATH)


if __name__ == "__main__":
    main()
