"""Pure scoring rules — the single source of truth for how a seller is scored.

**This module deliberately has no third-party imports.** Two callers depend on
that:

* `olxads.scoring` (build time) applies these rules across a whole DataFrame.
* `olxads.actions` (serve time) applies the same rules to one seller after a
  rep logs a call.

Keeping the rules here means the live write path can never drift from the batch
build, and it keeps pandas/numpy (~90 MB) out of the serving runtime entirely —
which is what lets the API deploy as a small serverless function.

Functions accept anything supporting `row["field"]`, so a pandas Series and a
plain sqlite3 row-dict both work.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Tunables (mirrored in config.py, kept here so this module stays import-free)
# ---------------------------------------------------------------------------

TIER_BINS = [0, 20, 45, 70, 100.01]
TIER_LABELS = ["Low", "Cool", "Warm", "Hot"]

ADVERTISING_DAMPENER_FLOOR = 0.30
SALES_DAMPENER_FLOOR = 0.25
READINESS_DAMPENER_FLOOR = 0.40

PRODUCT_LABELS = {
    "featured_listing": "Featured Listing",
    "bump_up": "Bump Up",
    "search_boost": "Search Boost",
    "homepage_banner": "Homepage Banner",
    "category_spotlight": "Category Spotlight",
}

Row = Mapping[str, Any]


def _missing(value: Any) -> bool:
    """True for None or NaN, without needing pandas.

    numpy floats subclass float, so this covers `np.float64('nan')` and
    pandas' NaN alike.
    """
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Pillar 4 and the composite
# ---------------------------------------------------------------------------

def sales_gap_from_state(
    touch_count: int,
    last_deal_stage: str | None,
    last_outcome: str | None,
    has_open_follow_up: bool,
    days_since_last_contact: float | None,
) -> float:
    """Outreach-coverage gap, 0-100. Higher = more overdue for contact."""
    if not touch_count:
        return 100.0
    if last_deal_stage == "closed_won":
        return 5.0
    if last_deal_stage == "closed_lost" or last_outcome == "not_interested":
        return 15.0
    if has_open_follow_up:
        return 10.0  # already being worked - don't double-flag it
    days = 999.0 if _missing(days_since_last_contact) else float(days_since_last_contact)
    return round(_clip(days / 1.8, 10, 100), 1)


def composite_score(
    marketplace_score: float,
    advertising_gap_score: float,
    seller_score: float,
    sales_gap_score: float,
) -> float:
    """Combine the four pillars into the 0-100 opportunity score.

    A conjunction, not a sum: traction is the base and the other pillars apply
    bounded multiplicative dampeners, so neglect alone can never manufacture a
    lead out of a seller with no demand. See docs/OPPORTUNITY_SCORING.md.
    """
    advertising = ADVERTISING_DAMPENER_FLOOR + (1 - ADVERTISING_DAMPENER_FLOOR) * (advertising_gap_score / 100)
    sales = SALES_DAMPENER_FLOOR + (1 - SALES_DAMPENER_FLOOR) * (sales_gap_score / 100)
    readiness = READINESS_DAMPENER_FLOOR + (1 - READINESS_DAMPENER_FLOOR) * (seller_score / 100)
    return round(float(marketplace_score) * advertising * sales * readiness, 1)


def tier_for_score(score: float) -> str:
    for upper, label in zip(TIER_BINS[1:], TIER_LABELS):
        if score < upper:
            return label
    return TIER_LABELS[-1]


# ---------------------------------------------------------------------------
# Playbook
# ---------------------------------------------------------------------------

def recommend_product(row: Row) -> str:
    """Pick the ad product that fits this seller's size and category."""
    listings = row["active_listing_count"]
    big_ticket = row["primary_category"] in ("Property", "Vehicles")
    if listings >= 30 and row["seller_type"] in ("dealer", "enterprise"):
        return "category_spotlight" if big_ticket else "homepage_banner"
    if listings >= 10:
        return "search_boost"
    if listings >= 3:
        return "featured_listing"
    return "bump_up"


