# OLX Ads Intelligence

A sales-intelligence platform for an OLX-style classifieds marketplace. It finds
sellers who are already earning real buyer demand without paying for it,
explains **why** each one is an opportunity, estimates **what they're worth**,
and tells the Ads Sales team **who to call next**.

Built end-to-end: synthetic data generation → leakage audit → opportunity model →
analytics → REST API → React dashboard.

![Stack](https://img.shields.io/badge/python-3.13-blue) ![Stack](https://img.shields.io/badge/FastAPI-0.14x-009688) ![Stack](https://img.shields.io/badge/React-18-61dafb) ![Stack](https://img.shields.io/badge/TypeScript-5.6-3178c6) ![Tests](https://img.shields.io/badge/tests-76%20passing-brightgreen) ![Deploy](https://img.shields.io/badge/deploy-Vercel%20ready-black)

---

## The problem it solves

A marketplace's ad sales team can only call so many sellers. They tend to work
the accounts they already know — existing advertisers and big obvious names —
while the most interesting prospects hide in plain sight: sellers whose listings
are pulling thousands of views and hundreds of buyer conversations *organically*,
who have never spent a rupiah on promotion, and whom nobody has ever phoned.

On the current dataset the platform finds:

| | |
|---|---|
| **Rp867M/month** | untapped ad revenue (Rp10.4B annualised) |
| **245 accounts** | Hot/Warm sellers who have **never been contacted** |
| **3.8%** | of past outreach landed on accounts worth calling |
| **575** | low-value accounts the team contacted instead |

That last pair is the product's core finding: effort is being spent, just not
where the money is.

## The four pillars

Every seller is scored on four dimensions, each from a different part of the data:

| Pillar | Question | Source |
|---|---|---|
| **Marketplace** | How much organic demand do they earn? | `listings` + `listing_metrics` |
| **Seller** | Are they worth selling to — trusted, responsive, established? | `sellers` |
| **Advertising** | How under-monetised are they versus their peers? | `ad_campaigns` |
| **Opportunity** | How overdue are they for outreach? | `sales_activities` |

These combine **multiplicatively**, not additively — traction is the base and
the other pillars dampen it. That distinction matters: since "never advertised +
never contacted" describes most of the marketplace, a weighted sum would push
almost everyone into the top tiers. See
[docs/OPPORTUNITY_SCORING.md](docs/OPPORTUNITY_SCORING.md).

## What each lead is worth

The platform doesn't invent a spend figure. For each seller it asks what
*comparable sellers already pay* — the median monthly spend of real advertisers
in the same category and traction band — and treats the difference as headroom.
Then it applies a win probability derived from that segment's historical
conversion rate, shrunk toward the base rate so a thin segment can't post a
fake 100%.

The UI shows the actual peer set behind every estimate, so the number is
auditable rather than a black box.

## Running it

```bash
# 1. Backend
python -m venv .venv
source .venv/Scripts/activate      # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt

# 2. Frontend (production build, served by FastAPI at one origin)
cd web && npm install && npm run build && cd ..

# 3. Go — generates data and builds the database on first run
python run.py
```

> `requirements.txt` holds only the serverless **runtime** deps (FastAPI +
> Pydantic). `requirements-dev.txt` adds pandas, numpy, Faker, uvicorn and
> pytest for local work. See [Deployment](#deployment) for why they're split.

Open **http://127.0.0.1:8000** · API docs at **/docs**

For frontend development with hot reload, run the API and Vite side by side:

```bash
python run.py              # terminal 1 — API on :8000
cd web && npm run dev      # terminal 2 — UI on :5173, proxies /api
```

Other entry points:

```bash
python run.py --regenerate         # new dataset + full rebuild
python run.py --rebuild            # rebuild the DB from existing CSVs
python scripts/generate_data.py    # dataset only
python scripts/audit_data.py       # leakage & determinism diagnostics
python scripts/score_opportunities.py   # ranked lead list to CSV
python scripts/build_geo.py        # rebuild the Indonesia map asset
python run.py --deploy-build       # slim database for deployment
python -m pytest -q                # 76 tests
```

## The product

**Overview** — untapped revenue, risk-adjusted pipeline, opportunity mix by tier,
headroom by category, and today's top leads.

**Opportunities** — the working queue. Filter by tier, category, province, seller
type, ad status and contact status; sort any column; search; export the filtered
set to CSV. Filters live in the URL, so a filtered queue is a shareable link.

**Seller 360** — opens over the queue. Four-pillar score breakdown, evidence-backed
talking points a rep can open a call with, the comparable advertisers behind the
revenue estimate, daily traction, listings, campaign history, and an activity
timeline. Logging a call **rescores the account immediately** — a Hot lead that
was just contacted drops out of the queue, because it's now being worked.

**Coverage** — an interactive choropleth of Indonesia showing where sales
effort is and isn't landing. Shade the map by uncovered headroom, missed
priority accounts or coverage rate; hover any province for its full breakdown;
click one to jump straight into that territory's uncontacted queue. Provinces
with no sellers are drawn muted, so the map also shows where the business
simply isn't yet.

**Marketplace / Advertising / Pipeline** — the analytics behind the scores:
demand trends and the featured-listing lift that makes promotion sellable; ad
product efficiency (CTR, CPC, cost per conversion); and pipeline stages,
outcomes and rep performance.

## Data foundation

Five tables, ~300k rows, entirely synthetic — no real data anywhere.

| Table | Rows | Grain |
|---|---|---|
| `sellers` | 1,500 | one per seller account |
| `listings` | 12,311 | one per posted ad |
| `listing_metrics` | 286,461 | listing × day |
| `ad_campaigns` | 1,195 | one per campaign |
| `sales_activities` | 1,265 | one per logged outreach |

The generator was **audited for leakage** before any model was built on it. The
first version computed sales-contact probability directly from the traction
number the platform is meant to predict — a textbook label leak that would let
an "opportunity model" rediscover its own generating formula. That, and three
other over-deterministic relationships, were fixed; `scripts/audit_data.py`
re-checks all of them on any regenerated dataset.

Full details: [docs/DATA_MODEL.md](docs/DATA_MODEL.md) (schema, ERD, and the
leakage audit).

## Deployment

Deploys to Vercel as a static frontend on the CDN plus a Python serverless
function for `/api/*`:

```bash
vercel --prod
```

Two constraints shaped the architecture, and both are enforced by tests rather
than left to intention:

- **Bundle size.** pandas + numpy (90 MB) are build-time only — the scoring
  rules live in a dependency-free `olxads/rules.py` shared by the batch
  pipeline and the live write path, so the serving path is stdlib `sqlite3` +
  FastAPI. A test imports the API with pandas and numpy blocked to keep it
  that way.
- **Database size.** The API never reads a raw metric row, so the ETL
  pre-aggregates `listing_metrics` (286k rows, 54 MB) into three roll-up
  tables that every query uses. The deploy build drops the raw table:
  **58.9 MB → 13.2 MB**, with a test asserting the slim artefact returns
  identical analytics.

Serverless filesystems are read-only, so the database is copied to the temp dir
per instance — logging an activity genuinely works and resets on cold start,
which is the right behaviour for a public demo. Details and the durable-store
migration path: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

## Documentation

- **[docs/DATA_MODEL.md](docs/DATA_MODEL.md)** — schema, ERD, data dictionary, leakage audit
- **[docs/OPPORTUNITY_SCORING.md](docs/OPPORTUNITY_SCORING.md)** — the model, why it multiplies, validation
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — system design and the decisions behind it
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Vercel setup, bundle-size and read-only-FS handling

## Layout

```
olxads/          config · db · rules · scoring · etl · analytics · actions · api · runtime
api/index.py     Vercel serverless entrypoint
scripts/         generate_data · audit_data · score_opportunities
schema/          schema.sql
web/             Vite + React + TypeScript frontend
tests/           76 tests (model properties · API contract · deployment guarantees)
docs/            data model · scoring methodology · architecture · deployment
vercel.json      build, routing and function config
```
