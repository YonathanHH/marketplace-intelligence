/** Shapes returned by the FastAPI backend. */

export type PriorityTier = "Hot" | "Warm" | "Cool" | "Low";

export interface Lead {
  rank: number;
  seller_id: string;
  seller_name: string;
  seller_type: string;
  primary_category: string;
  city: string;
  province: string;
  account_tier: string;
  opportunity_score: number;
  priority_tier: PriorityTier;
  marketplace_score: number;
  advertising_gap_score: number;
  seller_score: number;
  sales_gap_score: number;
  total_views: number;
  total_chats: number;
  listing_count: number;
  active_listing_count: number;
  total_ad_spend: number;
  observed_monthly_spend: number;
  benchmark_monthly_spend: number;
  monthly_spend_headroom: number;
  expected_monthly_value: number;
  win_probability: number;
  has_ads: number;
  touch_count: number;
  days_since_last_contact: number | null;
  last_sales_rep: string | null;
  recommended_product: string;
  recommended_product_label: string;
  next_best_action: string;
  is_verified: number;
  rating_avg: number | null;
  response_rate_pct: number;
  reason: string;
}

export interface LeadsResponse {
  rows: Lead[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  aggregate: { monthly_headroom: number; expected_monthly_value: number };
}

export interface FilterOptions {
  categories: string[];
  provinces: string[];
  seller_types: string[];
  account_tiers: string[];
  tiers: string[];
  actions: string[];
  sorts: string[];
}

export interface Overview {
  kpis: {
    total_sellers: number;
    hot_leads: number;
    advertisers: number;
    contacted_sellers: number;
    current_monthly_revenue: number;
    monthly_headroom: number;
    expected_monthly_value: number;
    new_logo_headroom: number;
    upsell_headroom: number;
    uncovered_priority_headroom: number;
    uncovered_priority_leads: number;
    avg_win_probability: number;
    advertiser_penetration: number;
    coverage_rate: number;
    annual_headroom: number;
  };
  marketplace: {
    total_listings: number;
    active_listings: number;
    total_views: number;
    total_leads_generated: number;
  };
  tier_mix: {
    tier: PriorityTier;
    sellers: number;
    monthly_headroom: number;
    expected_monthly_value: number;
    avg_score: number;
  }[];
  top_leads: (Pick<
    Lead,
    | "rank" | "seller_id" | "seller_name" | "primary_category" | "city" | "province"
    | "opportunity_score" | "priority_tier" | "monthly_spend_headroom"
    | "expected_monthly_value" | "recommended_product_label" | "next_best_action"
    | "total_views" | "has_ads" | "touch_count" | "reason"
  >)[];
  category_opportunity: {
    category: string;
    sellers: number;
    advertisers: number;
    monthly_headroom: number;
    current_revenue: number;
    avg_score: number;
  }[];
  as_of: string;
  built_at: string;
}

export interface MarketplaceAnalytics {
  trend: { date: string; impressions: number; views: number; clicks: number; leads: number }[];
  categories: {
    category: string; listings: number; sellers: number; views: number; leads: number; avg_price: number;
  }[];
  provinces: { province: string; listings: number; sellers: number; views: number }[];
  status_mix: { status: string; listings: number }[];
  funnel: { impressions: number; views: number; clicks: number; chats: number; phone_reveals: number };
  featured_lift: {
    segment: string; listings: number; views_per_listing: number; leads_per_listing: number;
  }[];
}

export interface AdvertisingAnalytics {
  totals: {
    total_spend: number; total_budget: number; campaigns: number; advertisers: number;
    conversions: number; blended_cpa: number; blended_ctr: number;
  };
  revenue_trend: { month: string; spend: number; campaigns: number; advertisers: number }[];
  by_type: {
    campaign_type: string; campaigns: number; spend: number; impressions: number; clicks: number;
    conversions: number; ctr_pct: number; cpc: number; cost_per_conversion: number; conversion_rate: number;
  }[];
  by_category: { category: string; advertisers: number; spend: number; conversions: number }[];
  penetration: {
    account_tier: string; sellers: number; advertisers: number; penetration_pct: number;
    monthly_revenue: number; monthly_headroom: number;
  }[];
  spend_distribution: { band: string; sellers: number; monthly_revenue: number }[];
  status_mix: { status: string; campaigns: number; spend: number }[];
}

export interface PipelineAnalytics {
  totals: { activities: number; accounts_touched: number; wins: number; avg_deal_value: number };
  stage_funnel: { stage: string; sellers: number; monthly_headroom: number }[];
  outcomes: { outcome: string; activities: number }[];
  activity_types: { activity_type: string; activities: number; conversions: number }[];
  reps: {
    sales_rep: string; activities: number; accounts: number; wins: number;
    win_rate_pct: number; pipeline_value: number;
  }[];
  activity_trend: { month: string; activities: number; accounts_touched: number; wins: number }[];
  win_rate_by_segment: {
    seller_type: string; account_tier: string; contacted: number; modeled_win_rate: number;
  }[];
}

export interface CoverageAnalytics {
  by_province: {
    province: string; sellers: number; contacted: number; coverage_pct: number;
    priority_leads: number; uncovered_priority: number; uncovered_headroom: number;
  }[];
  by_category: {
    category: string; sellers: number; contacted: number; coverage_pct: number;
    uncovered_priority: number; uncovered_headroom: number;
  }[];
  effort_quality: {
    well_targeted: number; low_value_touched: number; missed_priority: number; correctly_skipped: number;
  };
  stale_priority_accounts: {
    seller_id: string; seller_name: string; primary_category: string; province: string;
    opportunity_score: number; priority_tier: PriorityTier; days_since_last_contact: number;
    last_sales_rep: string; monthly_spend_headroom: number;
  }[];
}

export interface SellerDetail {
  seller: Lead & {
    traction_band: number;
    benchmark_basis: string;
    benchmark_comparables: number;
    annual_revenue_potential: number;
    lead_quality_ratio: number;
    talking_points: string[];
    tenure_years: number;
    rating_count: number;
    response_time_hours: number;
    registration_date: string;
    total_impressions: number;
    total_clicks: number;
    total_phone_reveals: number;
    sold_listing_count: number;
    campaign_count: number;
    total_conversions: number;
    last_deal_stage: string | null;
    last_outcome: string | null;
    next_follow_up_date: string | null;
    days_since_active: number;
    avg_price_idr: number;
  };
  listings: {
    listing_id: string; title: string; category: string; subcategory: string; price_idr: number;
    condition: string; status: string; created_date: string; is_featured: number;
    photo_count: number; views: number; clicks: number; leads: number;
  }[];
  traction_trend: { date: string; views: number; clicks: number; leads: number }[];
  campaigns: {
    campaign_id: string; campaign_name: string; campaign_type: string; start_date: string;
    end_date: string; status: string; budget_idr: number; spend_idr: number;
    impressions: number; clicks: number; conversions: number;
  }[];
  activities: {
    activity_id: string; sales_rep: string; activity_date: string; activity_type: string;
    channel: string; outcome: string; deal_stage: string; potential_deal_value_idr: number;
    next_follow_up_date: string | null;
  }[];
  comparables: {
    seller_id: string; seller_name: string; observed_monthly_spend: number;
    total_views: number; account_tier: string;
  }[];
}

export interface ActivityInput {
  sales_rep: string;
  activity_type: string;
  outcome: string;
  deal_stage: string;
  activity_date?: string | null;
  next_follow_up_date?: string | null;
  potential_deal_value_idr?: number | null;
}

/* --------------------------------------------------------------- Deep dive --
   Results of the build-time DuckDB pass (see olxads/olap.py). The API serves
   them out of SQLite, so the shapes here mirror the materialised tables. */

export interface OlapAnalytics {
  engine: {
    name: string;
    version: string | null;
    fact_rows: number | null;
    build_ms: number | null;
  };
  listing_decay: {
    category: string; week_since_post: number; listings: number;
    avg_daily_views: number; avg_daily_leads: number; retention_index: number;
  }[];
  listing_decay_overall: {
    week_since_post: number; listings: number;
    avg_daily_views: number; avg_daily_leads: number; retention_index: number;
  }[];
  demand_weekly: {
    category: string; week: string; views: number; leads: number;
    views_4w_avg: number; wow_pct: number | null;
  }[];
  category_momentum: {
    category: string; recent_views: number; prior_views: number;
    recent_leads: number; momentum_pct: number | null;
  }[];
  revenue_concentration: {
    advertiser_pct: number; advertisers: number; spend: number; cum_revenue_pct: number;
  }[];
  traction_percentiles: {
    category: string; sellers: number;
    p10: number; p25: number; p50: number; p75: number; p90: number;
    median_advertiser: number; median_non_advertiser: number;
    non_advertisers: number; non_advertisers_above_median: number;
    headroom_above_median: number;
  }[];
  conversion_by_traction: {
    quintile: number; activities: number; views_floor: number; views_ceiling: number;
    avg_views_at_call: number; conversions: number;
    conversion_rate_pct: number; no_response_pct: number;
  }[];
  headlines: {
    retention_week1: number | null;
    retention_week3: number | null;
    top_5pct_revenue_share: number | null;
    top_20pct_revenue_share: number | null;
    underdog_sellers: number;
    underdog_headroom: number;
    conversion_bottom_quintile: number | null;
    conversion_top_quintile: number | null;
    conversion_best_quintile: number | null;
    conversion_lift: number | null;
    fastest_growing: string | null;
    fastest_growing_pct: number | null;
  };
}