def next_best_action(row: Row) -> str:
    if row["touch_count"] == 0:
        return "First outreach"
    if row["last_deal_stage"] == "closed_won":
        return "Account management"
    if row["last_deal_stage"] == "closed_lost" or row["last_outcome"] == "not_interested":
        return "Nurture"
    if row["has_open_follow_up"]:
        return "Follow-up booked"
    days = row["days_since_last_contact"]
    if not _missing(days) and days > 60:
        return "Re-engage (stalled)"
    return "Continue working"


def build_talking_points(row: Row) -> list[str]:
    """Evidence-backed bullets a rep can actually open a call with."""
    points: list[str] = []

    if row["total_views"] > 0:
        points.append(
            f"Their {int(row['active_listing_count'])} active listings pulled "
            f"{int(row['total_views']):,} views and {int(row['total_chats']):,} buyer chats "
            f"in the last 30 days - entirely unpaid reach."
        )
    if row["marketplace_score"] >= 70:
        points.append(
            f"That puts them in the top {max(1, round(100 - row['marketplace_score']))}% of "
            f"{row['primary_category']} sellers by organic demand."
        )
    if row["lead_quality_ratio"] > 0:
        points.append(
            f"{row['lead_quality_ratio']:.1f}% of their views turn into a direct buyer contact - "
            f"demand is converting, so more visibility compounds."
        )
    if not row["has_ads"] and row["benchmark_monthly_spend"] > 0:
        points.append(
            f"Comparable {row['primary_category']} sellers at this traction level invest about "
            f"Rp{int(row['benchmark_monthly_spend']):,}/month "
            f"({int(row['benchmark_comparables'])} comparables, basis: {row['benchmark_basis']})."
        )
    elif row["has_ads"] and row["monthly_spend_headroom"] > 0:
        points.append(
            f"They already spend Rp{int(row['observed_monthly_spend']):,}/month - "
            f"about Rp{int(row['monthly_spend_headroom']):,}/month below comparable sellers."
        )
    if row["response_rate_pct"] >= 80:
        points.append(
            f"Operationally ready: {row['response_rate_pct']:.0f}% response rate, "
            f"so extra leads won't go unanswered."
        )
    days = row["days_since_last_contact"]
    if not _missing(days) and days > 60:
        points.append(
            f"Last touched {int(days)} days ago by {row['last_sales_rep']} with no follow-up booked."
        )
    return points[:4]


def build_reason(row: Row) -> str:
    """One-line 'why this lead' summary, assembled from whatever is notable."""
    parts: list[str] = []

    if row["marketplace_score"] >= 80:
        parts.append(
            f"top {max(1, round(100 - row['marketplace_score']))}% organic traction in "
            f"{row['primary_category']} ({int(row['total_views']):,} views across "
            f"{int(row['listing_count'])} listings)"
        )
    elif row["marketplace_score"] >= 55:
        parts.append(
            f"above-average traction in {row['primary_category']} ({int(row['total_views']):,} views)"
        )
    elif row["marketplace_score"] < 25:
        parts.append(f"below-average organic traction in {row['primary_category']}")

    if not row["has_ads"]:
        parts.append("zero ad spend to date")
    elif row["advertising_gap_score"] >= 30:
        parts.append(f"only Rp{int(row['total_ad_spend']):,} spent so far - room to grow")
    else:
        parts.append("already a well-monetized advertiser")

    readiness: list[str] = []
    if row["is_verified"]:
        readiness.append("verified")
    rating = row["rating_avg"]
    if not _missing(rating) and rating >= 4.5:
        readiness.append(f"{rating:.1f}/5 rating")
    if row["response_rate_pct"] >= 80:
        readiness.append(f"{row['response_rate_pct']:.0f}% response rate")
    if readiness:
        parts.append(", ".join(readiness))
    elif row["seller_score"] < 40:
        parts.append("unverified / low engagement - vet before prioritizing")

    if row["touch_count"] == 0:
        parts.append("no sales contact on record")
    elif row["has_open_follow_up"]:
        parts.append(f"already being worked by {row['last_sales_rep']}")
    elif row["last_deal_stage"] == "closed_lost" or row["last_outcome"] == "not_interested":
        parts.append("previously declined - low priority for re-outreach")
    else:
        days = row["days_since_last_contact"]
        if not _missing(days):
            parts.append(f"last touched {int(days)}d ago, no follow-up scheduled")

    return "; ".join(parts).capitalize() + "."
