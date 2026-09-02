"""Opportunity scoring, revenue potential, and sales playbook generation.

Consumes only the five public tables (sellers / listings / listing_metrics /
ad_campaigns / sales_activities) — the same data a real analyst would have.

Three layers:

1. **Pillar scores** — four 0-100 sub-scores, one per platform pillar.
2. **Composite `opportunity_score`** — traction as the base, with the other
   pillars applying bounded multiplicative dampeners (see
   docs/OPPORTUNITY_SCORING.md for why this is a conjunction, not a sum).
3. **Commercial layer** — what the lead is actually worth: a comparable-based
   estimate of monthly ad spend headroom, a segment win probability, the
   risk-adjusted expected value, and a rep-facing playbook.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    ADVERTISING_DAMPENER_FLOOR,
    DEMAND_WEIGHTS,
    MIN_COMPARABLES,
    READINESS_DAMPENER_FLOOR,
    SALES_DAMPENER_FLOOR,
    TIER_BINS,
    TIER_LABELS,
    TRACTION_BANDS,
    WIN_RATE_PRIOR_WEIGHT,
)

# The scoring rules themselves live in `olxads.rules`, which has no third-party
# imports. This module is the *build-time* pipeline: it applies those rules
# across the whole population with pandas. Re-exported here so existing callers
# (and the tests) keep one obvious import site.
from .rules import (  # noqa: F401
    build_reason,
    build_talking_points,
    composite_score,
    next_best_action,
    recommend_product,
    sales_gap_from_state,
    tier_for_score,
    PRODUCT_LABELS,
)


def _clip(x, lo, hi):
    return np.minimum(np.maximum(x, lo), hi)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "sellers": pd.read_csv(data_dir / "sellers.csv", parse_dates=["registration_date", "last_active_date"]),
        "listings": pd.read_csv(data_dir / "listings.csv", parse_dates=["created_date", "sold_or_expired_date"]),
        "metrics": pd.read_csv(data_dir / "listing_metrics.csv", parse_dates=["date"]),
        "campaigns": pd.read_csv(data_dir / "ad_campaigns.csv", parse_dates=["start_date", "end_date"]),
        "activities": pd.read_csv(
            data_dir / "sales_activities.csv", parse_dates=["activity_date", "next_follow_up_date"]
        ),
    }


def resolve_as_of(tables: dict[str, pd.DataFrame]) -> dt.date:
    """The dataset's 'today' — the latest observation across the fact tables."""
    candidates = [
        tables["metrics"]["date"].max(),
        tables["activities"]["activity_date"].max(),
        tables["sellers"]["last_active_date"].max(),
        tables["campaigns"]["end_date"].max(),
    ]
    return max(c for c in candidates if pd.notna(c)).date()


# ---------------------------------------------------------------------------
# 1. Marketplace pillar — organic demand
# ---------------------------------------------------------------------------

def build_marketplace_features(
    sellers: pd.DataFrame, listings: pd.DataFrame, metrics: pd.DataFrame
) -> pd.DataFrame:
    listing_agg = (
        metrics.groupby("listing_id")
        .agg(
            total_views=("views", "sum"),
            total_clicks=("clicks", "sum"),
            total_chats=("chats_started", "sum"),
            total_phone_reveals=("phone_reveals", "sum"),
            total_favorites=("favorites_added", "sum"),
            total_impressions=("impressions", "sum"),
        )
        .reset_index()
    )

    listing_full = listings.merge(listing_agg, on="listing_id", how="left")
    metric_cols = [
        "total_views", "total_clicks", "total_chats",
        "total_phone_reveals", "total_favorites", "total_impressions",
    ]
    listing_full[metric_cols] = listing_full[metric_cols].fillna(0)

    listing_full["demand_raw"] = sum(
        listing_full[f"total_{src}"] * weight
        for src, weight in [
            ("views", DEMAND_WEIGHTS["views"]),
            ("clicks", DEMAND_WEIGHTS["clicks"]),
            ("chats", DEMAND_WEIGHTS["chats_started"]),
            ("phone_reveals", DEMAND_WEIGHTS["phone_reveals"]),
            ("favorites", DEMAND_WEIGHTS["favorites_added"]),
        ]
    )

    seller_agg = (
        listing_full.groupby("seller_id")
        .agg(
            listing_count=("listing_id", "count"),
            active_listing_count=("status", lambda s: int((s == "active").sum())),
            sold_listing_count=("status", lambda s: int((s == "sold").sum())),
            total_views=("total_views", "sum"),
            total_impressions=("total_impressions", "sum"),
            total_clicks=("total_clicks", "sum"),
            total_chats=("total_chats", "sum"),
            total_phone_reveals=("total_phone_reveals", "sum"),
            demand_raw=("demand_raw", "sum"),
            avg_price_idr=("price_idr", "mean"),
        )
        .reset_index()
    )

    out = sellers[["seller_id", "primary_category"]].merge(seller_agg, on="seller_id", how="left")
    fill_cols = [
        "listing_count", "active_listing_count", "sold_listing_count", "total_views",
        "total_impressions", "total_clicks", "total_chats", "total_phone_reveals",
        "demand_raw", "avg_price_idr",
    ]
    out[fill_cols] = out[fill_cols].fillna(0)

    # Category-normalized percentile: a seller is compared only against peers in
    # their own category, so naturally low-traffic categories aren't uniformly
    # buried under high-traffic ones.
    out["marketplace_score"] = (
        out.groupby("primary_category")["demand_raw"].rank(pct=True, method="average") * 100
    ).round(1)

    # Traction band (1-5) within category — the cohort key for revenue comparables.
    out["traction_band"] = (
        out.groupby("primary_category")["demand_raw"]
        .rank(pct=True, method="average")
        .mul(TRACTION_BANDS)
        .apply(np.ceil)
        .clip(1, TRACTION_BANDS)
        .astype(int)
    )

    out["lead_quality_ratio"] = np.where(
        out["total_views"] > 0,
        ((out["total_chats"] + out["total_phone_reveals"]) / out["total_views"] * 100).round(2),
        0.0,
    )

    return out.drop(columns=["primary_category"])


