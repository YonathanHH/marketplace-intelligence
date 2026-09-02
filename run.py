"""Launcher for the OLX Ads Intelligence platform.

    python run.py                # serve the API (+ built UI if web/dist exists)
    python run.py --rebuild      # rebuild the database from the CSVs first
    python run.py --regenerate   # regenerate the dataset, then rebuild everything

Bootstraps whatever is missing: if the CSVs or the database are not there yet,
it produces them rather than failing with a stack trace.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from olxads.config import DB_PATH, DEPLOY_DB_PATH, PROJECT_ROOT, RAW_DIR, RAW_TABLES, WEB_DIR


def csvs_present() -> bool:
    return all((RAW_DIR / f"{t}.csv").exists() for t in RAW_TABLES)


def generate_dataset() -> None:
    print("Generating synthetic dataset...")
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_data.py")],
        check=True,
        cwd=PROJECT_ROOT,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="rebuild the database before serving")
    parser.add_argument("--regenerate", action="store_true", help="regenerate the CSVs, then rebuild")
    parser.add_argument(
        "--deploy-build", action="store_true",
        help="build the slim database for deployment and exit (does not serve)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args()

    if args.regenerate or not csvs_present():
        generate_dataset()

    if args.deploy_build:
        from olxads.etl import build_database

        build_database(deploy=True, db_path=DEPLOY_DB_PATH)
        print(
            "\nCommit this file so the deployment can serve it:\n"
            f"  git add {DEPLOY_DB_PATH.relative_to(PROJECT_ROOT).as_posix()}"
        )
        return

    if args.rebuild or args.regenerate or not DB_PATH.exists():
        from olxads.etl import build_database

        build_database()

    dist = WEB_DIR / "dist"
    if not dist.exists():
        print(
            "\nNote: no production UI build found at web/dist.\n"
            "  For development run the Vite dev server in another terminal:\n"
            "      cd web && npm install && npm run dev\n"
            "  ...then open http://localhost:5173\n"
            "  For a single-origin production build:  cd web && npm run build\n"
        )
    else:
        print(f"\nServing UI from {dist}")

    print(f"API docs: http://{args.host}:{args.port}/docs\n")

    import uvicorn

    uvicorn.run(
        "olxads.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
