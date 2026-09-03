# The OLAP layer

The platform runs two database engines, and each does the job it is good at.

| | Engine | Role | Where |
|---|---|---|---|
| **Operational** | SQLite | Serves every request: the queue, seller detail, the write path for logging an activity | `olxads/db.py`, `olxads/analytics.py` |
| **Analytical** | DuckDB | Computes the Deep Dive analyses over the full 286k-row metric fact, at build time | `olxads/olap.py` |

DuckDB never runs at request time. It produces six small result sets, those are
written into SQLite as `olap_*` tables, and the API serves them like any other
query. So the deployed function ships neither DuckDB nor the warehouse — a test
asserts it (`tests/test_olap.py::test_serving_path_does_not_import_duckdb`).

```
data/raw/*.csv ──► DuckDB star schema ──► 6 result sets ──► SQLite olap_* tables ──► /api/analytics/olap
                   (data/processed/olxads.duckdb)            (inside the 13 MB deploy artefact)
```

## Why a second engine

SQLite is the right operational store here: one file, no server, indexed point
lookups, and a writable path so logging a call genuinely rescores an account.
It is the wrong tool for the Deep Dive questions, which are full scans of the
metric fact with window frames, ordered aggregates and quantiles.

The claim is measurable rather than asserted:

```bash
python scripts/build_olap.py --benchmark
```

```
          engine          rows     wall time
          ----------------------------------
          sqlite            45      793.2 ms
          duckdb            45       54.2 ms

          DuckDB is 14.6x faster on the same analysis.
          Results identical: True
```

That is the demand-decay analysis, which SQLite *can* express. Two of the six
cannot be written in SQLite at all:

- **`quantile_cont`** — SQLite has no percentile function, so the traction
  distribution would need a full sort pulled into Python.
- **`ASOF JOIN`** — a point-in-time lookup ("the seller's trailing traction as
  it stood on the day of the call"). The SQLite equivalent is a correlated
  subquery per row.

The second reason is subtler and matters more: the deployment artefact **drops
the raw `listing_metrics` table** to stay under 13 MB. Once it is gone, the
decay analysis is impossible at request time on any engine. Computing it at
build time is not just faster, it is the only way the deployed app can show it
at all.

## The six analyses

Each answers one commercial question. The SQL is in `olxads/olap.py` and is
meant to be read — it runs unchanged in the DuckDB CLI against the same
warehouse.

| Table | Question | What makes it OLAP |
|---|---|---|
| `olap_listing_decay` | How fast does a listing's organic demand fall off after posting? | 286k-row scan joined to listing age; `first_value` window to index each curve to its own week 0 |
| `olap_demand_weekly` | What is each category's weekly demand, smoothed? | `AVG ... ROWS BETWEEN 3 PRECEDING`, `LAG` for week-on-week |
| `olap_category_momentum` | Which categories are accelerating? | `dense_rank` over weeks, conditional aggregation across two windows |
| `olap_revenue_concentration` | How concentrated is ad revenue? | Running `SUM() OVER (ORDER BY spend DESC)` — a Lorenz curve |
| `olap_traction_percentiles` | How is organic demand distributed, and do non-advertisers really lag? | `quantile_cont` with `FILTER` clauses |
| `olap_conversion_by_traction` | Did past outreach convert better on high-traction sellers? | `ASOF JOIN` against a 28-day rolling window |

### What they found

- Organic reach falls to **47% of week-zero levels by week one and 15% by week
  three**, in every category. The same shape everywhere makes it a property of
  the ranking surface rather than of any one market — and the honest basis for
  selling Bump Up and Search Boost.
- The top **5% of advertisers carry ~21% of revenue**, the top 20% carry ~57%.
- **137 sellers who have never advertised** already out-perform the median
  *paying* seller in their own category — about **Rp105M/month of headroom** in
  accounts that look, on demand alone, like existing customers.
- Conversion rises **4×** from the lowest pre-call traction quintile to the
  best (0.79% → 3.16%). The opportunity model's core premise, validated against
  outreach that happened before the model existed.

## Star schema

Loaded straight from the CSVs by DuckDB's own reader — no pandas in this path,
so the warehouse builds from a clean checkout with nothing but `duckdb`
installed.

```
dim_seller ──┐
dim_listing ─┼── fact_listing_metrics   (286,461 rows, listing x day)
dim_date ────┤── fact_campaign          (1,195)
             └── fact_activity          (1,265)

seller_scores   copied from SQLite, so the score has one definition
```

`seller_scores` is mirrored across with stdlib `sqlite3` rather than DuckDB's
`sqlite_scanner` extension: that extension is downloaded on first use, and a
build should not need network access.

## Running it

The OLAP pass is part of the normal build and is skipped with a message if
DuckDB is not installed:

```bash
python run.py --rebuild          # includes the DuckDB pass
python run.py --deploy-build     # slim artefact, olap_* tables included

python -m olxads.olap            # the pass on its own
python scripts/build_olap.py --benchmark   # ...plus the SQLite comparison
```

Ad-hoc querying against the warehouse:

```bash
duckdb data/processed/olxads.duckdb
```

```sql
SELECT category, week_since_post, retention_index
FROM (...)   -- paste any query from olxads/olap.py
```

## Determinism

Both database builds must produce byte-identical analytics — a test asserts it
(`test_deploy_database_serves_identical_analytics`). That caught a real defect:
`NTILE(5) OVER (ORDER BY views_at_call)` splits ties arbitrarily, and several
hundred calls landed on sellers with identical trailing views, so two builds of
the *same data* produced different quintile boundaries. The fix is a tiebreaker
column, not decoration:

```sql
NTILE(5) OVER (ORDER BY views_at_call, activity_id)
```

A related trap, worth knowing if you extend the catalog: DuckDB's `/` is always
float division, and `CAST(<double> AS INTEGER)` **rounds**. So
`CAST(date_diff('day', a, b) / 7 AS INTEGER)` silently shifts every bucket by
half a week versus the same expression in SQLite. Use `//` for integer
division.

## Adding an analysis

1. Add the SQL to `QUERIES` in `olxads/olap.py`, keyed by its table name.
2. Add that name to `OLAP_TABLES` in the same file and in `olxads/analytics.py`
   — `test_catalog_and_table_list_agree` fails if the three drift apart.
3. Read it in `olap_analytics()` and surface it in `web/src/views/DeepDive.tsx`.
4. Rebuild: `python run.py --rebuild && python run.py --deploy-build`.
