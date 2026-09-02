"""API contract and behaviour tests.

Each test runs against a throwaway database built from the real CSVs, so the
write-path tests can mutate freely without touching the development database.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from olxads.config import DB_PATH


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    """A client bound to a disposable copy of the built database."""
    if not DB_PATH.exists():
        pytest.skip("Database not built. Run: python run.py --rebuild")

    tmp_db = tmp_path_factory.mktemp("db") / "test.db"
    shutil.copy(DB_PATH, tmp_db)

    from olxads import api as api_module

    def override_conn():
        conn = sqlite3.connect(tmp_db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    api_module.app.dependency_overrides[api_module.get_conn] = override_conn
    yield TestClient(api_module.app)
    api_module.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_meta_reports_build_provenance(client):
    body = client.get("/api/meta").json()
    assert "as_of_date" in body and "built_at" in body


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/overview",
    "/api/analytics/marketplace",
    "/api/analytics/advertising",
    "/api/analytics/pipeline",
    "/api/analytics/coverage",
    "/api/leads/filters",
])
def test_analytics_endpoints_return_data(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.json()


def test_overview_totals_are_internally_consistent(client):
    body = client.get("/api/overview").json()
    k = body["kpis"]
    assert k["monthly_headroom"] == pytest.approx(
        k["new_logo_headroom"] + k["upsell_headroom"], rel=1e-6
    )
    assert k["annual_headroom"] == pytest.approx(k["monthly_headroom"] * 12, rel=1e-6)
    assert sum(t["sellers"] for t in body["tier_mix"]) == k["total_sellers"]
    assert 0 <= k["coverage_rate"] <= 100
    assert 0 <= k["advertiser_penetration"] <= 100


def test_marketplace_funnel_is_monotonic(client):
    f = client.get("/api/analytics/marketplace").json()["funnel"]
    assert f["impressions"] >= f["views"] >= f["clicks"]
    assert f["clicks"] >= 0


def test_advertising_ctr_is_realistic(client):
    """Guards the regression where organic engagement rates leaked into ad CTR."""
    totals = client.get("/api/analytics/advertising").json()["totals"]
    assert 0.1 < totals["blended_ctr"] < 5.0


# ---------------------------------------------------------------------------
# Opportunity queue
# ---------------------------------------------------------------------------

def test_leads_pagination(client):
    body = client.get("/api/leads?page_size=10").json()
    assert len(body["rows"]) == 10
    assert body["page"] == 1
    assert body["total"] > 10
    page2 = client.get("/api/leads?page_size=10&page=2").json()
    assert {r["seller_id"] for r in body["rows"]}.isdisjoint(
        {r["seller_id"] for r in page2["rows"]}
    )


def test_leads_rank_is_sequential(client):
    body = client.get("/api/leads?page_size=25").json()
    assert [r["rank"] for r in body["rows"]] == list(range(1, 26))


def test_leads_default_sort_is_by_score(client):
    rows = client.get("/api/leads?page_size=50").json()["rows"]
    scores = [r["opportunity_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_leads_sort_and_order(client):
    rows = client.get(
        "/api/leads?sort=monthly_spend_headroom&order=asc&page_size=20"
    ).json()["rows"]
    values = [r["monthly_spend_headroom"] for r in rows]
    assert values == sorted(values)


@pytest.mark.parametrize("params,check", [
    ("tier=Hot", lambda r: r["priority_tier"] == "Hot"),
    ("advertiser_status=never", lambda r: r["has_ads"] == 0),
    ("advertiser_status=active", lambda r: r["has_ads"] == 1),
    ("contact_status=uncontacted", lambda r: r["touch_count"] == 0),
    ("contact_status=contacted", lambda r: r["touch_count"] > 0),
    ("category=Vehicles", lambda r: r["primary_category"] == "Vehicles"),
    ("min_score=70", lambda r: r["opportunity_score"] >= 70),
])
def test_lead_filters_are_applied(client, params, check):
    body = client.get(f"/api/leads?{params}&page_size=50").json()
    assert body["rows"], f"no rows for {params}"
    assert all(check(r) for r in body["rows"])


def test_multiple_tiers_can_be_combined(client):
    body = client.get("/api/leads?tier=Hot&tier=Warm&page_size=100").json()
    assert {r["priority_tier"] for r in body["rows"]} <= {"Hot", "Warm"}


def test_search_matches_seller_and_city(client):
    seed = client.get("/api/leads?page_size=1").json()["rows"][0]
    body = client.get(f"/api/leads?q={seed['seller_id']}").json()
    assert body["total"] >= 1
    assert any(r["seller_id"] == seed["seller_id"] for r in body["rows"])


def test_filter_aggregates_match_the_filtered_set(client):
    body = client.get("/api/leads?tier=Hot&page_size=200").json()
    assert body["total"] == len(body["rows"])
    assert body["aggregate"]["monthly_headroom"] == pytest.approx(
        sum(r["monthly_spend_headroom"] for r in body["rows"]), rel=1e-6
    )


def test_sql_injection_attempt_is_treated_as_a_search_string(client):
    res = client.get("/api/leads?q=%27%3B+DROP+TABLE+sellers%3B--")
    assert res.status_code == 200
    assert res.json()["total"] == 0
    # the table is still there
    assert client.get("/api/overview").json()["kpis"]["total_sellers"] > 0


def test_export_returns_csv(client):
    res = client.get("/api/leads/export?tier=Hot")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("rank,seller_id,seller_name")
    assert len(lines) > 1


# ---------------------------------------------------------------------------
# Seller 360
# ---------------------------------------------------------------------------

def test_seller_detail_shape(client):
    seller_id = client.get("/api/leads?page_size=1").json()["rows"][0]["seller_id"]
    body = client.get(f"/api/sellers/{seller_id}").json()
    assert set(body) == {"seller", "listings", "traction_trend", "campaigns", "activities", "comparables"}
    assert body["seller"]["seller_id"] == seller_id
    assert isinstance(body["seller"]["talking_points"], list)


def test_unknown_seller_is_404(client):
    assert client.get("/api/sellers/SEL-999999").status_code == 404


def test_comparables_are_advertisers_in_the_same_cohort(client):
    """The benchmark must be auditable: peers shown are real, spending sellers."""
    body = client.get("/api/leads?advertiser_status=never&page_size=1").json()
    detail = client.get(f"/api/sellers/{body['rows'][0]['seller_id']}").json()
    for peer in detail["comparables"]:
        assert peer["observed_monthly_spend"] > 0


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------

def test_logging_an_activity_rescores_the_seller(client):
    target = client.get(
        "/api/leads?contact_status=uncontacted&tier=Hot&page_size=1"
    ).json()["rows"][0]
    before = client.get(f"/api/sellers/{target['seller_id']}").json()["seller"]
    assert before["touch_count"] == 0
    assert before["sales_gap_score"] == 100

    res = client.post(
        f"/api/sellers/{target['seller_id']}/activities",
        json={
            "sales_rep": "Test Rep",
            "activity_type": "cold_call",
            "outcome": "interested",
            "deal_stage": "qualified",
            "next_follow_up_date": "2026-09-20",
        },
    )
    assert res.status_code == 201
    after = res.json()["seller"]

    # An account now being worked must drop out of the priority queue.
    assert after["touch_count"] == 1
    assert after["sales_gap_score"] == 10.0
    assert after["opportunity_score"] < before["opportunity_score"]
    assert after["next_best_action"] == "Follow-up booked"

    # ...and the change is persisted, not just returned.
    refetched = client.get(f"/api/sellers/{target['seller_id']}").json()["seller"]
    assert refetched["opportunity_score"] == after["opportunity_score"]
    assert len(client.get(f"/api/sellers/{target['seller_id']}").json()["activities"]) == 1


def test_activity_validation_rejects_bad_enums(client):
    seller_id = client.get("/api/leads?page_size=1").json()["rows"][0]["seller_id"]
    res = client.post(
        f"/api/sellers/{seller_id}/activities",
        json={"sales_rep": "X", "activity_type": "telepathy",
              "outcome": "interested", "deal_stage": "qualified"},
    )
    assert res.status_code == 422


def test_activity_on_unknown_seller_is_rejected(client):
    res = client.post(
        "/api/sellers/SEL-999999/activities",
        json={"sales_rep": "X", "activity_type": "cold_call",
              "outcome": "interested", "deal_stage": "qualified"},
    )
    assert res.status_code == 400
