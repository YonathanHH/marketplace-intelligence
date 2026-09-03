"""Shared paths and tunables for the OLX Ads Intelligence platform."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
# Full local build (includes the raw metrics table, ~67 MB).
DB_PATH = PROCESSED_DIR / "olxads.db"
# Slim artefact committed for deployment (~13 MB, aggregates only, same results).
DEPLOY_DB_PATH = PROCESSED_DIR / "olxads-deploy.db"
# Columnar OLAP warehouse. Build-time only: `olxads.olap` computes the deep-dive
# analytics here and materialises the (tiny) results back into SQLite, so the
# serving path never opens it. Kept on disk for ad-hoc analysis.
OLAP_DB_PATH = PROCESSED_DIR / "olxads.duckdb"
SCHEMA_PATH = PROJECT_ROOT / "schema" / "schema.sql"
WEB_DIR = PROJECT_ROOT / "web"

# Serverless hosts give us a read-only filesystem apart from the temp dir.
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

RAW_TABLES = ["sellers", "listings", "listing_metrics", "ad_campaigns", "sales_activities"]

# ---------------------------------------------------------------------------
# Scoring tunables
# ---------------------------------------------------------------------------

TIER_BINS = [0, 20, 45, 70, 100.01]
TIER_LABELS = ["Low", "Cool", "Warm", "Hot"]

# funnel-weighted demand: deeper-intent actions count for more than a passive view
DEMAND_WEIGHTS = {
    "views": 1.0,
    "clicks": 4.0,
    "chats_started": 8.0,
    "phone_reveals": 8.0,
    "favorites_added": 3.0,
}

# multiplicative dampener floors — see docs/OPPORTUNITY_SCORING.md for why the
# pillars multiply rather than sum
ADVERTISING_DAMPENER_FLOOR = 0.30
SALES_DAMPENER_FLOOR = 0.25
READINESS_DAMPENER_FLOOR = 0.40

# ---------------------------------------------------------------------------
# Revenue model tunables
# ---------------------------------------------------------------------------

# minimum comparable advertisers required before a (category, traction band)
# cell is trusted for a spend estimate; below this we fall back up the hierarchy
MIN_COMPARABLES = 5
TRACTION_BANDS = 5
# shrinkage strength when estimating win probability per segment (higher =
# pulled harder toward the global base rate; guards tiny segments)
WIN_RATE_PRIOR_WEIGHT = 20.0

CURRENCY = "IDR"
