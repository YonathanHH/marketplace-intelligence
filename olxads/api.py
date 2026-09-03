"""FastAPI application serving the OLX Ads Intelligence platform."""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analytics as A
from . import actions
from .config import WEB_DIR
from .db import connect, query
from .runtime import database_path

app = FastAPI(
    title="OLX Ads Intelligence API",
    version="1.0.0",
    description=(
        "Sales intelligence for marketplace advertising: which sellers to call, "
        "why they matter, and what they are worth."
    ),
)

# The Vite dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    """One short-lived connection per request."""
    db = database_path()
    if not db.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not built. Run: python run.py --rebuild",
        )
    conn = connect(db)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[Any, Depends(get_conn)]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ActivityIn(BaseModel):
    sales_rep: str = Field(..., min_length=1, description="Rep logging the activity")
    activity_type: Literal[
        "cold_call", "email", "meeting", "demo", "proposal_sent", "follow_up", "renewal_call"
    ]
    outcome: Literal[
        "interested", "not_interested", "converted", "no_response", "follow_up_scheduled"
    ]
    deal_stage: Literal[
        "prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"
    ]
    activity_date: str | None = Field(None, description="ISO date; defaults to the dataset's as-of date")
    next_follow_up_date: str | None = None
    potential_deal_value_idr: int | None = Field(
        None, description="Defaults to the modeled monthly headroom for this seller"
    )


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
def health() -> dict:
    db = database_path()
    return {"status": "ok", "database": db.exists(), "source": db.name}


@app.get("/api/engines", tags=["meta"])
def engines(conn: Conn) -> dict:
    """Which engine produced what. SQLite serves; DuckDB pre-computes."""
    meta = {r["key"]: r["value"] for r in query(conn, "SELECT key, value FROM build_metadata")}
    return {
        "serving": {"engine": "sqlite", "version": sqlite3.sqlite_version},
        "analytical": {
            "engine": meta.get("olap_engine") or "none",
            "version": meta.get("olap_version") or None,
            "fact_rows": int(meta.get("olap_fact_rows") or 0) or None,
            "available": A.olap_available(conn),
        },
    }


@app.get("/api/meta", tags=["meta"])
def meta(conn: Conn) -> dict:
    rows = query(conn, "SELECT key, value FROM build_metadata")
    return {r["key"]: r["value"] for r in rows}


# ---------------------------------------------------------------------------
# Opportunity queue
# ---------------------------------------------------------------------------

@app.get("/api/leads", tags=["opportunities"])
def list_leads(
    conn: Conn,
    tier: Annotated[list[str] | None, Query()] = None,
    category: Annotated[list[str] | None, Query()] = None,
    province: Annotated[list[str] | None, Query()] = None,
    seller_type: Annotated[list[str] | None, Query()] = None,
    account_tier: Annotated[list[str] | None, Query()] = None,
    action: Annotated[list[str] | None, Query()] = None,
    advertiser_status: Literal["any", "never", "active"] = "any",
    contact_status: Literal["any", "uncontacted", "contacted"] = "any",
    min_score: float | None = None,
    q: str | None = None,
    sort: str = "opportunity_score",
    order: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    return A.list_leads(conn, {
        "tier": tier, "category": category, "province": province,
        "seller_type": seller_type, "account_tier": account_tier, "action": action,
        "advertiser_status": advertiser_status, "contact_status": contact_status,
        "min_score": min_score, "q": q, "sort": sort, "order": order,
        "page": page, "page_size": page_size,
    })


@app.get("/api/leads/filters", tags=["opportunities"])
def lead_filters(conn: Conn) -> dict:
    return A.filter_options(conn)


@app.get("/api/leads/export", tags=["opportunities"])
def export_leads(request: Request, conn: Conn) -> StreamingResponse:
    """Export the current filtered queue as CSV — reps live in spreadsheets."""
    params = dict(request.query_params)
    multi = {k: request.query_params.getlist(k) for k in ("tier", "category", "province", "seller_type", "account_tier", "action")}
    params.update({k: v for k, v in multi.items() if v})
    params["page"] = 1
    params["page_size"] = 200

    columns = [
        "rank", "seller_id", "seller_name", "primary_category", "city", "province",
        "account_tier", "opportunity_score", "priority_tier", "monthly_spend_headroom",
        "expected_monthly_value", "recommended_product_label", "next_best_action",
        "total_views", "touch_count", "days_since_last_contact", "reason",
    ]

    def rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()
        page = 1
        while True:
            params["page"] = page
            result = A.list_leads(conn, params)
            if not result["rows"]:
                break
            for row in result["rows"]:
                buf.seek(0), buf.truncate(0)
                writer.writerow([row.get(c, "") for c in columns])
                yield buf.getvalue()
            if page >= result["total_pages"]:
                break
            page += 1

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="olx_ads_opportunities.csv"'},
    )


@app.get("/api/sellers/{seller_id}", tags=["opportunities"])
def seller_detail(seller_id: str, conn: Conn) -> dict:
    detail = A.seller_detail(conn, seller_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")
    return detail


@app.post("/api/sellers/{seller_id}/activities", tags=["opportunities"], status_code=201)
def create_activity(seller_id: str, payload: ActivityIn, conn: Conn) -> dict:
    """Log an outreach activity; the seller is rescored immediately."""
    try:
        return actions.log_activity(conn, seller_id, payload.model_dump())
    except actions.ActivityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/api/overview", tags=["analytics"])
def overview(conn: Conn) -> dict:
    return A.overview(conn)


@app.get("/api/analytics/marketplace", tags=["analytics"])
def marketplace(conn: Conn) -> dict:
    return A.marketplace_analytics(conn)


@app.get("/api/analytics/advertising", tags=["analytics"])
def advertising(conn: Conn) -> dict:
    return A.advertising_analytics(conn)


@app.get("/api/analytics/pipeline", tags=["analytics"])
def pipeline(conn: Conn) -> dict:
    return A.pipeline_analytics(conn)


@app.get("/api/analytics/coverage", tags=["analytics"])
def coverage(conn: Conn) -> dict:
    return A.coverage_analytics(conn)


@app.get("/api/analytics/olap", tags=["analytics"])
def olap(conn: Conn) -> dict:
    """Deep-dive analytics computed by the DuckDB OLAP pass at build time.

    Missing tables mean the database was built without DuckDB installed, which
    is a legitimate state (runtime-only install) — say so plainly instead of
    surfacing `no such table: olap_listing_decay`.
    """
    if not A.olap_available(conn):
        raise HTTPException(
            status_code=503,
            detail=(
                "Deep-dive analytics are not in this database. Install DuckDB "
                "(pip install -r requirements-dev.txt) and rebuild: python run.py --rebuild"
            ),
        )
    return A.olap_analytics(conn)


# ---------------------------------------------------------------------------
# Static frontend (production build). In dev, Vite serves the UI instead.
# ---------------------------------------------------------------------------

DIST_DIR = WEB_DIR / "dist"

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
