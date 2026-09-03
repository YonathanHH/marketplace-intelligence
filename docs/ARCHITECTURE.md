# Architecture

## System shape

The system splits cleanly in two. Everything above the line runs once, offline,
and may use heavy libraries. Everything below runs per request and may not.

```
BUILD TIME  (pandas, numpy, duckdb — never deployed)
  scripts/generate_data.py ──► data/raw/*.csv
                                    │
                    olxads/scoring.py│  (applies olxads/rules.py across the population)
                                    ▼
                              olxads/etl.py
                                    │
                                    ├── 5 source tables      (schema/schema.sql)
                                    ├── seller_scores        (one row per seller)
                                    ├── seller_scores_ranked (view: live rank)
                                    ├── aggregates: listing_totals
                                    │               marketplace_daily
                                    │               seller_daily_traction
                                    └── olxads/olap.py ──► DuckDB star schema
                                                            (olxads.duckdb)
                                                              │  6 analyses
                                                              ▼
                                                        olap_* tables
                                    │
                     ┌──────────────┴───────────────┐
              olxads.db (67 MB, local)      olxads-deploy.db (13 MB, committed)
─────────────────────────────────────────────────────────────────────────────
SERVE TIME  (stdlib sqlite3 + FastAPI only)
                     olxads/runtime.py  → picks the DB, copies to /tmp if read-only
                                    │
                     olxads/analytics.py · olxads/actions.py → olxads/rules.py
                                    │
                            olxads/api.py  (FastAPI)
                                    │
                     ┌──────────────┴───────────────┐
            local: run.py + uvicorn        Vercel: api/index.py (function)
                     │                              │
                web/dist served by FastAPI     web/dist served by CDN
```

## Layers

| Module | Responsibility |
|---|---|
| `olxads/config.py` | Paths and every tunable constant (weights, dampener floors, comparable thresholds) |
| `olxads/db.py` | SQLite connection handling, query helpers returning plain dicts |
| `olxads/rules.py` | **The scoring rules themselves — zero third-party imports** |
| `olxads/scoring.py` | Build-time pipeline: applies the rules across the population with pandas |
| `olxads/etl.py` | CSV → validated tables → `seller_scores` → aggregates → OLAP pass → indexes → metadata |
| `olxads/olap.py` | **DuckDB warehouse and the analytical query catalog** — build-time only |
| `olxads/analytics.py` | Every aggregation the product surfaces, as reusable functions |
| `olxads/actions.py` | Write path: log an activity, rescore that seller in place |
| `olxads/runtime.py` | Which database to open, including read-only serverless hosts |
| `olxads/api.py` | HTTP surface, request validation, static hosting of the built UI |
| `api/index.py` | Vercel serverless entrypoint (path normalisation + `sys.path`) |

Analytics live in their own module rather than inline in route handlers, so the
same aggregation can be called from the API, a notebook, or a test without
going through HTTP.

## Decisions worth explaining

**Two engines, one of them build-time.** SQLite serves; DuckDB pre-computes.
The Deep Dive analyses are full scans of the 286k-row metric fact with window
frames, quantiles and an as-of join — the shape a columnar engine exists for,
and 14.6x faster on the one of them SQLite can also express (measured by
`scripts/build_olap.py --benchmark`, which also asserts the two agree
row-for-row). DuckDB never runs at request time: its six result sets are a few
hundred rows in total, so they are materialised into SQLite and served like any
other query. That keeps the serving path stdlib-only and keeps the function
small. It also makes the decay analysis possible *at all* in production, since
the deploy artefact drops the raw metrics table it needs. See
[OLAP.md](OLAP.md).

**SQLite, not Postgres.** The whole dataset is ~300k rows and read-mostly.
SQLite makes the project clone-and-run with no service to provision, while
still giving real indexed SQL and window functions. The data-access layer is
small and parameterised, so moving to Postgres would be a connection change,
not a rewrite.

**Derived data is computed, not stored — with one deliberate exception.**
`seller_scores` *is* materialised, because scoring 1,500 sellers involves
population-wide percentile ranks that are wasteful to recompute per request.
But anything that would go stale from a single write is derived:
- `rank` comes from the `seller_scores_ranked` view (`ROW_NUMBER()`), so logging
  one activity can't leave a gap in the ranking.
- "power seller" is not a column at all; it's derivable from active listing count.

