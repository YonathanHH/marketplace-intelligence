"""Analytics layer — every aggregation the product surfaces.

All queries run against the SQLite database built by `olxads.etl`. Keeping
them here (rather than inline in the API routes) means the same aggregation
can be reused by the API, a notebook, or a test without going through HTTP.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import query, query_one

# ---------------------------------------------------------------------------
# Filter handling for the opportunity queue
# ---------------------------------------------------------------------------

SORTABLE = {
    "opportunity_score": "opportunity_score",
    "expected_monthly_value": "expected_monthly_value",
    "monthly_spend_headroom": "monthly_spend_headroom",
    "marketplace_score": "marketplace_score",
    "total_views": "total_views",
    "seller_score": "seller_score",
    "days_since_last_contact": "days_since_last_contact",
    "seller_name": "seller_name",
}


def _lead_filters(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate query params into a parameterized WHERE clause."""
    clauses: list[str] = []
    binds: dict[str, Any] = {}

    for field, key in [
        ("priority_tier", "tier"),
        ("primary_category", "category"),
        ("province", "province"),
        ("seller_type", "seller_type"),
        ("account_tier", "account_tier"),
        ("next_best_action", "action"),
    ]:
        value = params.get(key)
        if value:
            values = value if isinstance(value, list) else [value]
            names = []
            for i, v in enumerate(values):
                bind = f"{key}_{i}"
                binds[bind] = v
                names.append(f":{bind}")
            clauses.append(f"{field} IN ({', '.join(names)})")

    if params.get("advertiser_status") == "never":
        clauses.append("has_ads = 0")
    elif params.get("advertiser_status") == "active":
        clauses.append("has_ads = 1")

    if params.get("contact_status") == "uncontacted":
        clauses.append("touch_count = 0")
    elif params.get("contact_status") == "contacted":
        clauses.append("touch_count > 0")

    if params.get("min_score") is not None:
        binds["min_score"] = params["min_score"]
        clauses.append("opportunity_score >= :min_score")

    if params.get("q"):
        binds["q"] = f"%{params['q']}%"
        clauses.append("(seller_name LIKE :q OR seller_id LIKE :q OR city LIKE :q)")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, binds


