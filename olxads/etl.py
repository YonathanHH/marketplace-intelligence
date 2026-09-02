"""Build the application database from the generated CSVs.

Pipeline:
    CSV (data/raw)
      -> schema/schema.sql tables, validated column-by-column
      -> derived `seller_scores` table (opportunity + revenue + playbook)
      -> indexes + a `build_metadata` row

Run via `python -m olxads.etl` or `python run.py --rebuild`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pandas as pd

from .config import DB_PATH, PROCESSED_DIR, RAW_DIR, RAW_TABLES, SCHEMA_PATH
from .scoring import load_tables, resolve_as_of, score_sellers

BOOL_COLUMNS = {
    "sellers": ["is_verified", "phone_verified"],
    "listings": ["is_featured"],
}

DATE_COLUMNS = {
    "sellers": ["registration_date", "last_active_date"],
    "listings": ["created_date", "sold_or_expired_date"],
    "listing_metrics": ["date"],
    "ad_campaigns": ["start_date", "end_date"],
    "sales_activities": ["activity_date", "next_follow_up_date"],
}


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _normalize(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Coerce CSV dtypes into what SQLite expects (0/1 bools, ISO date strings)."""
    out = df.copy()
    for col in BOOL_COLUMNS.get(table, []):
        if col in out.columns:
            out[col] = out[col].astype(bool).astype(int)
    for col in DATE_COLUMNS.get(table, []):
        if col in out.columns:
            parsed = pd.to_datetime(out[col], errors="coerce")
            out[col] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)
    return out


