"""Tests for the scoring model's invariants.

These assert the *properties* the methodology promises rather than pinning
exact numbers, so re-generating the dataset with a different seed doesn't
break the suite while a genuine regression still does.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from olxads.config import RAW_DIR, TIER_LABELS
from olxads.scoring import (
    build_revenue_model,
    composite_score,
    load_tables,
    resolve_as_of,
    sales_gap_from_state,
    score_sellers,
    tier_for_score,
)


@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    tables = load_tables(RAW_DIR)
    return score_sellers(tables, resolve_as_of(tables))


# ---------------------------------------------------------------------------
# Composite score: the conjunction property
# ---------------------------------------------------------------------------

def test_zero_traction_cannot_become_an_opportunity():
    """Neglect alone must never manufacture a lead out of a seller with no demand."""
    score = composite_score(
        marketplace_score=0.0, advertising_gap_score=100.0,
        seller_score=100.0, sales_gap_score=100.0,
    )
    assert score == 0.0


def test_dampeners_reduce_but_never_erase():
    """A fully monetised, fully covered account is dampened, not zeroed."""
    ideal = composite_score(100.0, 100.0, 100.0, 100.0)
    worst = composite_score(100.0, 0.0, 0.0, 0.0)
    assert ideal == pytest.approx(100.0)
    assert 0 < worst < ideal
    # floors are 0.30 * 0.25 * 0.40 = 0.03 -> 3.0 on a 100-point base
    assert worst == pytest.approx(3.0, abs=0.05)


def test_score_is_monotonic_in_every_pillar():
    base = composite_score(50, 50, 50, 50)
    assert composite_score(60, 50, 50, 50) > base
    assert composite_score(50, 60, 50, 50) > base
    assert composite_score(50, 50, 60, 50) > base
    assert composite_score(50, 50, 50, 60) > base


@pytest.mark.parametrize(
    "score,expected",
    [(0, "Low"), (19.9, "Low"), (20, "Cool"), (44.9, "Cool"),
     (45, "Warm"), (69.9, "Warm"), (70, "Hot"), (100, "Hot")],
)
def test_tier_boundaries(score, expected):
    assert tier_for_score(score) == expected


# ---------------------------------------------------------------------------
# Sales-coverage gap rule
# ---------------------------------------------------------------------------

def test_never_contacted_is_maximum_gap():
    assert sales_gap_from_state(0, None, None, False, None) == 100.0


def test_won_and_declined_accounts_are_deprioritised():
    won = sales_gap_from_state(3, "closed_won", "converted", False, 10)
    lost = sales_gap_from_state(3, "closed_lost", "not_interested", False, 10)
    assert won < lost < 20


def test_open_follow_up_suppresses_the_account():
    """An account already being worked shouldn't be re-flagged to another rep."""
    assert sales_gap_from_state(2, "qualified", "interested", True, 5) == 10.0


def test_stalled_accounts_resurface_over_time():
    """Gap grows as days/1.8, floored at 10 and capped at 100 (reached at 180d)."""
    fresh = sales_gap_from_state(2, "qualified", "interested", False, 10)
    stale = sales_gap_from_state(2, "qualified", "interested", False, 120)
    ancient = sales_gap_from_state(2, "qualified", "interested", False, 400)
    assert fresh == 10.0            # floor: a touch last week is not overdue
    assert stale == pytest.approx(66.7, abs=0.1)
    assert ancient == 100.0         # ceiling
    assert fresh < stale < ancient


# ---------------------------------------------------------------------------
# Revenue model
# ---------------------------------------------------------------------------

def test_headroom_is_never_negative(scored):
    assert (scored["monthly_spend_headroom"] >= 0).all()


def test_expected_value_never_exceeds_headroom(scored):
    """Risk adjustment can only shrink the number."""
    assert (scored["expected_monthly_value"] <= scored["monthly_spend_headroom"] + 1e-6).all()


def test_win_probability_is_a_probability(scored):
    assert scored["win_probability"].between(0, 1).all()