def list_leads(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    where, binds = _lead_filters(params)

    sort_key = params.get("sort") or "opportunity_score"
    sort_col = SORTABLE.get(sort_key, "opportunity_score")
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    page = max(1, int(params.get("page", 1)))
    page_size = min(200, max(1, int(params.get("page_size", 25))))
    offset = (page - 1) * page_size

    totals = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(monthly_spend_headroom), 0) AS total_headroom,
               COALESCE(SUM(expected_monthly_value), 0) AS total_expected_value
        FROM seller_scores {where}
        """,
        binds,
    )

    rows = query(
        conn,
        f"""
        SELECT rank, seller_id, seller_name, seller_type, primary_category, city, province,
               account_tier, opportunity_score, priority_tier, marketplace_score,
               advertising_gap_score, seller_score, sales_gap_score,
               total_views, total_chats, listing_count, active_listing_count,
               total_ad_spend, observed_monthly_spend, benchmark_monthly_spend,
               monthly_spend_headroom, expected_monthly_value, win_probability,
               has_ads, touch_count, days_since_last_contact, last_sales_rep,
               recommended_product, recommended_product_label, next_best_action,
               is_verified, rating_avg, response_rate_pct, reason
        FROM seller_scores_ranked
        {where}
        ORDER BY {sort_col} {direction}, seller_id ASC
        LIMIT :limit OFFSET :offset
        """,
        {**binds, "limit": page_size, "offset": offset},
    )

    return {
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total": totals["total"],
        "total_pages": max(1, -(-totals["total"] // page_size)),
        "aggregate": {
            "monthly_headroom": totals["total_headroom"],
            "expected_monthly_value": totals["total_expected_value"],
        },
    }


def filter_options(conn: sqlite3.Connection) -> dict[str, Any]:
    def distinct(col: str) -> list[str]:
        return [
            r[col] for r in query(
                conn, f"SELECT DISTINCT {col} AS {col} FROM seller_scores WHERE {col} IS NOT NULL ORDER BY {col}"
            )
        ]

    return {
        "categories": distinct("primary_category"),
        "provinces": distinct("province"),
        "seller_types": distinct("seller_type"),
        "account_tiers": distinct("account_tier"),
        "tiers": ["Hot", "Warm", "Cool", "Low"],
        "actions": distinct("next_best_action"),
        "sorts": list(SORTABLE.keys()),
    }


# ---------------------------------------------------------------------------
# Executive overview
# ---------------------------------------------------------------------------

def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    kpis = query_one(
        conn,
        """
        SELECT
            COUNT(*)                                               AS total_sellers,
            SUM(CASE WHEN priority_tier = 'Hot' THEN 1 ELSE 0 END) AS hot_leads,
            SUM(CASE WHEN has_ads = 1 THEN 1 ELSE 0 END)           AS advertisers,
            SUM(CASE WHEN touch_count > 0 THEN 1 ELSE 0 END)       AS contacted_sellers,
            SUM(observed_monthly_spend)                            AS current_monthly_revenue,
            SUM(monthly_spend_headroom)                            AS monthly_headroom,
            SUM(expected_monthly_value)                            AS expected_monthly_value,
            SUM(CASE WHEN has_ads = 0 THEN monthly_spend_headroom ELSE 0 END) AS new_logo_headroom,
            SUM(CASE WHEN has_ads = 1 THEN monthly_spend_headroom ELSE 0 END) AS upsell_headroom,
            SUM(CASE WHEN priority_tier IN ('Hot','Warm') AND touch_count = 0
                     THEN monthly_spend_headroom ELSE 0 END)       AS uncovered_priority_headroom,
            SUM(CASE WHEN priority_tier IN ('Hot','Warm') AND touch_count = 0
                     THEN 1 ELSE 0 END)                            AS uncovered_priority_leads,
            AVG(win_probability)                                   AS avg_win_probability
        FROM seller_scores
        """,
    )

    marketplace = query_one(
        conn,
        """
        SELECT (SELECT COUNT(*) FROM listings)                                  AS total_listings,
               (SELECT COUNT(*) FROM listings WHERE status = 'active')          AS active_listings,
               (SELECT COALESCE(SUM(views), 0) FROM marketplace_daily)          AS total_views,
               (SELECT COALESCE(SUM(chats_started + phone_reveals), 0)
                  FROM marketplace_daily)                                       AS total_leads_generated
        """,
    )

    tier_mix = query(
        conn,
        """
        SELECT priority_tier AS tier, COUNT(*) AS sellers,
               COALESCE(SUM(monthly_spend_headroom), 0) AS monthly_headroom,
               COALESCE(SUM(expected_monthly_value), 0) AS expected_monthly_value,
               ROUND(AVG(opportunity_score), 1) AS avg_score
        FROM seller_scores GROUP BY priority_tier
        """,
    )
    order = {"Hot": 0, "Warm": 1, "Cool": 2, "Low": 3}
    tier_mix.sort(key=lambda r: order.get(r["tier"], 9))

    top_leads = query(
        conn,
        """
        SELECT rank, seller_id, seller_name, primary_category, city, province,
               opportunity_score, priority_tier, monthly_spend_headroom,
               expected_monthly_value, recommended_product_label, next_best_action,
               total_views, has_ads, touch_count, reason
        FROM seller_scores_ranked
        ORDER BY opportunity_score DESC, seller_id ASC
        LIMIT 8
        """,
    )

    category_opportunity = query(
        conn,
        """
        SELECT primary_category AS category,
               COUNT(*) AS sellers,
               SUM(CASE WHEN has_ads = 1 THEN 1 ELSE 0 END) AS advertisers,
               COALESCE(SUM(monthly_spend_headroom), 0) AS monthly_headroom,
               COALESCE(SUM(observed_monthly_spend), 0) AS current_revenue,
               ROUND(AVG(opportunity_score), 1) AS avg_score
        FROM seller_scores
        GROUP BY primary_category
        ORDER BY monthly_headroom DESC
        """,
    )

    meta = {r["key"]: r["value"] for r in query(conn, "SELECT key, value FROM build_metadata")}

    total = kpis["total_sellers"] or 1
    kpis["advertiser_penetration"] = round(100.0 * (kpis["advertisers"] or 0) / total, 1)
    kpis["coverage_rate"] = round(100.0 * (kpis["contacted_sellers"] or 0) / total, 1)
    kpis["annual_headroom"] = (kpis["monthly_headroom"] or 0) * 12

    return {
        "kpis": kpis,
        "marketplace": marketplace,
        "tier_mix": tier_mix,
        "top_leads": top_leads,
        "category_opportunity": category_opportunity,
        "as_of": meta.get("as_of_date"),
        "built_at": meta.get("built_at"),
    }


# ---------------------------------------------------------------------------
# Marketplace analytics
# ---------------------------------------------------------------------------

def marketplace_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    trend = query(
        conn,
        """
        SELECT date, impressions, views, clicks,
               (chats_started + phone_reveals) AS leads
        FROM marketplace_daily
        ORDER BY date
        """,
    )

    categories = query(
        conn,
        """
        SELECT l.category,
               COUNT(DISTINCT l.listing_id) AS listings,
               COUNT(DISTINCT l.seller_id)  AS sellers,
               COALESCE(SUM(m.views), 0)    AS views,
               COALESCE(SUM(m.chats_started + m.phone_reveals), 0) AS leads,
               ROUND(AVG(l.price_idr), 0)   AS avg_price
        FROM listings l
        LEFT JOIN listing_totals m ON m.listing_id = l.listing_id
        GROUP BY l.category
        ORDER BY views DESC
        """,
    )

    provinces = query(
        conn,
        """
        SELECT l.province,
               COUNT(DISTINCT l.listing_id) AS listings,
               COUNT(DISTINCT l.seller_id)  AS sellers,
               COALESCE(SUM(m.views), 0)    AS views
        FROM listings l
        LEFT JOIN listing_totals m ON m.listing_id = l.listing_id
        GROUP BY l.province
        ORDER BY views DESC
        """,
    )

    status_mix = query(
        conn,
        "SELECT status, COUNT(*) AS listings FROM listings GROUP BY status ORDER BY listings DESC",
    )

    funnel = query_one(
        conn,
        """
        SELECT COALESCE(SUM(impressions), 0)   AS impressions,
               COALESCE(SUM(views), 0)         AS views,
               COALESCE(SUM(clicks), 0)        AS clicks,
               COALESCE(SUM(chats_started), 0) AS chats,
               COALESCE(SUM(phone_reveals), 0) AS phone_reveals
        FROM marketplace_daily
        """,
    )

    featured_lift = query(
        conn,
        """
        SELECT CASE WHEN l.is_featured = 1 THEN 'Featured' ELSE 'Standard' END AS segment,
               COUNT(DISTINCT l.listing_id) AS listings,
               ROUND(COALESCE(SUM(m.views), 0) * 1.0 / COUNT(DISTINCT l.listing_id), 1) AS views_per_listing,
               ROUND(COALESCE(SUM(m.chats_started + m.phone_reveals), 0) * 1.0
                     / COUNT(DISTINCT l.listing_id), 2) AS leads_per_listing
        FROM listings l
        LEFT JOIN listing_totals m ON m.listing_id = l.listing_id
        GROUP BY l.is_featured
        """,
    )

    return {
        "trend": trend,
        "categories": categories,
        "provinces": provinces,
        "status_mix": status_mix,
        "funnel": funnel,
        "featured_lift": featured_lift,
    }


# ---------------------------------------------------------------------------
# Advertising analytics
# ---------------------------------------------------------------------------

def advertising_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    revenue_trend = query(
        conn,
        """
        SELECT strftime('%Y-%m', start_date) AS month,
               SUM(spend_idr) AS spend,
               COUNT(*) AS campaigns,
               COUNT(DISTINCT seller_id) AS advertisers
        FROM ad_campaigns
        GROUP BY month
        ORDER BY month
        """,
    )

    by_type = query(
        conn,
        """
        SELECT campaign_type,
               COUNT(*) AS campaigns,
               SUM(spend_idr) AS spend,
               SUM(impressions) AS impressions,
               SUM(clicks) AS clicks,
               SUM(conversions) AS conversions,
               ROUND(SUM(clicks) * 100.0 / NULLIF(SUM(impressions), 0), 2) AS ctr_pct,
               ROUND(SUM(spend_idr) * 1.0 / NULLIF(SUM(clicks), 0), 0) AS cpc,
               ROUND(SUM(spend_idr) * 1.0 / NULLIF(SUM(conversions), 0), 0) AS cost_per_conversion,
               ROUND(SUM(conversions) * 100.0 / NULLIF(SUM(clicks), 0), 2) AS conversion_rate
        FROM ad_campaigns
        GROUP BY campaign_type
        ORDER BY spend DESC
        """,
    )

    by_category = query(
        conn,
        """
        SELECT s.primary_category AS category,
               COUNT(DISTINCT c.seller_id) AS advertisers,
               SUM(c.spend_idr) AS spend,
               SUM(c.conversions) AS conversions
        FROM ad_campaigns c
        JOIN sellers s ON s.seller_id = c.seller_id
        GROUP BY s.primary_category
        ORDER BY spend DESC
        """,
    )

    penetration = query(
        conn,
        """
        SELECT account_tier,
               COUNT(*) AS sellers,
               SUM(CASE WHEN has_ads = 1 THEN 1 ELSE 0 END) AS advertisers,
               ROUND(SUM(CASE WHEN has_ads = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS penetration_pct,
               COALESCE(SUM(observed_monthly_spend), 0) AS monthly_revenue,
               COALESCE(SUM(monthly_spend_headroom), 0) AS monthly_headroom
        FROM seller_scores
        GROUP BY account_tier
        """,
    )

    spend_distribution = query(
        conn,
        """
        SELECT CASE
                 WHEN observed_monthly_spend = 0 THEN '0 (never advertised)'
                 WHEN observed_monthly_spend < 250000 THEN '< 250k'
                 WHEN observed_monthly_spend < 750000 THEN '250k - 750k'
                 WHEN observed_monthly_spend < 2000000 THEN '750k - 2M'
                 WHEN observed_monthly_spend < 5000000 THEN '2M - 5M'
                 ELSE '5M+'
               END AS band,
               COUNT(*) AS sellers,
               COALESCE(SUM(observed_monthly_spend), 0) AS monthly_revenue
        FROM seller_scores
        GROUP BY band
        """,
    )
    band_order = ["0 (never advertised)", "< 250k", "250k - 750k", "750k - 2M", "2M - 5M", "5M+"]
    spend_distribution.sort(key=lambda r: band_order.index(r["band"]) if r["band"] in band_order else 99)

    status_mix = query(
        conn,
        "SELECT status, COUNT(*) AS campaigns, SUM(spend_idr) AS spend FROM ad_campaigns GROUP BY status",
    )

    totals = query_one(
        conn,
        """
        SELECT SUM(spend_idr) AS total_spend, SUM(budget_idr) AS total_budget,
               COUNT(*) AS campaigns, COUNT(DISTINCT seller_id) AS advertisers,
               SUM(conversions) AS conversions,
               ROUND(SUM(spend_idr) * 1.0 / NULLIF(SUM(conversions), 0), 0) AS blended_cpa,
               ROUND(SUM(clicks) * 100.0 / NULLIF(SUM(impressions), 0), 2) AS blended_ctr
        FROM ad_campaigns
        """,
    )

    return {
        "totals": totals,
        "revenue_trend": revenue_trend,
        "by_type": by_type,
        "by_category": by_category,
        "penetration": penetration,
        "spend_distribution": spend_distribution,
        "status_mix": status_mix,
    }


# ---------------------------------------------------------------------------
# Sales pipeline analytics
# ---------------------------------------------------------------------------

STAGE_ORDER = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


def pipeline_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    # Current stage per seller = the stage of their most recent activity.
    stage_funnel = query(
        conn,
        """
        WITH latest AS (
            SELECT a.seller_id, a.deal_stage,
                   ROW_NUMBER() OVER (PARTITION BY a.seller_id ORDER BY a.activity_date DESC, a.activity_id DESC) AS rn
            FROM sales_activities a
        )
        SELECT l.deal_stage AS stage, COUNT(*) AS sellers,
               COALESCE(SUM(s.monthly_spend_headroom), 0) AS monthly_headroom
        FROM latest l
        JOIN seller_scores s ON s.seller_id = l.seller_id
        WHERE l.rn = 1
        GROUP BY l.deal_stage
        """,
    )
    stage_funnel.sort(key=lambda r: STAGE_ORDER.index(r["stage"]) if r["stage"] in STAGE_ORDER else 99)

    outcomes = query(
        conn,
        "SELECT outcome, COUNT(*) AS activities FROM sales_activities GROUP BY outcome ORDER BY activities DESC",
    )

    activity_types = query(
        conn,
        """
        SELECT activity_type, COUNT(*) AS activities,
               SUM(CASE WHEN outcome = 'converted' THEN 1 ELSE 0 END) AS conversions
        FROM sales_activities GROUP BY activity_type ORDER BY activities DESC
        """,
    )

    reps = query(
        conn,
        """
        SELECT a.sales_rep,
               COUNT(*) AS activities,
               COUNT(DISTINCT a.seller_id) AS accounts,
               SUM(CASE WHEN a.outcome = 'converted' THEN 1 ELSE 0 END) AS wins,
               ROUND(SUM(CASE WHEN a.outcome = 'converted' THEN 1 ELSE 0 END) * 100.0
                     / COUNT(DISTINCT a.seller_id), 1) AS win_rate_pct,
               COALESCE(SUM(DISTINCT a.potential_deal_value_idr), 0) AS pipeline_value
        FROM sales_activities a
        GROUP BY a.sales_rep
        ORDER BY wins DESC, activities DESC
        """,
    )

    activity_trend = query(
        conn,
        """
        SELECT strftime('%Y-%m', activity_date) AS month,
               COUNT(*) AS activities,
               COUNT(DISTINCT seller_id) AS accounts_touched,
               SUM(CASE WHEN outcome = 'converted' THEN 1 ELSE 0 END) AS wins
        FROM sales_activities
        GROUP BY month ORDER BY month
        """,
    )

    win_rate_by_segment = query(
        conn,
        """
        SELECT seller_type, account_tier,
               COUNT(*) AS contacted,
               ROUND(AVG(win_probability) * 100, 2) AS modeled_win_rate
        FROM seller_scores
        WHERE touch_count > 0
        GROUP BY seller_type, account_tier
        ORDER BY modeled_win_rate DESC
        """,
    )

    totals = query_one(
        conn,
        """
        SELECT COUNT(*) AS activities,
               COUNT(DISTINCT seller_id) AS accounts_touched,
               SUM(CASE WHEN outcome = 'converted' THEN 1 ELSE 0 END) AS wins,
               ROUND(AVG(potential_deal_value_idr), 0) AS avg_deal_value
        FROM sales_activities
        """,
    )

    return {
        "totals": totals,
        "stage_funnel": stage_funnel,
        "outcomes": outcomes,
        "activity_types": activity_types,
        "reps": reps,
        "activity_trend": activity_trend,
        "win_rate_by_segment": win_rate_by_segment,
    }


# ---------------------------------------------------------------------------
# Territory coverage
# ---------------------------------------------------------------------------

def coverage_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    by_province = query(
        conn,
        """
        SELECT province,
               COUNT(*) AS sellers,
               SUM(CASE WHEN touch_count > 0 THEN 1 ELSE 0 END) AS contacted,
               ROUND(SUM(CASE WHEN touch_count > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS coverage_pct,
               SUM(CASE WHEN priority_tier IN ('Hot','Warm') THEN 1 ELSE 0 END) AS priority_leads,
               SUM(CASE WHEN priority_tier IN ('Hot','Warm') AND touch_count = 0 THEN 1 ELSE 0 END) AS uncovered_priority,
               COALESCE(SUM(CASE WHEN touch_count = 0 THEN monthly_spend_headroom ELSE 0 END), 0) AS uncovered_headroom
        FROM seller_scores
        GROUP BY province
        ORDER BY uncovered_headroom DESC
        """,
    )

    by_category = query(
        conn,
        """
        SELECT primary_category AS category,
               COUNT(*) AS sellers,
               SUM(CASE WHEN touch_count > 0 THEN 1 ELSE 0 END) AS contacted,
               ROUND(SUM(CASE WHEN touch_count > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS coverage_pct,
               SUM(CASE WHEN priority_tier IN ('Hot','Warm') AND touch_count = 0 THEN 1 ELSE 0 END) AS uncovered_priority,
               COALESCE(SUM(CASE WHEN touch_count = 0 THEN monthly_spend_headroom ELSE 0 END), 0) AS uncovered_headroom
        FROM seller_scores
        GROUP BY primary_category
        ORDER BY uncovered_headroom DESC
        """,
    )

    # Where coverage effort is going vs. where the value is: contacted sellers
    # split by whether they were actually worth contacting.
    effort_quality = query_one(
        conn,
        """
        SELECT
            SUM(CASE WHEN touch_count > 0 AND priority_tier IN ('Hot','Warm') THEN 1 ELSE 0 END) AS well_targeted,
            SUM(CASE WHEN touch_count > 0 AND priority_tier IN ('Cool','Low') THEN 1 ELSE 0 END) AS low_value_touched,
            SUM(CASE WHEN touch_count = 0 AND priority_tier IN ('Hot','Warm') THEN 1 ELSE 0 END) AS missed_priority,
            SUM(CASE WHEN touch_count = 0 AND priority_tier IN ('Cool','Low') THEN 1 ELSE 0 END) AS correctly_skipped
        FROM seller_scores
        """,
    )

    stale = query(
        conn,
        """
        SELECT seller_id, seller_name, primary_category, province, opportunity_score,
               priority_tier, days_since_last_contact, last_sales_rep, monthly_spend_headroom
        FROM seller_scores
        WHERE touch_count > 0 AND days_since_last_contact > 60
          AND priority_tier IN ('Hot','Warm')
        ORDER BY monthly_spend_headroom DESC
        LIMIT 15
        """,
    )

    return {
        "by_province": by_province,
        "by_category": by_category,
        "effort_quality": effort_quality,
        "stale_priority_accounts": stale,
    }


# ---------------------------------------------------------------------------
# Seller 360
# ---------------------------------------------------------------------------

def seller_detail(conn: sqlite3.Connection, seller_id: str) -> dict[str, Any] | None:
    score = query_one(conn, "SELECT * FROM seller_scores_ranked WHERE seller_id = :sid", {"sid": seller_id})
    if score is None:
        return None

    listings = query(
        conn,
        """
        SELECT l.listing_id, l.title, l.category, l.subcategory, l.price_idr, l.condition,
               l.status, l.created_date, l.is_featured, l.photo_count,
               COALESCE(SUM(m.views), 0) AS views,
               COALESCE(SUM(m.clicks), 0) AS clicks,
               COALESCE(SUM(m.chats_started + m.phone_reveals), 0) AS leads
        FROM listings l
        LEFT JOIN listing_totals m ON m.listing_id = l.listing_id
        WHERE l.seller_id = :sid
        GROUP BY l.listing_id
        ORDER BY views DESC
        LIMIT 50
        """,
        {"sid": seller_id},
    )

    traction_trend = query(
        conn,
        """
        SELECT date, views, clicks, leads
        FROM seller_daily_traction
        WHERE seller_id = :sid
        ORDER BY date
        """,
        {"sid": seller_id},
    )

    campaigns = query(
        conn,
        """
        SELECT campaign_id, campaign_name, campaign_type, start_date, end_date, status,
               budget_idr, spend_idr, impressions, clicks, conversions
        FROM ad_campaigns WHERE seller_id = :sid ORDER BY start_date DESC
        """,
        {"sid": seller_id},
    )

    activities = query(
        conn,
        """
        SELECT activity_id, sales_rep, activity_date, activity_type, channel, outcome,
               deal_stage, potential_deal_value_idr, next_follow_up_date
        FROM sales_activities WHERE seller_id = :sid ORDER BY activity_date DESC
        """,
        {"sid": seller_id},
    )

    # The actual peer set behind the benchmark — makes the revenue estimate
    # auditable in the UI instead of a black-box number.
    comparables = query(
        conn,
        """
        SELECT seller_id, seller_name, observed_monthly_spend, total_views, account_tier
        FROM seller_scores
        WHERE primary_category = :cat AND traction_band = :band
          AND has_ads = 1 AND seller_id != :sid
        ORDER BY observed_monthly_spend DESC
        LIMIT 8
        """,
        {"cat": score["primary_category"], "band": score["traction_band"], "sid": seller_id},
    )

    score["talking_points"] = [p for p in (score.get("talking_points") or "").split(" | ") if p]

    return {
        "seller": score,
        "listings": listings,
        "traction_trend": traction_trend,
        "campaigns": campaigns,
        "activities": activities,
        "comparables": comparables,
    }


# ---------------------------------------------------------------------------
# Deep dive — results of the DuckDB OLAP pass
#
# These tables are computed at build time by `olxads.olap` against a columnar
# warehouse and materialised here, so serving them stays stdlib sqlite3. The
# headline figures are derived in this module rather than in the frontend: they
# are business logic, and the CSV export and any future alerting need the same
# numbers.
# ---------------------------------------------------------------------------

OLAP_TABLES = (
    "olap_listing_decay",
    "olap_demand_weekly",
    "olap_category_momentum",
    "olap_revenue_concentration",
    "olap_traction_percentiles",
    "olap_conversion_by_traction",
)


def olap_available(conn: sqlite3.Connection) -> bool:
    present = {
        r["name"] for r in query(
            conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'olap_%'"
        )
    }
    return all(t in present for t in OLAP_TABLES)


def _weighted(rows: list[dict[str, Any]], value: str, weight: str) -> float | None:
    total = sum((r[weight] or 0) for r in rows)
    if not total:
        return None
    return sum((r[value] or 0) * (r[weight] or 0) for r in rows) / total


def olap_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    decay = query(conn, "SELECT * FROM olap_listing_decay ORDER BY category, week_since_post")
    weekly = query(conn, "SELECT * FROM olap_demand_weekly ORDER BY category, week")
    momentum = query(conn, "SELECT * FROM olap_category_momentum ORDER BY momentum_pct DESC")
    concentration = query(conn, "SELECT * FROM olap_revenue_concentration ORDER BY advertiser_pct")
    percentiles = query(conn, "SELECT * FROM olap_traction_percentiles ORDER BY p50 DESC")
    conversion = query(conn, "SELECT * FROM olap_conversion_by_traction ORDER BY quintile")

    # Decay curve for the marketplace as a whole: the per-category curves are
    # averaged by listing count so a large category is not out-voted by a small one.
    weeks = sorted({r["week_since_post"] for r in decay})
    overall_decay = []
    for week in weeks:
        rows = [r for r in decay if r["week_since_post"] == week]
        overall_decay.append({
            "week_since_post": week,
            "listings": sum(r["listings"] for r in rows),
            "avg_daily_views": round(_weighted(rows, "avg_daily_views", "listings") or 0, 2),
            "avg_daily_leads": round(_weighted(rows, "avg_daily_leads", "listings") or 0, 3),
            "retention_index": round(_weighted(rows, "retention_index", "listings") or 0, 1),
        })

    def retention_at(week: int) -> float | None:
        row = next((r for r in overall_decay if r["week_since_post"] == week), None)
        return row["retention_index"] if row else None

    def cumulative_at(pct: int) -> float | None:
        row = next((r for r in concentration if r["advertiser_pct"] == pct), None)
        return row["cum_revenue_pct"] if row else None

    bottom = conversion[0] if conversion else None
    top = conversion[-1] if conversion else None
    best = max(conversion, key=lambda r: r["conversion_rate_pct"]) if conversion else None

    meta = {r["key"]: r["value"] for r in query(conn, "SELECT key, value FROM build_metadata")}

    return {
        "engine": {
            "name": meta.get("olap_engine") or "unknown",
            "version": meta.get("olap_version") or None,
            "fact_rows": int(meta.get("olap_fact_rows") or 0) or None,
            "build_ms": float(meta.get("olap_build_ms") or 0) or None,
        },
        "listing_decay": decay,
        "listing_decay_overall": overall_decay,
        "demand_weekly": weekly,
        "category_momentum": momentum,
        "revenue_concentration": concentration,
        "traction_percentiles": percentiles,
        "conversion_by_traction": conversion,
        "headlines": {
            "retention_week1": retention_at(1),
            "retention_week3": retention_at(3),
            "top_5pct_revenue_share": cumulative_at(5),
            "top_20pct_revenue_share": cumulative_at(20),
            "underdog_sellers": sum(r["non_advertisers_above_median"] for r in percentiles),
            "underdog_headroom": sum((r["headroom_above_median"] or 0) for r in percentiles),
            "conversion_bottom_quintile": bottom["conversion_rate_pct"] if bottom else None,
            "conversion_top_quintile": top["conversion_rate_pct"] if top else None,
            "conversion_best_quintile": best["quintile"] if best else None,
            "conversion_lift": (
                round(best["conversion_rate_pct"] / bottom["conversion_rate_pct"], 1)
                if best and bottom and bottom["conversion_rate_pct"] else None
            ),
            "fastest_growing": momentum[0]["category"] if momentum else None,
            "fastest_growing_pct": momentum[0]["momentum_pct"] if momentum else None,
        },
    }