# ---------------------------------------------------------------------------
# 2. Advertising pillar — under-monetization
# ---------------------------------------------------------------------------

def build_advertising_features(
    sellers: pd.DataFrame, campaigns: pd.DataFrame, as_of: dt.date
) -> pd.DataFrame:
    camp_agg = (
        campaigns.groupby("seller_id")
        .agg(
            total_ad_spend=("spend_idr", "sum"),
            total_ad_budget=("budget_idr", "sum"),
            campaign_count=("campaign_id", "count"),
            total_ad_impressions=("impressions", "sum"),
            total_ad_clicks=("clicks", "sum"),
            total_conversions=("conversions", "sum"),
            first_campaign_start=("start_date", "min"),
            last_campaign_end=("end_date", "max"),
        )
        .reset_index()
    )

    out = sellers[["seller_id", "primary_category"]].merge(camp_agg, on="seller_id", how="left")
    num_cols = [
        "total_ad_spend", "total_ad_budget", "campaign_count",
        "total_ad_impressions", "total_ad_clicks", "total_conversions",
    ]
    out[num_cols] = out[num_cols].fillna(0)
    out["has_ads"] = out["total_ad_spend"] > 0

    # Monthly spend run-rate: total spend spread over the months since they
    # first advertised (floored at one month so a single recent campaign isn't
    # annualized into a fantasy number).
    months_advertising = (
        (pd.Timestamp(as_of) - out["first_campaign_start"]).dt.days / 30.44
    ).clip(lower=1.0)
    out["observed_monthly_spend"] = np.where(
        out["has_ads"], (out["total_ad_spend"] / months_advertising).round(0), 0.0
    )
    out["days_since_last_campaign"] = (
        (pd.Timestamp(as_of) - out["last_campaign_end"]).dt.days
    )
    out["ad_cost_per_conversion"] = np.where(
        out["total_conversions"] > 0, (out["total_ad_spend"] / out["total_conversions"]).round(0), np.nan
    )

    # Among sellers who DO advertise, rank spend within category. Never having
    # advertised takes the ceiling (100) directly rather than merely ranking
    # last, keeping "never advertised" and "advertised a little" distinct.
    advertisers = out.loc[out["has_ads"], ["seller_id", "primary_category", "total_ad_spend"]].copy()
    advertisers["spend_pctile"] = advertisers.groupby("primary_category")["total_ad_spend"].rank(pct=True)
    out = out.merge(advertisers[["seller_id", "spend_pctile"]], on="seller_id", how="left")

    out["advertising_gap_score"] = np.where(
        out["has_ads"], (60 * (1 - out["spend_pctile"].fillna(0))).round(1), 100.0
    )

    return out.drop(columns=["primary_category", "spend_pctile", "first_campaign_start"])


# ---------------------------------------------------------------------------
# 3. Seller pillar — readiness / trustworthiness
# ---------------------------------------------------------------------------

