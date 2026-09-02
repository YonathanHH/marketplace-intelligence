"""CLI: score every seller and write a ranked, explained lead list to CSV.

This is a thin wrapper over `olxads.scoring` — the same code path the API and
the nightly database build use, so a CSV exported here can never disagree with
what the product shows. See docs/OPPORTUNITY_SCORING.md for the methodology.

Usage:
    python scripts/score_opportunities.py [--dir data/raw] [--out data/processed] [--top 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from olxads.config import PROCESSED_DIR, RAW_DIR, TIER_LABELS  # noqa: E402
from olxads.scoring import score_from_csv  # noqa: E402

EXPORT_COLUMNS = [
    "rank", "seller_id", "seller_name", "seller_type", "primary_category", "city", "province",
    "account_tier", "opportunity_score", "priority_tier",
    "marketplace_score", "advertising_gap_score", "seller_score", "sales_gap_score",
    "total_views", "total_clicks", "total_chats", "listing_count", "active_listing_count",
    "total_ad_spend", "observed_monthly_spend", "benchmark_monthly_spend", "benchmark_basis",
    "monthly_spend_headroom", "annual_revenue_potential", "win_probability",
    "expected_monthly_value", "has_ads", "campaign_count",
    "is_verified", "rating_avg", "response_rate_pct", "tenure_years",
    "touch_count", "days_since_last_contact", "last_deal_stage", "last_sales_rep",
    "recommended_product_label", "next_best_action", "reason", "talking_points",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Score sellers on advertising opportunity.")
    parser.add_argument("--dir", default=str(RAW_DIR), help="input directory with the 5 CSVs")
    parser.add_argument("--out", default=str(PROCESSED_DIR), help="output directory")
    parser.add_argument("--top", type=int, default=20, help="how many top leads to print")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Scoring sellers...")
    df = score_from_csv(Path(args.dir))

    out_path = out_dir / "opportunity_scores.csv"
    df[EXPORT_COLUMNS].to_csv(out_path, index=False)

    as_of = df["as_of_date"].iloc[0].date()
    print(f"\nScored {len(df):,} sellers as of {as_of}.\n")

    print("Priority tier distribution:")
    counts = df["priority_tier"].value_counts()
    for tier in reversed(TIER_LABELS):
        n = int(counts.get(tier, 0))
        print(f"  {tier:<5} {n:>5,}  ({n / len(df):5.1%})")

    headroom = df["monthly_spend_headroom"].sum()
    expected = df["expected_monthly_value"].sum()
    print(f"\nUntapped monthly revenue:  Rp{headroom:,.0f}")
    print(f"Risk-adjusted pipeline:    Rp{expected:,.0f}")

    print(f"\nTop {args.top} leads:\n")
    for _, row in df.head(args.top).iterrows():
        print(
            f"#{row['rank']:>3}  {row['opportunity_score']:>5.1f}  [{row['priority_tier']:<4}]  "
            f"{row['seller_name']} ({row['seller_id']}, {row['primary_category']}, {row['city']})"
        )
        print(
            f"      Rp{row['monthly_spend_headroom']:,.0f}/mo headroom  |  "
            f"{row['recommended_product_label']}  |  {row['next_best_action']}"
        )
        print(f"      {row['reason']}")

    print(f"\nFull ranked list written to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
