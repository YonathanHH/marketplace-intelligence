"""Write operations — the things a rep actually *does* in the tool.

Logging an activity has to update the seller's score immediately, otherwise
the queue would keep recommending an account that was just called. Rather
than re-running the whole batch pipeline, we recompute only what a new touch
can actually change: the sales-coverage pillar and the composite. The
marketplace/advertising/seller pillars are population percentiles that a
single phone call does not move.

The gap rule and the composite formula come from `olxads.rules`, which the
batch build uses too, so this path cannot drift from how the nightly build
would score the same seller. `rules` has no third-party imports, which keeps
pandas out of the serving runtime.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from .db import query_one
from .rules import (
    build_reason,
    composite_score,
    next_best_action,
    sales_gap_from_state,
    tier_for_score,
)

ACTIVITY_TYPES = [
    "cold_call", "email", "meeting", "demo", "proposal_sent", "follow_up", "renewal_call",
]
CHANNELS = {
    "cold_call": "phone", "email": "email", "meeting": "in_person", "demo": "video_call",
    "proposal_sent": "email", "follow_up": "phone", "renewal_call": "phone",
}
OUTCOMES = ["interested", "not_interested", "converted", "no_response", "follow_up_scheduled"]
DEAL_STAGES = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


class ActivityError(ValueError):
    """Raised when a logged activity fails validation."""


def _next_activity_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(activity_id, 5) AS INTEGER)) AS n FROM sales_activities").fetchone()
    return f"ACT-{(row['n'] or 0) + 1:06d}"


def _as_of(conn: sqlite3.Connection) -> dt.date:
    row = conn.execute("SELECT value FROM build_metadata WHERE key = 'as_of_date'").fetchone()
    return dt.date.fromisoformat(row["value"]) if row else dt.date.today()


def log_activity(conn: sqlite3.Connection, seller_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Insert a sales activity and rescore the affected seller."""
    seller = query_one(conn, "SELECT * FROM seller_scores WHERE seller_id = ?", (seller_id,))
    if seller is None:
        raise ActivityError(f"Unknown seller: {seller_id}")

    activity_type = payload.get("activity_type")
    outcome = payload.get("outcome")
    deal_stage = payload.get("deal_stage")
    if activity_type not in ACTIVITY_TYPES:
        raise ActivityError(f"activity_type must be one of {ACTIVITY_TYPES}")
    if outcome not in OUTCOMES:
        raise ActivityError(f"outcome must be one of {OUTCOMES}")
    if deal_stage not in DEAL_STAGES:
        raise ActivityError(f"deal_stage must be one of {DEAL_STAGES}")

    as_of = _as_of(conn)
    activity_date = payload.get("activity_date") or as_of.isoformat()
    next_follow_up = payload.get("next_follow_up_date") or None
    sales_rep = (payload.get("sales_rep") or "").strip()
    if not sales_rep:
        raise ActivityError("sales_rep is required")

    deal_value = payload.get("potential_deal_value_idr")
    if deal_value in (None, ""):
        # Default to the modeled headroom — the number the platform itself
        # says this account is worth per month.
        deal_value = int(seller.get("monthly_spend_headroom") or 0)
    deal_value = max(0, int(deal_value))

    activity_id = _next_activity_id(conn)
    conn.execute(
        """
        INSERT INTO sales_activities (
            activity_id, seller_id, sales_rep, activity_date, activity_type, channel,
            outcome, deal_stage, potential_deal_value_idr, next_follow_up_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id, seller_id, sales_rep, activity_date, activity_type,
            CHANNELS[activity_type], outcome, deal_stage, deal_value, next_follow_up,
        ),
    )

    updated = _rescore_seller(conn, seller_id, as_of)
    conn.commit()
    return {"activity_id": activity_id, "seller": updated}


def _rescore_seller(conn: sqlite3.Connection, seller_id: str, as_of: dt.date) -> dict[str, Any]:
    """Recompute the sales pillar and composite for one seller, in place."""
    state = query_one(
        conn,
        """
        SELECT COUNT(*) AS touch_count,
               MAX(activity_date) AS last_contact_date,
               MAX(next_follow_up_date) AS next_follow_up_date
        FROM sales_activities WHERE seller_id = ?
        """,
        (seller_id,),
    )
    last = query_one(
        conn,
        """
        SELECT deal_stage, outcome, sales_rep
        FROM sales_activities WHERE seller_id = ?
        ORDER BY activity_date DESC, activity_id DESC LIMIT 1
        """,
        (seller_id,),
    ) or {}

    touch_count = state["touch_count"] or 0
    last_contact = state["last_contact_date"]
    days_since = (as_of - dt.date.fromisoformat(last_contact)).days if last_contact else None
    follow_up = state["next_follow_up_date"]
    has_open_follow_up = bool(follow_up and dt.date.fromisoformat(follow_up) >= as_of)

    sales_gap = sales_gap_from_state(
        touch_count, last.get("deal_stage"), last.get("outcome"), has_open_follow_up, days_since
    )

    seller = query_one(conn, "SELECT * FROM seller_scores WHERE seller_id = ?", (seller_id,))
    score = composite_score(
        seller["marketplace_score"], seller["advertising_gap_score"], seller["seller_score"], sales_gap
    )

    merged = {
        **seller,
        "touch_count": touch_count,
        "last_contact_date": last_contact,
        "next_follow_up_date": follow_up,
        "last_deal_stage": last.get("deal_stage"),
        "last_outcome": last.get("outcome"),
        "last_sales_rep": last.get("sales_rep"),
        "has_open_follow_up": int(has_open_follow_up),
        "days_since_last_contact": days_since,
        "sales_gap_score": sales_gap,
        "opportunity_score": score,
        "priority_tier": tier_for_score(score),
    }
    merged["next_best_action"] = next_best_action(merged)
    merged["reason"] = build_reason(merged)

    conn.execute(
        """
        UPDATE seller_scores SET
            touch_count = :touch_count,
            last_contact_date = :last_contact_date,
            next_follow_up_date = :next_follow_up_date,
            last_deal_stage = :last_deal_stage,
            last_outcome = :last_outcome,
            last_sales_rep = :last_sales_rep,
            has_open_follow_up = :has_open_follow_up,
            days_since_last_contact = :days_since_last_contact,
            sales_gap_score = :sales_gap_score,
            opportunity_score = :opportunity_score,
            priority_tier = :priority_tier,
            next_best_action = :next_best_action,
            reason = :reason
        WHERE seller_id = :seller_id
        """,
        {k: merged[k] for k in [
            "touch_count", "last_contact_date", "next_follow_up_date", "last_deal_stage",
            "last_outcome", "last_sales_rep", "has_open_follow_up", "days_since_last_contact",
            "sales_gap_score", "opportunity_score", "priority_tier", "next_best_action",
            "reason", "seller_id",
        ]},
    )
    return merged
