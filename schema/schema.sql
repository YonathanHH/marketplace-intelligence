-- OLX Ads Intelligence — schema.sql
-- SQLite-compatible DDL (also valid, with minor type tweaks, on Postgres).
-- See docs/DATA_MODEL.md for the full data dictionary and ERD.

PRAGMA foreign_keys = ON;

-- 1. SELLERS ------------------------------------------------------------
CREATE TABLE sellers (
    seller_id            TEXT PRIMARY KEY,
    seller_name          TEXT NOT NULL,
    seller_type          TEXT NOT NULL CHECK (seller_type IN ('individual','small_business','dealer','enterprise')),
    primary_category     TEXT NOT NULL,
    city                 TEXT NOT NULL,
    province             TEXT NOT NULL,
    registration_date    DATE NOT NULL,
    account_tier         TEXT NOT NULL CHECK (account_tier IN ('free','basic','premium')),
    is_verified          INTEGER NOT NULL CHECK (is_verified IN (0,1)),
    phone_verified       INTEGER NOT NULL CHECK (phone_verified IN (0,1)),
    rating_avg           REAL,
    rating_count         INTEGER NOT NULL DEFAULT 0,
    response_rate_pct    REAL,
    response_time_hours  REAL,
    last_active_date     DATE NOT NULL
    -- NOTE: "power seller" is deliberately NOT stored here. It is fully
    -- derivable (active listing count >= 20) and a stored snapshot flag would
    -- drift from the listings table. It is computed in the scoring layer.
);

-- 2. LISTINGS -------------------------------------------------------------
CREATE TABLE listings (
    listing_id           TEXT PRIMARY KEY,
    seller_id            TEXT NOT NULL REFERENCES sellers(seller_id),
    category             TEXT NOT NULL,
    subcategory          TEXT NOT NULL,
    title                TEXT NOT NULL,
    price_idr            INTEGER NOT NULL CHECK (price_idr >= 0),
    condition            TEXT NOT NULL CHECK (condition IN ('new','used')),
    city                 TEXT NOT NULL,
    province             TEXT NOT NULL,
    created_date          DATE NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('active','sold','expired','removed')),
    sold_or_expired_date  DATE,
    is_featured          INTEGER NOT NULL CHECK (is_featured IN (0,1)),
    photo_count          INTEGER NOT NULL CHECK (photo_count >= 0),
    description_length   INTEGER NOT NULL CHECK (description_length >= 0)
);
CREATE INDEX idx_listings_seller ON listings(seller_id);
CREATE INDEX idx_listings_category ON listings(category);
CREATE INDEX idx_listings_status ON listings(status);

-- 3. LISTING_METRICS (grain: listing x day) --------------------------------
CREATE TABLE listing_metrics (
    metric_id            TEXT PRIMARY KEY,
    listing_id           TEXT NOT NULL REFERENCES listings(listing_id),
    date                 DATE NOT NULL,
    impressions          INTEGER NOT NULL CHECK (impressions >= 0),
    views                INTEGER NOT NULL CHECK (views >= 0),
    clicks               INTEGER NOT NULL CHECK (clicks >= 0),
    ctr_pct              REAL NOT NULL,
    chats_started        INTEGER NOT NULL CHECK (chats_started >= 0),
    phone_reveals        INTEGER NOT NULL CHECK (phone_reveals >= 0),
    favorites_added      INTEGER NOT NULL CHECK (favorites_added >= 0),
    search_rank_avg      REAL,
    UNIQUE (listing_id, date)
);
CREATE INDEX idx_metrics_listing ON listing_metrics(listing_id);
CREATE INDEX idx_metrics_date ON listing_metrics(date);

-- 4. AD_CAMPAIGNS ---------------------------------------------------------
CREATE TABLE ad_campaigns (
    campaign_id          TEXT PRIMARY KEY,
    seller_id            TEXT NOT NULL REFERENCES sellers(seller_id),
    listing_id           TEXT REFERENCES listings(listing_id),
    campaign_name        TEXT NOT NULL,
    campaign_type        TEXT NOT NULL CHECK (campaign_type IN
                          ('featured_listing','bump_up','search_boost','homepage_banner','category_spotlight')),
    start_date           DATE NOT NULL,
    end_date             DATE NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('active','completed','paused')),
    budget_idr           INTEGER NOT NULL CHECK (budget_idr >= 0),
    spend_idr            INTEGER NOT NULL CHECK (spend_idr >= 0),
    impressions          INTEGER NOT NULL CHECK (impressions >= 0),
    clicks               INTEGER NOT NULL CHECK (clicks >= 0),
    conversions           INTEGER NOT NULL CHECK (conversions >= 0),
    CHECK (spend_idr <= budget_idr),
    CHECK (end_date >= start_date)
);
CREATE INDEX idx_campaigns_seller ON ad_campaigns(seller_id);
CREATE INDEX idx_campaigns_listing ON ad_campaigns(listing_id);

-- 5. SALES_ACTIVITIES -------------------------------------------------------
CREATE TABLE sales_activities (
    activity_id                TEXT PRIMARY KEY,
    seller_id                  TEXT NOT NULL REFERENCES sellers(seller_id),
    sales_rep                  TEXT NOT NULL,
    activity_date               DATE NOT NULL,
    activity_type               TEXT NOT NULL CHECK (activity_type IN
                                ('cold_call','email','meeting','demo','proposal_sent','follow_up','renewal_call')),
    channel                    TEXT NOT NULL CHECK (channel IN ('phone','email','in_person','video_call')),
    outcome                    TEXT NOT NULL CHECK (outcome IN
                                ('interested','not_interested','converted','no_response','follow_up_scheduled')),
    deal_stage                 TEXT NOT NULL CHECK (deal_stage IN
                                ('prospecting','qualified','proposal','negotiation','closed_won','closed_lost')),
    potential_deal_value_idr    INTEGER NOT NULL CHECK (potential_deal_value_idr >= 0),
    next_follow_up_date         DATE
);
CREATE INDEX idx_activities_seller ON sales_activities(seller_id);
CREATE INDEX idx_activities_rep ON sales_activities(sales_rep);
