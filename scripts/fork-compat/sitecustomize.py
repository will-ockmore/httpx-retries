"""Redirect ``import httpx`` to a community fork, for CI compatibility testing.

This is *only* active when this directory is on ``PYTHONPATH`` **and** the
``HTTPX_BACKEND`` environment variable is set. Python imports ``sitecustomize``
automatically at interpreter startup — before pytest or ``httpx_retries`` import
``httpx`` — so the alias is guaranteed to win regardless of import order.

Used by ``scripts/test-fork``; a no-op in normal runs.
"""

import os
import sys

_backend = os.environ.get("HTTPX_BACKEND")

if _backend == "httpxyz":
    # httpxyz registers itself as sys.modules["httpx"] on first import.
    import httpxyz  # type: ignore[import-not-found]  # noqa: F401
elif _backend == "httpx2":
    # httpx2 is a rename fork with no auto-alias, so wire it up ourselves.
    # It preserves httpx's public API, which is all httpx-retries touches.
    import httpx2  # type: ignore[import-not-found]

    sys.modules["httpx"] = httpx2
