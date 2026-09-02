# Deployment (Vercel)

The platform deploys as two pieces on one origin:

- **Static frontend** — the Vite build in `web/dist`, served from Vercel's CDN.
- **Python serverless function** — `api/index.py` exposes the FastAPI app and
  handles `/api/*` only.

```
Request
  ├── /assets/*, /index.html   → CDN (static, cached)
  ├── /api/*                   → Python function → SQLite (bundled, read-only)
  └── anything else            → /index.html   (SPA client-side routing)
```

## Deploy it

```bash
npm i -g vercel      # once
vercel               # preview deployment
vercel --prod        # production
```

Or import the GitHub repo at [vercel.com/new](https://vercel.com/new) — the
committed `vercel.json` supplies the build command, output directory, function
config and routes, so no dashboard settings are required.

## The two constraints, and how they're handled

### 1. Bundle size — 250 MB uncompressed

The naive version of this project would not have fit comfortably:

| | Size |
|---|---|
| pandas | 59.9 MB |
| numpy | 30.7 MB |
| Full SQLite database | 58.9 MB |
| **Total** | **~150 MB** before FastAPI, wheels, or pip overhead |

Two changes fixed it:

**pandas and numpy are build-time only.** The scoring rules were extracted into
`olxads/rules.py`, which has *no third-party imports*. The batch pipeline
(`olxads/scoring.py`) applies those rules across a DataFrame; the live write
path (`olxads/actions.py`) applies the same functions to one seller. The
serving path — `api → analytics → db → rules` — is stdlib `sqlite3` plus
FastAPI. `requirements.txt` (what Vercel installs) therefore contains only
`fastapi` and `pydantic`; everything else lives in `requirements-dev.txt`.

This is enforced by a test, not just intended:
`tests/test_deployment.py::test_serving_path_has_no_pandas_or_numpy` imports the
API in a subprocess with pandas and numpy blocked at the import hook level.

**The database ships pre-aggregated.** `listing_metrics` is 286,461 rows and
54 MB, but the API never reads a raw metric row — every query is a roll-up. The
ETL materialises three aggregates (`listing_totals`, `marketplace_daily`,
`seller_daily_traction`) and *all* queries read those, locally and in
production alike. A `--deploy` build then drops the raw table:

```bash
python run.py --deploy-build     # → data/processed/olxads-deploy.db (13.2 MB)
```

`test_deploy_database_serves_identical_analytics` asserts the slim artefact
returns byte-identical analytics to the full one, so the optimisation can't
silently change a reported number.

Final function bundle: **~13 MB database + ~11 MB dependencies.**

### 2. Read-only filesystem

Serverless filesystems are read-only apart from the temp directory, but logging
an activity writes to SQLite. `olxads/runtime.py` detects a serverless host (the
`VERCEL` env var) and copies the database into the writable temp dir once per
instance.

The consequence, stated plainly: **writes are real but instance-local.** Logging
a call rescores the account and persists for the life of that warm instance,
then resets on a cold start. That is the correct trade-off for a public demo —
visitors get a genuinely interactive tool that always returns to a clean state.
Backing it with a durable store (Turso, Neon, Postgres) would mean changing
`olxads/db.py`'s connection helper and nothing else; the query layer is already
parameterised and isolated.

## Committed build artefact

`data/processed/olxads-deploy.db` is committed to git, because Vercel builds
from the repository and the function needs the database at runtime. The full
local database is gitignored. Regenerate the committed artefact whenever the
dataset or scoring model changes:

```bash
python run.py --regenerate       # new dataset + full local rebuild
python run.py --deploy-build     # refresh the slim artefact
git add data/processed/olxads-deploy.db
```

## Configuration reference

**`vercel.json`** — `routes` is used rather than `rewrites` because it preserves
the original request path when dispatching to the function, which an ASGI app
needs in order to route. `{ "handle": "filesystem" }` serves static assets
first, so only genuine misses fall through to the SPA fallback.

**`api/index.py`** — adds the repo root to `sys.path` and wraps the app in
`NormalizeApiPath`, which repairs the request path if the host collapses
`/api/leads` onto the function's own route or strips the `/api` prefix. Four
routing shapes are covered by parametrised tests, so the deployment does not
depend on one specific host behaviour.

**`.vercelignore`** — keeps tests, scripts, docs, the raw CSVs (19 MB) and the
full database out of the bundle.

## Local development is unchanged

```bash
pip install -r requirements-dev.txt
python run.py                        # API + built UI on :8000
cd web && npm run dev                # or Vite with hot reload on :5173
```

Locally the API uses the full database if present and falls back to the slim
one, so a fresh clone works before anything is generated.