def load_raw_tables(conn: sqlite3.Connection, raw_dir: Path) -> dict[str, int]:
    """Create the schema and load each CSV, validating columns match the DDL."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    counts: dict[str, int] = {}
    for table in RAW_TABLES:
        csv_path = raw_dir / f"{table}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Missing {csv_path}. Run `python scripts/generate_data.py` first."
            )
        df = pd.read_csv(csv_path)

        expected = set(_table_columns(conn, table))
        actual = set(df.columns)
        if expected != actual:
            raise ValueError(
                f"Column mismatch for '{table}'.\n"
                f"  In schema but not CSV: {sorted(expected - actual)}\n"
                f"  In CSV but not schema: {sorted(actual - expected)}"
            )

        df = _normalize(df, table)
        df.to_sql(table, conn, if_exists="append", index=False)
        counts[table] = len(df)
    return counts


def build_seller_scores(conn: sqlite3.Connection, raw_dir: Path) -> tuple[int, dt.date]:
    """Score every seller and persist the result as a queryable table."""
    tables = load_tables(raw_dir)
    as_of = resolve_as_of(tables)
    scores = score_sellers(tables, as_of)

    persisted = scores.copy()
    persisted["as_of_date"] = pd.to_datetime(persisted["as_of_date"]).dt.strftime("%Y-%m-%d")
    for col in ["registration_date", "last_contact_date", "next_follow_up_date", "last_campaign_end"]:
        if col in persisted.columns:
            parsed = pd.to_datetime(persisted[col], errors="coerce")
            persisted[col] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)
    for col in persisted.columns:
        if persisted[col].dtype == bool:
            persisted[col] = persisted[col].astype(int)

    # `rank` is deliberately NOT stored: logging an activity rescores a single
    # seller, which would leave a persisted rank stale and full of gaps. It is
    # derived live by the view below instead.
    persisted = persisted.drop(columns=["rank"], errors="ignore")
    persisted.to_sql("seller_scores", conn, if_exists="replace", index=False)

    conn.execute("DROP VIEW IF EXISTS seller_scores_ranked")
    conn.execute(
        """
        CREATE VIEW seller_scores_ranked AS
        SELECT *,
               ROW_NUMBER() OVER (ORDER BY opportunity_score DESC, seller_id ASC) AS rank
        FROM seller_scores
        """
    )
    return len(persisted), as_of


def build_aggregates(conn: sqlite3.Connection) -> dict[str, int]:
    """Pre-aggregate `listing_metrics` into the shapes the product actually reads.

    Nothing in the API needs a raw metric row — every query is a roll-up by
    listing, by day, or by seller-day. Materialising those three shapes means
    request-time queries scan thousands of rows instead of ~286k, and it lets a
    deployment build drop the raw table entirely (54 MB of the 59 MB database)
    without changing a single number the product reports.
    """
    statements = {
        # One row per listing: totals over its whole life.
        "listing_totals": """
            CREATE TABLE listing_totals AS
            SELECT listing_id,
                   SUM(impressions)      AS impressions,
                   SUM(views)            AS views,
                   SUM(clicks)           AS clicks,
                   SUM(chats_started)    AS chats_started,
                   SUM(phone_reveals)    AS phone_reveals,
                   SUM(favorites_added)  AS favorites_added
            FROM listing_metrics GROUP BY listing_id
        """,
        # One row per calendar day, marketplace-wide.
        "marketplace_daily": """
            CREATE TABLE marketplace_daily AS
            SELECT date,
                   SUM(impressions)      AS impressions,
                   SUM(views)            AS views,
                   SUM(clicks)           AS clicks,
                   SUM(chats_started)    AS chats_started,
                   SUM(phone_reveals)    AS phone_reveals,
                   SUM(favorites_added)  AS favorites_added
            FROM listing_metrics GROUP BY date
        """,
        # One row per seller per day: powers the traction sparkline in Seller 360.
        "seller_daily_traction": """
            CREATE TABLE seller_daily_traction AS
            SELECT l.seller_id,
                   m.date,
                   SUM(m.views)  AS views,
                   SUM(m.clicks) AS clicks,
                   SUM(m.chats_started + m.phone_reveals) AS leads
            FROM listing_metrics m
            JOIN listings l ON l.listing_id = m.listing_id
            GROUP BY l.seller_id, m.date
        """,
    }

    counts: dict[str, int] = {}
    for table, sql in statements.items():
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(sql)
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    conn.execute("CREATE UNIQUE INDEX idx_listing_totals ON listing_totals(listing_id)")
    conn.execute("CREATE UNIQUE INDEX idx_marketplace_daily ON marketplace_daily(date)")
    conn.execute("CREATE INDEX idx_seller_traction ON seller_daily_traction(seller_id, date)")
    return counts


def drop_raw_metrics(conn: sqlite3.Connection) -> None:
    """Deployment builds ship the aggregates only.

    Safe because `build_aggregates` has already derived everything the API
    reads. Local builds keep the raw table so the generator, the audit script
    and the scoring pipeline can still be re-run against it.
    """
    conn.execute("DROP TABLE IF EXISTS listing_metrics")
    conn.commit()
    conn.execute("VACUUM")


def create_indexes(conn: sqlite3.Connection) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_scores_opportunity ON seller_scores(opportunity_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_scores_tier ON seller_scores(priority_tier)",
        "CREATE INDEX IF NOT EXISTS idx_scores_category ON seller_scores(primary_category)",
        "CREATE INDEX IF NOT EXISTS idx_scores_province ON seller_scores(province)",
        "CREATE INDEX IF NOT EXISTS idx_scores_seller ON seller_scores(seller_id)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_listing_date ON listing_metrics(listing_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_activities_date ON sales_activities(activity_date)",
        "CREATE INDEX IF NOT EXISTS idx_campaigns_start ON ad_campaigns(start_date)",
    ]
    for stmt in statements:
        conn.execute(stmt)


def write_metadata(conn: sqlite3.Connection, counts: dict[str, int], as_of: dt.date) -> None:
    conn.execute("DROP TABLE IF EXISTS build_metadata")
    conn.execute(
        "CREATE TABLE build_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    meta = {
        "as_of_date": as_of.isoformat(),
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "row_counts": json.dumps(counts),
    }
    conn.executemany(
        "INSERT INTO build_metadata (key, value) VALUES (?, ?)", list(meta.items())
    )


def build_database(
    raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH, *, deploy: bool = False
) -> dict:
    """Rebuild the database from scratch. Destructive and idempotent by design.

    `deploy=True` produces the slim artefact that ships to a serverless host:
    identical query results, minus the raw metrics table the API never reads.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        print("Loading raw tables...")
        counts = load_raw_tables(conn, raw_dir)
        for table, n in counts.items():
            print(f"  {table:<22} {n:>8,} rows")

        print("Scoring sellers...")
        n_scored, as_of = build_seller_scores(conn, raw_dir)
        print(f"  {'seller_scores':<22} {n_scored:>8,} rows (as of {as_of})")

        print("Building aggregates...")
        for table, n in build_aggregates(conn).items():
            print(f"  {table:<22} {n:>8,} rows")

        print("Creating indexes...")
        create_indexes(conn)
        write_metadata(conn, counts, as_of)
        conn.commit()

        if deploy:
            print("Deploy build: dropping raw listing_metrics...")
            drop_raw_metrics(conn)
    finally:
        conn.close()

    size_mb = db_path.stat().st_size / 1_048_576
    print(f"\nDatabase built: {db_path} ({size_mb:.1f} MB)")
    return {"counts": counts, "as_of": as_of.isoformat(), "path": str(db_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the OLX Ads Intelligence database.")
    parser.add_argument("--raw", default=str(RAW_DIR), help="directory holding the 5 CSVs")
    parser.add_argument("--db", default=str(DB_PATH), help="output SQLite path")
    parser.add_argument(
        "--deploy", action="store_true",
        help="build the slim deployment artefact (drops the raw metrics table)",
    )
    args = parser.parse_args()
    build_database(Path(args.raw), Path(args.db), deploy=args.deploy)


if __name__ == "__main__":
    main()