def build_seller_features(sellers: pd.DataFrame, as_of: dt.date) -> pd.DataFrame:
    out = sellers.copy()
    out["tenure_years"] = ((pd.Timestamp(as_of) - out["registration_date"]).dt.days / 365.25).round(2)
    out["days_since_active"] = (pd.Timestamp(as_of) - out["last_active_date"]).dt.days

    rating_filled = out["rating_avg"].fillna(out["rating_avg"].median())

    out["seller_score"] = (
        25 * out["is_verified"].astype(float)
        + 10 * out["phone_verified"].astype(float)
        + 25 * _clip(rating_filled / 5.0, 0, 1)
        + 25 * _clip(out["response_rate_pct"] / 100.0, 0, 1)
        + 15 * _clip(out["tenure_years"] / 2.0, 0, 1)
    ).round(1)

    return out[[
        "seller_id", "seller_name", "seller_type", "primary_category", "city", "province",
        "registration_date", "account_tier", "is_verified", "phone_verified", "rating_avg",
        "rating_count", "response_rate_pct", "response_time_hours", "tenure_years",
        "days_since_active", "seller_score",
    ]]


# ---------------------------------------------------------------------------
# 4. Sales-activity pillar — outreach coverage gap
# ---------------------------------------------------------------------------

def build_sales_features(
    sellers: pd.DataFrame, activities: pd.DataFrame, as_of: dt.date
) -> pd.DataFrame:
    base = sellers[["seller_id"]].copy()

    if len(activities) == 0:
        out = base.assign(
            touch_count=0, last_contact_date=pd.NaT, last_deal_stage=None,
            last_outcome=None, last_sales_rep=None, has_open_follow_up=False,
            next_follow_up_date=pd.NaT, ever_converted=False,
        )
    else:
        ordered = activities.sort_values("activity_date")
        last_touch = ordered.groupby("seller_id").tail(1).set_index("seller_id")
        touch_count = activities.groupby("seller_id").size().rename("touch_count")
        ever_converted = (
            activities.assign(
                _won=(activities["outcome"] == "converted") | (activities["deal_stage"] == "closed_won")
            )
            .groupby("seller_id")["_won"].max().rename("ever_converted")
        )

        out = (
            base.merge(touch_count, left_on="seller_id", right_index=True, how="left")
            .merge(ever_converted, left_on="seller_id", right_index=True, how="left")
            .merge(
                last_touch[[
                    "activity_date", "deal_stage", "outcome", "sales_rep", "next_follow_up_date",
                ]].rename(columns={
                    "activity_date": "last_contact_date", "deal_stage": "last_deal_stage",
                    "outcome": "last_outcome", "sales_rep": "last_sales_rep",
                }),
                left_on="seller_id", right_index=True, how="left",
            )
        )
        out["touch_count"] = out["touch_count"].fillna(0).astype(int)
        out["ever_converted"] = out["ever_converted"].fillna(False).astype(bool)
        out["has_open_follow_up"] = (
            out["next_follow_up_date"].notna() & (out["next_follow_up_date"] >= pd.Timestamp(as_of))
        )

    out["days_since_last_contact"] = (
        (pd.Timestamp(as_of) - out["last_contact_date"]).dt.days
    )

    out["sales_gap_score"] = out.apply(
        lambda r: sales_gap_from_state(
            r["touch_count"], r["last_deal_stage"], r["last_outcome"],
            bool(r["has_open_follow_up"]), r["days_since_last_contact"],
        ),
        axis=1,
    ).round(1)
    return out


# ---------------------------------------------------------------------------
# 5. Commercial layer — what is this lead actually worth?
# ---------------------------------------------------------------------------