**One scoring rule, two callers — and it pays for itself twice.**
`sales_gap_from_state()`, `composite_score()` and the playbook builders are
pure functions in `olxads/rules.py`. The batch pipeline applies them across a
DataFrame; `actions.py` applies the same functions to a single seller after a
rep logs a call. Neither can drift from the other.

The second payoff is deployment: because `rules.py` has no third-party imports,
the whole serving path (`api → analytics → db → rules`) runs on stdlib
`sqlite3` plus FastAPI. pandas and numpy — 90 MB — are build-time only, which
is what lets the API ship as a small serverless function.
`tests/test_deployment.py` imports the API with both libraries blocked at the
import-hook level, so the property is enforced rather than assumed.

**Aggregates are materialised; the raw fact table is a build input.** Nothing in
the API reads an individual `listing_metrics` row — every query is a roll-up by
listing, by day, or by seller-day. The ETL materialises exactly those three
shapes (`listing_totals`, `marketplace_daily`, `seller_daily_traction`) and all
queries read them, locally and in production alike. Request-time scans drop
from ~286k rows to hundreds, and a deployment build can drop the raw table
entirely (58.9 MB → 13.2 MB) without changing any reported number — asserted by
a test that diffs full-vs-slim analytics output.

**Partial rescoring on write.** Logging an activity only recomputes the sales
pillar and the composite. The other three pillars are population percentiles
that a single phone call genuinely does not move, so recomputing them would be
both slow and wrong.

**The frontend is a separate Vite app, served two ways.** In development, Vite
runs on :5173 and proxies `/api` to FastAPI on :8000. In production,
`npm run build` emits `web/dist` and FastAPI serves it, so everything is
same-origin and the app uses relative URLs in both modes with no config switch.

**The map is a build artefact, not a mapping library.** The Coverage
choropleth needs Indonesian province geometry, which normally means a mapping
library plus a runtime GeoJSON or tile fetch. Instead `scripts/build_geo.py`
takes public-domain Natural Earth 1:50m admin-1 data, isolates Indonesia, drops
sub-pixel islands, runs Ramer-Douglas-Peucker simplification and Mercator-projects
the result into SVG path strings — 44 KB, committed. The component is then plain
SVG: no dependency, no network call, works offline, and themes through the same
CSS variables as everything else. A test asserts every province present in the
data is present in the map, so a rename can't silently drop a territory.

**Route-level code splitting.** The charting library is ~426KB. The opportunity
queue — the view reps actually live in — doesn't need it up front, so views are
lazily imported. Initial JS is ~59KB gzipped; the map asset rides along with
the Coverage chunk and is only fetched when that view is opened.

## Data flow for one request

`GET /api/leads?tier=Hot&category=Vehicles`

1. `api.list_leads` validates and normalises query params (FastAPI/Pydantic).
2. `analytics.list_leads` builds a parameterised `WHERE` clause — user input is
   only ever bound, never interpolated — and runs two queries: one for the
   filtered aggregate, one for the page.
3. Rows come back from `seller_scores_ranked` as dicts and serialise directly.

## Testing

`tests/test_scoring.py` asserts model *properties* rather than fixed numbers —
zero traction can never produce an opportunity, risk-adjusted value can never
exceed headroom, tiers match scores, the opportunity segment exists — so
regenerating the dataset with a new seed doesn't break the suite while a real
regression still does.

`tests/test_api.py` runs against a throwaway copy of the database via a
dependency override, so write-path tests can mutate freely. It covers the
contract (filters actually filter, pagination doesn't overlap, aggregates match
the filtered set), a SQL-injection attempt, and the full log-activity →
rescore → persist cycle.

`tests/test_deployment.py` guards the two properties the serverless deployment
depends on: no pandas/numpy/duckdb in the serving path, and identical analytics
from the slim database. It also covers the four path shapes a host might hand to
the function.

`tests/test_olap.py` asserts that the second engine stays out of the serving
path, and — more importantly — that it agrees with SQLite where both can express
the question. A faster engine returning different numbers is not an
optimisation, it is a second source of truth. The identical-analytics test
earned its keep here: it caught `NTILE` splitting ties non-deterministically, so
two builds of the same data disagreed on quintile boundaries.

`tests/test_design_tokens.py` parses `tokens.css` and asserts every text colour
clears WCAG AA against every surface it can sit on, in both themes, and that no
component hardcodes a hex value. Contrast is the kind of thing that is checked
once by eye and quietly regresses; this makes it a build failure.

```bash
python -m pytest -q     # 101 tests
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for the hosting setup.