def test_every_seller_gets_a_benchmark_with_a_stated_basis(scored):
    assert scored["benchmark_monthly_spend"].notna().all()
    assert scored["benchmark_basis"].isin(
        ["category + traction band", "category", "marketplace-wide"]
    ).all()


def test_benchmark_falls_back_when_comparables_are_thin():
    """A category with too few advertisers must not produce a cell-level estimate."""
    df = pd.DataFrame({
        "seller_id": [f"S{i}" for i in range(6)],
        "primary_category": ["Vehicles"] * 6,
        "traction_band": [1, 1, 2, 2, 3, 3],
        "has_ads": [True, True, False, False, False, False],
        "observed_monthly_spend": [1_000_000.0, 2_000_000.0, 0.0, 0.0, 0.0, 0.0],
        "seller_type": ["dealer"] * 6,
        "account_tier": ["premium"] * 6,
        "touch_count": [1, 1, 0, 0, 0, 0],
        "ever_converted": [False] * 6,
    })
    out = build_revenue_model(df, pd.DataFrame())
    # only 2 advertisers total, so no (category, band) cell reaches MIN_COMPARABLES
    assert (out["benchmark_basis"] != "category + traction band").all()


# ---------------------------------------------------------------------------
# Full pipeline on the real dataset
# ---------------------------------------------------------------------------

def test_every_seller_is_scored_exactly_once(scored):
    tables = load_tables(RAW_DIR)
    assert len(scored) == len(tables["sellers"])
    assert scored["seller_id"].is_unique


def test_scores_and_tiers_are_in_range(scored):
    assert scored["opportunity_score"].between(0, 100).all()
    assert scored["priority_tier"].isin(TIER_LABELS).all()
    for pillar in ["marketplace_score", "advertising_gap_score", "seller_score", "sales_gap_score"]:
        assert scored[pillar].between(0, 100).all(), pillar


def test_tier_matches_score(scored):
    recomputed = scored["opportunity_score"].apply(tier_for_score)
    assert (recomputed == scored["priority_tier"]).all()


def test_ranking_is_ordered_by_score(scored):
    assert scored["opportunity_score"].is_monotonic_decreasing


def test_never_advertised_sellers_get_the_maximum_advertising_gap(scored):
    never = scored[~scored["has_ads"]]
    assert (never["advertising_gap_score"] == 100).all()
    # existing advertisers are capped below that, keeping the two groups distinct
    assert (scored[scored["has_ads"]]["advertising_gap_score"] <= 60).all()


def test_the_opportunity_segment_exists(scored):
    """The product's core claim: high-traction, unmonetised, uncontacted accounts."""
    segment = scored[
        (scored["marketplace_score"] >= 75)
        & (~scored["has_ads"])
        & (scored["touch_count"] == 0)
    ]
    assert len(segment) > 0
    assert (segment["priority_tier"].isin(["Hot", "Warm"])).mean() > 0.5


def test_playbook_is_populated(scored):
    assert scored["recommended_product_label"].notna().all()
    assert scored["next_best_action"].notna().all()
    assert scored["reason"].str.len().gt(10).all()
    assert scored[scored["priority_tier"] == "Hot"]["talking_points"].str.len().gt(0).all()


def test_uncontacted_sellers_are_told_to_be_contacted_first(scored):
    uncontacted = scored[scored["touch_count"] == 0]
    assert (uncontacted["next_best_action"] == "First outreach").all()


def test_as_of_date_is_the_latest_observation():
    tables = load_tables(RAW_DIR)
    as_of = resolve_as_of(tables)
    assert isinstance(as_of, dt.date)
    assert as_of >= tables["metrics"]["date"].max().date()


def test_scoring_is_deterministic():
    """Same inputs, same outputs — no hidden randomness in the model."""
    tables = load_tables(RAW_DIR)
    as_of = resolve_as_of(tables)
    a = score_sellers(tables, as_of)
    b = score_sellers(tables, as_of)
    np.testing.assert_array_equal(a["seller_id"].to_numpy(), b["seller_id"].to_numpy())
    np.testing.assert_allclose(
        a["opportunity_score"].to_numpy(), b["opportunity_score"].to_numpy()
    )