def build_revenue_model(df: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    """Comparable-based ad-spend potential and a risk-adjusted expected value.

    Rather than inventing a spend number, we ask what sellers *just like this
    one* already pay: the median monthly spend of actual advertisers in the
    same category and traction band. If that cohort is too thin to trust
    (< MIN_COMPARABLES), the estimate falls back up a hierarchy —
    category median, then global median — so every seller gets an estimate
    with a stated basis rather than a silent NaN.
    """
    out = df.copy()
    advertisers = out[out["has_ads"] & (out["observed_monthly_spend"] > 0)]

    cell = (
        advertisers.groupby(["primary_category", "traction_band"])["observed_monthly_spend"]
        .agg(["median", "size"])
        .rename(columns={"median": "cell_spend", "size": "cell_n"})
    )
    by_category = (
        advertisers.groupby("primary_category")["observed_monthly_spend"]
        .agg(["median", "size"])
        .rename(columns={"median": "cat_spend", "size": "cat_n"})
    )
    global_median = float(advertisers["observed_monthly_spend"].median()) if len(advertisers) else 0.0

    out = out.merge(cell, left_on=["primary_category", "traction_band"], right_index=True, how="left")
    out = out.merge(by_category, left_on="primary_category", right_index=True, how="left")

    use_cell = out["cell_n"].fillna(0) >= MIN_COMPARABLES
    use_cat = (~use_cell) & (out["cat_n"].fillna(0) >= MIN_COMPARABLES)

    out["benchmark_monthly_spend"] = np.select(
        [use_cell, use_cat], [out["cell_spend"], out["cat_spend"]], default=global_median
    ).round(0)
    out["benchmark_basis"] = np.select(
        [use_cell, use_cat],
        ["category + traction band", "category"],
        default="marketplace-wide",
    )
    out["benchmark_comparables"] = np.select(
        [use_cell, use_cat], [out["cell_n"].fillna(0), out["cat_n"].fillna(0)], default=len(advertisers)
    ).astype(int)

    # Headroom is what they *aren't* spending yet relative to their cohort.
    out["monthly_spend_headroom"] = (
        (out["benchmark_monthly_spend"] - out["observed_monthly_spend"]).clip(lower=0).round(0)
    )

    # Win probability by segment, shrunk toward the global base rate so a
    # 2-seller segment can't post a 100% win rate.
    contacted = out[out["touch_count"] > 0]
    global_win = float(contacted["ever_converted"].mean()) if len(contacted) else 0.15
    seg = (
        contacted.groupby(["seller_type", "account_tier"])["ever_converted"]
        .agg(["sum", "size"]).rename(columns={"sum": "seg_wins", "size": "seg_n"})
    )
    out = out.merge(seg, left_on=["seller_type", "account_tier"], right_index=True, how="left")
    out[["seg_wins", "seg_n"]] = out[["seg_wins", "seg_n"]].fillna(0)
    out["win_probability"] = (
        (out["seg_wins"] + WIN_RATE_PRIOR_WEIGHT * global_win)
        / (out["seg_n"] + WIN_RATE_PRIOR_WEIGHT)
    ).round(4)

    out["expected_monthly_value"] = (out["monthly_spend_headroom"] * out["win_probability"]).round(0)
    out["annual_revenue_potential"] = (out["monthly_spend_headroom"] * 12).round(0)

    return out.drop(columns=["cell_spend", "cell_n", "cat_spend", "cat_n", "seg_wins", "seg_n"])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def score_sellers(tables: dict[str, pd.DataFrame], as_of: dt.date | None = None) -> pd.DataFrame:
    """Full pipeline: four pillars -> composite score -> revenue -> playbook."""
    sellers, listings = tables["sellers"], tables["listings"]
    metrics, campaigns, activities = tables["metrics"], tables["campaigns"], tables["activities"]
    as_of = as_of or resolve_as_of(tables)

    df = (
        build_seller_features(sellers, as_of)
        .merge(build_marketplace_features(sellers, listings, metrics), on="seller_id", how="left")
        .merge(build_advertising_features(sellers, campaigns, as_of), on="seller_id", how="left")
        .merge(build_sales_features(sellers, activities, as_of), on="seller_id", how="left")
    )

    # Vectorized form of `composite_score` (same formula, applied to the whole
    # population at once). The scalar version in the write path must match this.
    advertising_dampener = ADVERTISING_DAMPENER_FLOOR + (1 - ADVERTISING_DAMPENER_FLOOR) * (
        df["advertising_gap_score"] / 100
    )
    sales_dampener = SALES_DAMPENER_FLOOR + (1 - SALES_DAMPENER_FLOOR) * (df["sales_gap_score"] / 100)
    readiness_dampener = READINESS_DAMPENER_FLOOR + (1 - READINESS_DAMPENER_FLOOR) * (
        df["seller_score"] / 100
    )

    df["opportunity_score"] = (
        df["marketplace_score"] * advertising_dampener * sales_dampener * readiness_dampener
    ).round(1)
    df["priority_tier"] = pd.cut(
        df["opportunity_score"], bins=TIER_BINS, labels=TIER_LABELS, right=False
    ).astype(str)

    df = build_revenue_model(df, activities)

    df["recommended_product"] = df.apply(recommend_product, axis=1)
    df["recommended_product_label"] = df["recommended_product"].map(PRODUCT_LABELS)
    df["next_best_action"] = df.apply(next_best_action, axis=1)
    df["reason"] = df.apply(build_reason, axis=1)
    df["talking_points"] = df.apply(lambda r: " | ".join(build_talking_points(r)), axis=1)

    df = df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    df["as_of_date"] = pd.Timestamp(as_of)
    return df


def score_from_csv(data_dir: Path, as_of: dt.date | None = None) -> pd.DataFrame:
    tables = load_tables(data_dir)
    return score_sellers(tables, as_of)
