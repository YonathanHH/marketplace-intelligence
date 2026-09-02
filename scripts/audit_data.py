"""
OLX Ads Intelligence — synthetic data leakage & determinism audit.

Checks that "opportunity"-adjacent signals (organic traction, ad spend,
sales contact) are correlated the way a real business would expect, but are
NOT perfectly reconstructable from a closed-form combination of other columns.
Run after scripts/generate_data.py. See docs/DATA_MODEL.md, "Data quality &
leakage audit" section, for what each check is guarding against and why.

Usage:
    python scripts/audit_data.py [--dir data/raw]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def ols_r2(y: np.ndarray, X: pd.DataFrame) -> float:
    """R^2 of an OLS fit of y on X (X may mix numeric and categorical columns)."""
    Xd = pd.get_dummies(X, drop_first=True).astype(float)
    Xd.insert(0, "intercept", 1.0)
    Xm = Xd.to_numpy()
    beta, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    y_hat = Xm @ beta
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/raw")
    args = parser.parse_args()
    d = Path(args.dir)

    sellers = pd.read_csv(d / "sellers.csv", parse_dates=["registration_date", "last_active_date"])
    listings = pd.read_csv(d / "listings.csv", parse_dates=["created_date", "sold_or_expired_date"])
    metrics = pd.read_csv(d / "listing_metrics.csv", parse_dates=["date"])
    campaigns = pd.read_csv(d / "ad_campaigns.csv", parse_dates=["start_date", "end_date"])
    activities = pd.read_csv(d / "sales_activities.csv", parse_dates=["activity_date"])

    print("=" * 78)
    print("1. Is per-listing traction a deterministic function of stored columns?")
    print("=" * 78)
    listing_attrs = listings[["listing_id", "seller_id", "category", "is_featured", "photo_count", "condition"]]
    m = metrics.merge(listing_attrs, on="listing_id")
    listing_views = (
        m.groupby("listing_id")
        .agg(total_views=("views", "sum"))
        .reset_index()
        .merge(listing_attrs, on="listing_id")
        .merge(sellers[["seller_id", "account_tier", "rating_avg", "seller_type"]], on="seller_id")
    )
    listing_views["rating_avg"] = listing_views["rating_avg"].fillna(listing_views["rating_avg"].median())

    y = np.log1p(listing_views["total_views"].to_numpy())
    X = listing_views[["category", "is_featured", "photo_count", "condition", "account_tier", "rating_avg", "seller_type"]]
    r2 = ols_r2(y, X)
    print(f"R^2 of log(total_views) ~ category + featured + photos + condition + tier + rating + type: {r2:.3f}")
    print("  Target: comfortably below 1.0 (0.15-0.6-ish). If this is >0.9, traction is basically")
    print("  a formula on stored columns and there's nothing left for a model to discover.")

    print()
    print("=" * 78)
    print("2. Is advertiser status a deterministic function of account_tier alone?")
    print("=" * 78)
    adv_sellers = set(campaigns["seller_id"])
    sellers["is_advertiser"] = sellers["seller_id"].isin(adv_sellers)
    crosstab = pd.crosstab(sellers["account_tier"], sellers["is_advertiser"], normalize="index")
    print(crosstab.round(3).to_string())
    print("  Target: tier should raise the ad rate monotonically, but no cell at 0% or 100% —")
    print("  i.e. some free-tier sellers advertise and some premium sellers don't.")

    print()
    print("=" * 78)
    print("3. Is sales contact driven directly by true organic traction (the leak to avoid)?")
    print("=" * 78)
    traction = listing_views.groupby("seller_id")["total_views"].sum().reindex(sellers["seller_id"]).fillna(0)
    contacted = sellers["seller_id"].isin(set(activities["seller_id"]))
    corr = np.corrcoef(traction.to_numpy(), contacted.to_numpy().astype(float))[0, 1]
    print(f"Pearson correlation(true traction, was_contacted): {corr:.3f}")
    print("  Target: weak/moderate (well under ~0.5), not a clean step function. Contact should")
    print("  come from tier/type/listing-count-proxy/territory, only loosely tracking real traction.")

    print()
    print("=" * 78)
    print("4. Does the opportunity segment still exist (signal preserved, not erased)?")
    print("=" * 78)
    opp = listing_views.groupby("seller_id")["total_views"].sum()
    opp = opp.reindex(sellers["seller_id"]).fillna(0)
    opp_uncovered = opp[~opp.index.isin(adv_sellers) & ~opp.index.isin(set(activities["seller_id"]))]
    threshold = opp[opp > 0].quantile(0.75)
    high_opp = opp_uncovered[opp_uncovered >= threshold]
    print(f"Sellers with top-quartile traction, zero ad spend, zero sales contact: {len(high_opp)} "
          f"({len(high_opp) / len(sellers):.1%} of all sellers)")
    print("Top 5 by traction (the leads an opportunity model should surface):")
    print(high_opp.sort_values(ascending=False).head(5).to_string())

    print()
    print("=" * 78)
    print("5. Ad campaign spend -> impressions: sub-linear (diminishing returns), not flat-rate?")
    print("=" * 78)
    log_spend = np.log(campaigns["spend_idr"].clip(lower=1))
    log_impr = np.log(campaigns["impressions"].clip(lower=1))
    slope = np.polyfit(log_spend, log_impr, 1)[0]
    print(f"Elasticity of impressions w.r.t. spend (log-log slope): {slope:.3f}")
    print("  Target: below 1.0 — each extra rupiah buys fewer marginal impressions than the last.")


if __name__ == "__main__":
    main()
