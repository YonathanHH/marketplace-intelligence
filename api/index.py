"""Vercel serverless entrypoint.

Vercel treats any `.py` file under `api/` as a serverless function and serves
the module-level ASGI callable named `app`. Everything else — the built React
bundle in `web/dist` — is served straight from Vercel's CDN, so the function
only ever handles `/api/*`.

Two details this file exists to handle:

1. **sys.path** — the function is executed with `api/` context, so the repo
   root is added explicitly to make `import olxads` work.
2. **Path normalisation** — depending on how a host rewrites `/api/*` onto this
   function, the ASGI scope can arrive either with the original path
   (`/api/leads`) or collapsed onto the function's own route (`/api/index`).
   The routes are declared with the `/api` prefix, so the middleware below
   repairs the collapsed form instead of 404-ing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from olxads.api import app as _app  # noqa: E402

_FUNCTION_ROUTE = "/api/index"


class NormalizeApiPath:
    """Repair the request path when the host collapses it onto /api/index."""

    def __init__(self, application):
        self.app = application

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == _FUNCTION_ROUTE or path.startswith(_FUNCTION_ROUTE + "/"):
                remainder = path[len(_FUNCTION_ROUTE):]
                scope = {**scope, "path": "/api" + remainder}
            elif not path.startswith("/api"):
                # Host stripped the prefix before invoking the function.
                scope = {**scope, "path": "/api" + path if path != "/" else "/api"}
        await self.app(scope, receive, send)


app = NormalizeApiPath(_app)
