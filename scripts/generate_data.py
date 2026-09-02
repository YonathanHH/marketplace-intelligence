"""
OLX Ads Intelligence — synthetic dataset generator.

Generates five relational tables (sellers, listings, listing_metrics,
ad_campaigns, sales_activities) that back the OLX Ads Intelligence platform.
See docs/DATA_MODEL.md for the schema design and rationale, and
"Data quality & leakage audit" in that doc for why the generation logic below
looks the way it does (latent quality draws, logistic propensities, proxies
instead of ground truth) rather than simpler deterministic formulas.

Usage:
    python scripts/generate_data.py [--out data/raw] [--seed 42]

All randomness is seeded, so re-running with the same --seed reproduces the
exact same dataset. Run scripts/audit_data.py afterwards to check the
leakage/determinism diagnostics.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

N_SELLERS = 1500
TODAY = dt.date(2026, 9, 1)  # generation "as of" date
METRICS_DAY_CAP = 30  # max days of daily metrics captured per listing

PROVINCES_CITIES = {
    "DKI Jakarta": ["Jakarta Selatan", "Jakarta Barat", "Jakarta Timur", "Jakarta Utara", "Jakarta Pusat"],
    "Jawa Barat": ["Bandung", "Bekasi", "Depok", "Bogor", "Cimahi"],
    "Jawa Timur": ["Surabaya", "Malang", "Sidoarjo", "Kediri"],
    "Jawa Tengah": ["Semarang", "Solo", "Magelang"],
    "Banten": ["Tangerang", "Tangerang Selatan", "Serang"],
    "Sumatera Utara": ["Medan", "Binjai"],
    "Sumatera Selatan": ["Palembang"],
    "DI Yogyakarta": ["Yogyakarta"],
    "Bali": ["Denpasar", "Badung"],
    "Kalimantan Timur": ["Balikpapan", "Samarinda"],
    "Sulawesi Selatan": ["Makassar"],
    "Kepulauan Riau": ["Batam"],
}
ALL_PROVINCES = list(PROVINCES_CITIES.keys())
# Bigger metro provinces get proportionally more sellers
PROVINCE_WEIGHTS = np.array([0.22, 0.16, 0.13, 0.09, 0.10, 0.07, 0.05, 0.04, 0.05, 0.03, 0.03, 0.03])
PROVINCE_WEIGHTS = PROVINCE_WEIGHTS / PROVINCE_WEIGHTS.sum()
# rough cost-of-living / price multiplier used for big-ticket categories (Property, Vehicles)
PROVINCE_PRICE_MULT = {
    "DKI Jakarta": 1.35, "Banten": 1.15, "Jawa Barat": 1.05, "Bali": 1.25,
    "DI Yogyakarta": 0.95, "Jawa Timur": 1.0, "Jawa Tengah": 0.9,
    "Sumatera Utara": 0.9, "Sumatera Selatan": 0.85, "Kalimantan Timur": 1.05,
    "Sulawesi Selatan": 0.9, "Kepulauan Riau": 1.0,
}

CATEGORIES = {
    "Vehicles": {
        "subcategories": ["Cars", "Motorcycles", "Auto Parts & Accessories"],
        "price_range": (5_000_000, 350_000_000),
        "titles": ["{brand} {model} {year} {cond}", "Dijual {brand} {model} {year} mulus", "{brand} {model} pajak panjang"],
        "brands": ["Toyota", "Honda", "Suzuki", "Daihatsu", "Yamaha", "Mitsubishi", "Nissan", "Kawasaki"],
    },
    "Property": {
        "subcategories": ["Houses for Sale", "Apartments", "Land", "Houses for Rent"],
        "price_range": (150_000_000, 6_000_000_000),
        "titles": ["Rumah {rooms}KT {city} Siap Huni", "Dijual Tanah Strategis {city}", "Apartemen {rooms}BR {city} View Kota"],
        "brands": [],
    },
    "Electronics & Gadgets": {
        "subcategories": ["Smartphones", "Laptops", "Cameras", "TV & Audio"],
        "price_range": (300_000, 35_000_000),
        "titles": ["{brand} {model} {cond} Fullset", "Jual {brand} {model} Mulus Bergaransi", "{brand} {model} Second Like New"],
        "brands": ["Samsung", "Apple", "Xiaomi", "Asus", "Lenovo", "Canon", "Sony", "Oppo"],
    },
    "Fashion & Beauty": {
        "subcategories": ["Men's Clothing", "Women's Clothing", "Bags & Shoes", "Watches"],
        "price_range": (30_000, 3_000_000),
        "titles": ["{brand} Original {cond}", "Preloved {brand} Kondisi Mulus", "{brand} New With Tag"],
        "brands": ["Uniqlo", "Zara", "Nike", "Adidas", "Fossil", "Charles & Keith"],
    },
    "Home & Furniture": {
        "subcategories": ["Furniture", "Home Decor", "Kitchenware", "Appliances"],
        "price_range": (50_000, 15_000_000),
        "titles": ["{brand} {cond} Siap Kirim", "Sofa & Meja Set Kondisi Bagus", "{brand} Peralatan Rumah Tangga"],
        "brands": ["IKEA", "Informa", "Ace Hardware", "Polytron", "Sharp", "Electrolux"],
    },
    "Jobs": {
        "subcategories": ["Full Time", "Part Time", "Freelance"],
        "price_range": (2_500_000, 25_000_000),
        "titles": ["Dicari {role} Berpengalaman", "Lowongan {role} {city}", "Loker {role} Gaji Kompetitif"],
        "brands": [],
    },
    "Hobbies & Sports": {
        "subcategories": ["Sports Equipment", "Musical Instruments", "Collectibles", "Outdoor Gear"],
        "price_range": (50_000, 12_000_000),
        "titles": ["{brand} {cond} Jarang Pakai", "Jual {brand} Original", "{brand} Set Lengkap"],
        "brands": ["Yamaha", "Wilson", "Eiger", "Consina", "Specialized"],
    },
    "Baby & Kids": {
        "subcategories": ["Baby Gear", "Toys", "Kids Clothing"],
        "price_range": (30_000, 5_000_000),
        "titles": ["{brand} {cond} Aman & Bersih", "Preloved {brand} Anak", "{brand} Second Mulus"],
        "brands": ["Pigeon", "Chicco", "Fisher-Price", "Cussons Baby"],
    },
    "Services": {
        "subcategories": ["Home Services", "Tutoring", "Event Services", "IT Services"],
        "price_range": (100_000, 10_000_000),
        "titles": ["Jasa {role} Profesional Berpengalaman", "{role} Panggilan Siap Bantu", "Jasa {role} Harga Bersahabat"],
        "brands": [],
    },
}
CATEGORY_NAMES = list(CATEGORIES.keys())
CATEGORY_WEIGHTS = np.array([0.20, 0.14, 0.16, 0.14, 0.10, 0.08, 0.07, 0.06, 0.05])
CATEGORY_WEIGHTS = CATEGORY_WEIGHTS / CATEGORY_WEIGHTS.sum()

# segment-specific engagement baselines: how a click, once earned, turns into
# a chat / phone reveal / favorite differs a lot by category (a car buyer
# calls; a fashion buyer chats; a job seeker never "favorites")
CATEGORY_ENGAGEMENT = {
    "Vehicles":               dict(click=0.11, chat=0.35, phone=0.45, favorite=0.05),
    "Property":                dict(click=0.08, chat=0.30, phone=0.50, favorite=0.06),
    "Electronics & Gadgets":    dict(click=0.10, chat=0.55, phone=0.20, favorite=0.05),
    "Fashion & Beauty":         dict(click=0.09, chat=0.60, phone=0.10, favorite=0.08),
    "Home & Furniture":         dict(click=0.07, chat=0.45, phone=0.20, favorite=0.05),
    "Jobs":                    dict(click=0.15, chat=0.70, phone=0.10, favorite=0.02),
    "Hobbies & Sports":         dict(click=0.08, chat=0.50, phone=0.15, favorite=0.06),
    "Baby & Kids":              dict(click=0.09, chat=0.55, phone=0.15, favorite=0.07),
    "Services":                dict(click=0.12, chat=0.40, phone=0.35, favorite=0.03),
}

# how much a "featured" boost actually helps varies by category: high-consideration
# purchases (cars, property) get a bigger lift from extra visibility than impulse
# categories where buyers browse broadly anyway
FEATURED_BOOST_BY_CATEGORY = {
    "Vehicles": 2.6, "Property": 2.8, "Electronics & Gadgets": 2.2,
    "Fashion & Beauty": 1.5, "Home & Furniture": 1.7, "Jobs": 1.4,
    "Hobbies & Sports": 1.5, "Baby & Kids": 1.6, "Services": 1.5,
}

# rough monthly demand seasonality per category (1.0 = no effect). Deliberately
# sparse — most category/month combos are left at the 1.0 default.
CATEGORY_SEASONALITY = {
    "Jobs":                    {1: 1.35, 2: 1.15, 7: 1.10, 12: 0.75},
    "Property":                 {12: 1.25, 1: 1.15, 6: 0.85},
    "Vehicles":                {12: 1.30, 1: 1.10, 6: 0.85},
    "Electronics & Gadgets":    {11: 1.25, 12: 1.35, 1: 0.9},
    "Fashion & Beauty":         {3: 1.15, 4: 1.25, 12: 1.2},
}

# advertising affinity by category (logit units): high-ticket categories with
# professional sellers lean into paid promotion more than casual categories
CATEGORY_AD_AFFINITY = {
    "Vehicles": 0.5, "Property": 0.6, "Electronics & Gadgets": 0.2,
    "Fashion & Beauty": -0.1, "Home & Furniture": -0.05, "Jobs": -0.3,
    "Hobbies & Sports": -0.15, "Baby & Kids": -0.15, "Services": 0.0,
}
# Paid click-through rates are a property of the AD PLACEMENT, not of the
# category's organic browsing behaviour — a homepage banner is seen by everyone
# and clicked by few, while a search boost is served to people already hunting
# for that exact thing. These are baselines in the realistic 0.4%-2.5% range;
# reusing the organic view->contact rate here would imply a ~14% ad CTR.
CAMPAIGN_CTR_BASE = {
    "featured_listing": 0.018,
    "bump_up": 0.015,
    "search_boost": 0.025,
    "homepage_banner": 0.004,
    "category_spotlight": 0.009,
}

CATEGORY_CPM_FACTOR = {
    "Vehicles": 1.15, "Property": 1.3, "Electronics & Gadgets": 1.05,
    "Fashion & Beauty": 0.9, "Home & Furniture": 0.95, "Jobs": 0.8,
    "Hobbies & Sports": 0.9, "Baby & Kids": 0.9, "Services": 1.0,
}

JOB_ROLES = ["Admin", "Sales", "Driver", "Designer", "Content Writer", "Kasir", "Guru", "Programmer", "Marketing"]

SELLER_TYPES = ["individual", "small_business", "dealer", "enterprise"]
SELLER_TYPE_WEIGHTS = [0.65, 0.20, 0.10, 0.05]
# average number of listings a seller of this type ends up with (Poisson lambda)
LISTINGS_LAMBDA = {"individual": 3, "small_business": 8, "dealer": 22, "enterprise": 45}
# advertising affinity by seller type (logit units) — independent axis from account_tier,
# since type and tier are correlated but not identical in this dataset
SELLER_TYPE_AD_AFFINITY = {"individual": -0.3, "small_business": 0.05, "dealer": 0.3, "enterprise": 0.4}
SELLER_TYPE_CONTACT_AFFINITY = {"individual": -0.4, "small_business": 0.1, "dealer": 0.4, "enterprise": 0.6}

SALES_REPS = [
    "Dewi Anggraini", "Rizky Pratama", "Siti Nurhaliza", "Bagus Wicaksono",
    "Putri Ramadhani", "Fajar Nugroho", "Ayu Lestari", "Hendra Setiawan",
]

RNG_SEED = 42


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def weighted_choice(rng: np.random.Generator, options, weights, size=None):
    return rng.choice(options, size=size, p=weights)


def random_date(rng: np.random.Generator, start: dt.date, end: dt.date):
    span = (end - start).days
    if span <= 0:
        return start
    return start + dt.timedelta(days=int(rng.integers(0, span + 1)))


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


# --------------------------------------------------------------------------
# 1. Sellers
# --------------------------------------------------------------------------

def generate_sellers(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    seller_types = weighted_choice(rng, SELLER_TYPES, SELLER_TYPE_WEIGHTS, size=N_SELLERS)
    provinces = weighted_choice(rng, ALL_PROVINCES, PROVINCE_WEIGHTS, size=N_SELLERS)

    for i in range(N_SELLERS):
        seller_id = f"SEL-{i + 1:06d}"
        seller_type = seller_types[i]
        province = provinces[i]
        city = rng.choice(PROVINCES_CITIES[province])
        primary_category = weighted_choice(rng, CATEGORY_NAMES, CATEGORY_WEIGHTS)

        if seller_type == "individual":
            seller_name = fake.name()
        else:
            # Faker's id_ID company names already carry an Indonesian legal-entity
            # prefix (PT / CV / UD / Perum), so prepending our own produced
            # nonsense like "Toko PT Megantara". Truncating mid-word produced
            # "PT Perum Mayasari Andriani (Perse". Use the name as generated and
            # trim on a word boundary; seller_type is its own column anyway.
            seller_name = fake.company()
            if len(seller_name) > 34:
                seller_name = seller_name[:34].rsplit(" ", 1)[0].rstrip(" ,(-")

        registration_date = random_date(rng, dt.date(2018, 1, 1), TODAY - dt.timedelta(days=30))
        tenure_years = (TODAY - registration_date).days / 365.25

        # account tier probabilities depend on seller type
        tier_probs = {
            "individual": [0.85, 0.12, 0.03],
            "small_business": [0.40, 0.40, 0.20],
            "dealer": [0.10, 0.35, 0.55],
            "enterprise": [0.02, 0.18, 0.80],
        }[seller_type]
        account_tier = weighted_choice(rng, ["free", "basic", "premium"], tier_probs)

        is_verified = rng.random() < (0.55 if seller_type == "individual" else 0.90)
        phone_verified = rng.random() < 0.93 if is_verified else rng.random() < 0.5

        # latent, unobserved "operator quality" trait (not exported) — drives weak,
        # noisy correlations across response metrics/rating/ad propensity without
        # any single stored column fully explaining another
        hustle = rng.beta(2, 2)

        rating_count = int(max(0, rng.negative_binomial(5, 0.35 if seller_type != "individual" else 0.5)))
        rating_avg = round(clip(rng.normal(3.9 + 0.9 * hustle, 0.35), 1.0, 5.0), 2) if rating_count > 0 else None

        response_rate_pct = round(clip(rng.normal(50 + 42 * hustle, 14), 5, 100), 1)
        response_time_hours = round(clip(rng.exponential(9 - 5 * hustle), 0.1, 96), 1)

        last_active_date = random_date(rng, max(registration_date, TODAY - dt.timedelta(days=90)), TODAY)

        rows.append({
            "seller_id": seller_id,
            "seller_name": seller_name,
            "seller_type": seller_type,
            "primary_category": primary_category,
            "city": city,
            "province": province,
            "registration_date": registration_date,
            "account_tier": account_tier,
            "is_verified": is_verified,
            "phone_verified": phone_verified,
            "rating_avg": rating_avg,
            "rating_count": rating_count,
            "response_rate_pct": response_rate_pct,
            "response_time_hours": response_time_hours,
            "last_active_date": last_active_date,
            "listings_lambda_helper": LISTINGS_LAMBDA[seller_type],
            "hustle_helper": hustle,
            "tenure_years_helper": tenure_years,
        })

    df = pd.DataFrame(rows)
    return df


# --------------------------------------------------------------------------
# 2. Listings
# --------------------------------------------------------------------------

def make_title(rng: np.random.Generator, category: str, city: str, condition: str) -> str:
    spec = CATEGORIES[category]
    template = rng.choice(spec["titles"])
    brand = rng.choice(spec["brands"]) if spec["brands"] else ""
    return template.format(
        brand=brand,
        model=fake_model_token(rng),
        year=int(rng.integers(2012, 2026)),
        cond="Baru" if condition == "new" else "Bekas",
        rooms=int(rng.integers(1, 5)),
        city=city,
        role=rng.choice(JOB_ROLES),
    )


def fake_model_token(rng: np.random.Generator) -> str:
    letters = "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), size=2))
    return f"{letters}{int(rng.integers(10, 999))}"


def generate_listings(rng: np.random.Generator, sellers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    listing_counter = 1

    for seller in sellers.itertuples():
        n_listings = max(1, rng.poisson(seller.listings_lambda_helper))
        for _ in range(n_listings):
            listing_id = f"LST-{listing_counter:07d}"
            listing_counter += 1

            # dealers/enterprise occasionally cross-list outside home province
            if rng.random() < 0.08 and seller.seller_type in ("dealer", "enterprise"):
                province = rng.choice(ALL_PROVINCES)
                city = rng.choice(PROVINCES_CITIES[province])
            else:
                province, city = seller.province, seller.city

            # category: usually the seller's primary category
            category = seller.primary_category if rng.random() < 0.8 else weighted_choice(rng, CATEGORY_NAMES, CATEGORY_WEIGHTS)
            spec = CATEGORIES[category]
            subcategory = rng.choice(spec["subcategories"])
            condition = weighted_choice(rng, ["new", "used"], [0.3, 0.7])
            title = make_title(rng, category, city, condition)

            lo, hi = spec["price_range"]
            # log-normal-ish price within range
            price = clip(rng.lognormal(mean=np.log(np.sqrt(lo * hi)), sigma=0.5), lo, hi)
            if condition == "used":
                price *= rng.uniform(0.5, 0.85)  # used items priced below new
            if category in ("Property", "Vehicles"):
                price *= PROVINCE_PRICE_MULT.get(province, 1.0)
            price = round(int(clip(price, lo * 0.4, hi)), -3)  # round to nearest 1000 IDR

            created_date = random_date(rng, max(seller.registration_date, TODAY - dt.timedelta(days=180)), TODAY)
            age_days = (TODAY - created_date).days

            status_probs = [0.45, 0.25, 0.25, 0.05] if age_days > 20 else [0.75, 0.10, 0.10, 0.05]
            status = weighted_choice(rng, ["active", "sold", "expired", "removed"], status_probs)
            sold_or_expired_date = None
            if status in ("sold", "expired", "removed"):
                sold_or_expired_date = random_date(rng, created_date, min(TODAY, created_date + dt.timedelta(days=60)))

            is_featured = rng.random() < (0.35 if seller.account_tier != "free" else 0.08)
            photo_count = int(clip(rng.poisson(5), 0, 12))
            description_length = int(clip(rng.normal(220, 90), 20, 900))

            # latent, unobserved per-listing "quality" (photography, pricing, write-up
            # attractiveness) — the single biggest lever keeping traction from being a
            # deterministic function of stored columns
            quality = rng.lognormal(mean=0.0, sigma=0.55)

            rows.append({
                "listing_id": listing_id,
                "seller_id": seller.seller_id,
                "category": category,
                "subcategory": subcategory,
                "title": title,
                "price_idr": price,
                "condition": condition,
                "city": city,
                "province": province,
                "created_date": created_date,
                "status": status,
                "sold_or_expired_date": sold_or_expired_date,
                "is_featured": is_featured,
                "photo_count": photo_count,
                "description_length": description_length,
                "seller_type_helper": seller.seller_type,
                "seller_tier_helper": seller.account_tier,
                "seller_rating_helper": seller.rating_avg if seller.rating_avg else 3.8,
                "quality_helper": quality,
            })

    df = pd.DataFrame(rows)

    # market competition index: how saturated is this category+province combo?
    # more active supply for the same buyer demand dilutes any one listing's
    # share of impressions — a confound tied to marketplace structure, not to
    # any individual seller's attributes
    comp_counts = df.groupby(["category", "province"])["listing_id"].transform("count")
    df["competition_helper"] = 1.0 / (1.0 + 0.16 * np.log1p(comp_counts))

    return df


# --------------------------------------------------------------------------
# 3. Listing metrics (daily grain)
# --------------------------------------------------------------------------

def generate_listing_metrics(rng: np.random.Generator, listings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metric_counter = 1

    for listing in listings.itertuples():
        end_date = listing.sold_or_expired_date if listing.sold_or_expired_date is not None else TODAY
        active_days = (end_date - listing.created_date).days + 1
        n_days = min(active_days, METRICS_DAY_CAP)
        if n_days <= 0:
            continue

        category_boost = {"Vehicles": 1.3, "Property": 1.2, "Electronics & Gadgets": 1.4}.get(listing.category, 1.0)
        featured_boost = FEATURED_BOOST_BY_CATEGORY[listing.category] if listing.is_featured else 1.0
        photo_boost = 0.75 + 0.045 * listing.photo_count
        # tier and rating still matter (known business pattern: better/paying sellers
        # get modestly more traction), but their weight is deliberately small relative
        # to the latent quality draw and competition factor below
        tier_boost = {"free": 1.0, "basic": 1.08, "premium": 1.18}[listing.seller_tier_helper] * rng.normal(1.0, 0.08)
        rating_boost = (0.85 + 0.06 * listing.seller_rating_helper) * rng.normal(1.0, 0.08)
        condition_boost = 1.1 if (listing.category in ("Electronics & Gadgets", "Fashion & Beauty") and listing.condition == "new") \
            else (1.08 if (listing.category in ("Vehicles", "Property") and listing.condition == "used") else 1.0)

        base_impressions = max(
            3,
            rng.gamma(shape=2.0, scale=15)
            * category_boost * featured_boost * photo_boost * tier_boost * rating_boost
            * condition_boost * listing.quality_helper * listing.competition_helper,
        )

        engagement = CATEGORY_ENGAGEMENT[listing.category]

        for day_offset in range(n_days):
            metric_date = listing.created_date + dt.timedelta(days=day_offset)
            if metric_date > TODAY:
                break

            # decay: interest drops off after the first ~5 days, weekly seasonality bump on weekends
            decay = max(0.15, 1.0 - 0.06 * day_offset)
            weekend_bump = 1.25 if metric_date.weekday() >= 5 else 1.0
            season_mult = CATEGORY_SEASONALITY.get(listing.category, {}).get(metric_date.month, 1.0)
            noise = rng.lognormal(mean=0.0, sigma=0.32)  # fat-tailed day-to-day noise (occasional spikes/duds)

            impressions = max(0, int(base_impressions * decay * weekend_bump * season_mult * clip(noise, 0.15, 4.0)))
            views = int(impressions * clip(rng.normal(0.55, 0.1), 0.1, 0.95))

            click_rate = clip(rng.normal(engagement["click"], 0.03), 0.005, 0.4)
            clicks = int(views * click_rate)
            chats_started = int(clicks * clip(rng.normal(engagement["chat"], 0.15), 0, 1))
            phone_reveals = int(clicks * clip(rng.normal(engagement["phone"], 0.15), 0, 1))
            favorites_added = int(views * clip(rng.normal(engagement["favorite"], 0.02), 0, 0.3))
            search_rank_avg = round(clip(rng.normal(18 if listing.is_featured else 40, 12), 1, 200), 1)

            ctr_pct = round((clicks / views * 100) if views > 0 else 0.0, 2)

            rows.append({
                "metric_id": f"MTR-{metric_counter:08d}",
                "listing_id": listing.listing_id,
                "date": metric_date,
                "impressions": impressions,
                "views": views,
                "clicks": clicks,
                "ctr_pct": ctr_pct,
                "chats_started": chats_started,
                "phone_reveals": phone_reveals,
                "favorites_added": favorites_added,
                "search_rank_avg": search_rank_avg,
            })
            metric_counter += 1

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 4. Ad campaigns
# --------------------------------------------------------------------------

CAMPAIGN_TYPES = ["featured_listing", "bump_up", "search_boost", "homepage_banner", "category_spotlight"]
CAMPAIGN_TYPE_BUDGET = {
    "featured_listing": (100_000, 1_500_000),
    "bump_up": (50_000, 400_000),
    "search_boost": (200_000, 2_500_000),
    "homepage_banner": (2_000_000, 20_000_000),
    "category_spotlight": (1_000_000, 8_000_000),
}


def generate_ad_campaigns(rng: np.random.Generator, sellers: pd.DataFrame, listings: pd.DataFrame) -> pd.DataFrame:
    # advertiser propensity: a noisy logistic function of SEVERAL weak, only
    # partially-overlapping factors (tier, category, seller type, tenure, the
    # latent hustle trait) plus substantial idiosyncratic noise — not a clean
    # lookup on a single column. This keeps ad adoption a real but imperfectly
    # predictable pattern instead of a deterministic tier->ads mapping.
    tier_logit = sellers["account_tier"].map({"free": -2.0, "basic": 0.3, "premium": 1.4}).to_numpy()
    category_logit = sellers["primary_category"].map(CATEGORY_AD_AFFINITY).fillna(0.0).to_numpy()
    type_logit = sellers["seller_type"].map(SELLER_TYPE_AD_AFFINITY).to_numpy()
    tenure_logit = np.where(sellers["tenure_years_helper"] >= 1.0, 0.35,
                             np.where(sellers["tenure_years_helper"] >= 0.5, 0.1, -0.2))
    hustle_logit = (sellers["hustle_helper"].to_numpy() - 0.5) * 1.0
    noise = rng.normal(0, 1.0, size=len(sellers))

    logit = tier_logit + category_logit + type_logit + tenure_logit + hustle_logit + noise
    advertiser_prob = sigmoid(logit)
    is_advertiser = rng.random(len(sellers)) < advertiser_prob

    listings_by_seller = listings.groupby("seller_id")["listing_id"].apply(list).to_dict()

    rows = []
    campaign_counter = 1
    for seller, advertises in zip(sellers.itertuples(), is_advertiser):
        if not advertises:
            continue
        n_campaigns = int(clip(rng.poisson(2), 1, 8))
        seller_listings = listings_by_seller.get(seller.seller_id, [])

        for _ in range(n_campaigns):
            campaign_id = f"CMP-{campaign_counter:06d}"
            campaign_counter += 1
            campaign_type = rng.choice(CAMPAIGN_TYPES)

            listing_id = None
            if campaign_type in ("featured_listing", "bump_up", "search_boost") and seller_listings:
                listing_id = rng.choice(seller_listings)

            start_date = random_date(rng, max(seller.registration_date, TODAY - dt.timedelta(days=270)), TODAY)
            duration = int(clip(rng.exponential(10), 1, 60))
            end_date = min(TODAY, start_date + dt.timedelta(days=duration))
            status = "active" if end_date >= TODAY else weighted_choice(rng, ["completed", "paused"], [0.85, 0.15])

            lo, hi = CAMPAIGN_TYPE_BUDGET[campaign_type]
            budget = int(round(rng.uniform(lo, hi), -3))
            spend_ratio = clip(rng.normal(0.8, 0.15), 0.1, 1.0)
            spend = int(budget * spend_ratio)

            category = seller.primary_category
            cpm_factor = CATEGORY_CPM_FACTOR.get(category, 1.0)
            season_mult = CATEGORY_SEASONALITY.get(category, {}).get(start_date.month, 1.0)
            # campaign-level latent "creative/execution quality" — same spend can
            # perform very differently depending on ad copy, targeting, timing
            creative_quality = rng.lognormal(mean=0.0, sigma=0.4)
            # diminishing returns: impressions grow sub-linearly with spend (auction
            # dynamics push effective CPM up as budget increases), not a flat rate.
            # Constant calibrated so a ~Rp750k campaign lands around ~5,000 impressions,
            # in the same ballpark as the old linear spend/150 rule it replaced.
            impressions = int(max(50, 0.026 * (spend ** 0.90) / cpm_factor * season_mult * creative_quality
                                   * clip(rng.lognormal(0, 0.25), 0.3, 3.0)))

            # CTR is driven by the placement, modulated by creative quality —
            # not by the category's organic engagement rate.
            ctr_base = CAMPAIGN_CTR_BASE[campaign_type]
            click_rate = clip(
                rng.normal(ctr_base, ctr_base * 0.35) * (0.7 + 0.6 * creative_quality), 0.0005, 0.06
            )
            clicks = int(impressions * click_rate)

            conv_rate = clip(rng.normal(0.15, 0.07), 0, 0.6)
            # campaigns tied to a genuinely strong organic listing get a small halo;
            # this links ad_campaigns to listing quality without being deterministic
            if listing_id is not None:
                listing_quality = listings.loc[listings["listing_id"] == listing_id, "quality_helper"]
                if len(listing_quality) and listing_quality.iloc[0] > 1.3:
                    conv_rate = clip(conv_rate * 1.2, 0, 0.7)
            conversions = int(clicks * conv_rate)

            rows.append({
                "campaign_id": campaign_id,
                "seller_id": seller.seller_id,
                "listing_id": listing_id,
                "campaign_name": f"{campaign_type.replace('_', ' ').title()} - {start_date.strftime('%b %Y')}",
                "campaign_type": campaign_type,
                "start_date": start_date,
                "end_date": end_date,
                "status": status,
                "budget_idr": budget,
                "spend_idr": spend,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
            })

    return pd.DataFrame(rows), set(sellers.loc[is_advertiser, "seller_id"])


# --------------------------------------------------------------------------
# 5. Sales activities
# --------------------------------------------------------------------------

ACTIVITY_TYPES = ["cold_call", "email", "meeting", "demo", "proposal_sent", "follow_up", "renewal_call"]
CHANNELS = {"cold_call": "phone", "email": "email", "meeting": "in_person", "demo": "video_call",
            "proposal_sent": "email", "follow_up": "phone", "renewal_call": "phone"}
OUTCOMES = ["interested", "not_interested", "converted", "no_response", "follow_up_scheduled"]
DEAL_STAGES = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


def generate_sales_activities(rng: np.random.Generator, sellers: pd.DataFrame, advertiser_ids: set,
                               listings: pd.DataFrame) -> pd.DataFrame:
    # IMPORTANT: contact probability is built ONLY from things a sales rep would
    # plausibly see or be assigned (tier, seller type, listing COUNT as a coarse,
    # noisy size proxy, tenure, a random territory-coverage flag, and whether the
    # seller already advertises). It deliberately never looks at true organic
    # traction (listing_metrics views) — that number isn't something a rep queries
    # before dialing, and using it here would bake the "opportunity" label straight
    # into its own predictor. Any correlation between contact and true traction
    # that shows up later is therefore indirect (via tier/type/size), not encoded.
    listing_counts = listings.groupby("seller_id").size().reindex(sellers["seller_id"]).fillna(0)
    count_norm = np.minimum(listing_counts.to_numpy(), 30) / 30.0

    # each seller's territory is "in rotation" this quarter or not — a capacity
    # constraint on the sales team that has nothing to do with seller quality
    territory_active = rng.random(len(sellers)) < 0.65

    tier_logit = sellers["account_tier"].map({"free": -0.3, "basic": 0.2, "premium": 0.6}).to_numpy()
    type_logit = sellers["seller_type"].map(SELLER_TYPE_CONTACT_AFFINITY).to_numpy()
    tenure_logit = np.minimum(sellers["tenure_years_helper"].to_numpy(), 4) * 0.12
    count_logit = count_norm * 0.9
    territory_logit = np.where(territory_active, 0.3, -1.6)
    is_adv_arr = sellers["seller_id"].isin(advertiser_ids).to_numpy()
    advertiser_logit = np.where(is_adv_arr, 1.6, 0.0)  # existing spenders get relationship/renewal attention
    noise = rng.normal(0, 0.9, size=len(sellers))

    logit = tier_logit + type_logit + tenure_logit + count_logit + territory_logit + advertiser_logit + noise - 1.1
    contact_prob = sigmoid(logit)

    # category-appropriate deal-value baseline (potential ad spend should track
    # what the seller actually transacts in, not a flat number for everyone)
    category_price_mid = {cat: int(np.sqrt(spec["price_range"][0] * spec["price_range"][1]) * 0.02)
                           for cat, spec in CATEGORIES.items()}

    rows = []
    activity_counter = 1

    for seller, prob, is_adv in zip(sellers.itertuples(), contact_prob, is_adv_arr):
        if rng.random() >= prob:
            continue

        n_touches = int(clip(rng.poisson(2.2 if is_adv else 1.3), 1, 7))
        stage_idx = 0
        base_value = category_price_mid.get(seller.primary_category, 500_000)
        deal_value_base = int(clip(rng.lognormal(np.log(max(base_value, 50_000)), 0.7), 50_000, 20_000_000))

        touch_date = random_date(rng, max(seller.registration_date, TODAY - dt.timedelta(days=180)), TODAY)
        for t in range(n_touches):
            activity_id = f"ACT-{activity_counter:06d}"
            activity_counter += 1

            activity_type = rng.choice(ACTIVITY_TYPES) if t == 0 else rng.choice(
                ["follow_up", "demo", "proposal_sent", "renewal_call"])
            channel = CHANNELS[activity_type]

            # deal stage progresses (roughly) with each successive touch
            stage_idx = min(stage_idx + int(rng.random() < 0.6), len(DEAL_STAGES) - 1)
            deal_stage = DEAL_STAGES[stage_idx]

            if deal_stage == "closed_won":
                outcome = "converted"
            elif deal_stage == "closed_lost":
                outcome = "not_interested"
            else:
                outcome = weighted_choice(rng, OUTCOMES[:2] + OUTCOMES[3:], [0.35, 0.15, 0.30, 0.20])

            next_follow_up = None
            if outcome in ("interested", "follow_up_scheduled") and deal_stage not in ("closed_won", "closed_lost"):
                next_follow_up = touch_date + dt.timedelta(days=int(rng.integers(3, 21)))

            rows.append({
                "activity_id": activity_id,
                "seller_id": seller.seller_id,
                "sales_rep": rng.choice(SALES_REPS),
                "activity_date": touch_date,
                "activity_type": activity_type,
                "channel": channel,
                "outcome": outcome,
                "deal_stage": deal_stage,
                "potential_deal_value_idr": deal_value_base,
                "next_follow_up_date": next_follow_up,
            })

            touch_date = min(TODAY, touch_date + dt.timedelta(days=int(rng.integers(4, 30))))

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate the OLX Ads Intelligence synthetic dataset.")
    parser.add_argument("--out", default="data/raw", help="output directory for CSVs")
    parser.add_argument("--seed", type=int, default=RNG_SEED, help="random seed")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    fake = Faker("id_ID")
    Faker.seed(args.seed)

    print("Generating sellers...")
    sellers = generate_sellers(rng, fake)

    print("Generating listings...")
    listings = generate_listings(rng, sellers)

    print("Generating listing_metrics...")
    listing_metrics = generate_listing_metrics(rng, listings)

    print("Generating ad_campaigns...")
    ad_campaigns, advertiser_ids = generate_ad_campaigns(rng, sellers, listings)

    print("Generating sales_activities...")
    sales_activities = generate_sales_activities(rng, sellers, advertiser_ids, listings)

    # strip internal helper columns before export
    sellers_out = sellers.drop(columns=["listings_lambda_helper", "hustle_helper", "tenure_years_helper"])
    listings_out = listings.drop(columns=["seller_type_helper", "seller_tier_helper", "seller_rating_helper",
                                           "quality_helper", "competition_helper"])

    sellers_out.to_csv(out_dir / "sellers.csv", index=False)
    listings_out.to_csv(out_dir / "listings.csv", index=False)
    listing_metrics.to_csv(out_dir / "listing_metrics.csv", index=False)
    ad_campaigns.to_csv(out_dir / "ad_campaigns.csv", index=False)
    sales_activities.to_csv(out_dir / "sales_activities.csv", index=False)

    # ---------------- integrity checks ----------------
    assert listings_out["seller_id"].isin(sellers_out["seller_id"]).all(), "orphan seller_id in listings"
    assert listing_metrics["listing_id"].isin(listings_out["listing_id"]).all(), "orphan listing_id in listing_metrics"
    assert ad_campaigns["seller_id"].isin(sellers_out["seller_id"]).all(), "orphan seller_id in ad_campaigns"
    assert ad_campaigns.loc[ad_campaigns["listing_id"].notna(), "listing_id"].isin(listings_out["listing_id"]).all(), \
        "orphan listing_id in ad_campaigns"
    assert sales_activities["seller_id"].isin(sellers_out["seller_id"]).all(), "orphan seller_id in sales_activities"
    assert (ad_campaigns["spend_idr"] <= ad_campaigns["budget_idr"]).all(), "spend exceeds budget"
    assert (ad_campaigns["end_date"] >= ad_campaigns["start_date"]).all(), "end_date before start_date"

    print("\nAll referential integrity checks passed.\n")
    print("Row counts:")
    print(f"  sellers:           {len(sellers_out):,}")
    print(f"  listings:          {len(listings_out):,}")
    print(f"  listing_metrics:   {len(listing_metrics):,}")
    print(f"  ad_campaigns:      {len(ad_campaigns):,}")
    print(f"  sales_activities:  {len(sales_activities):,}")
    print(f"\nAdvertiser sellers: {len(advertiser_ids):,} / {len(sellers_out):,} "
          f"({len(advertiser_ids) / len(sellers_out):.1%})")
    print(f"Output written to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
