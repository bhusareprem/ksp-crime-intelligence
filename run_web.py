#!/usr/bin/env python3
"""Start the KSP Crime Intelligence web server (FastAPI + chat UI)."""

import sys
from pathlib import Path

PROJECT = Path(__file__).parent

# Print the runtime arch up front so wheel-compatibility issues are obvious in logs.
import platform as _plat
print(f"RUNTIME: python={sys.version.split()[0]} machine={_plat.machine()} "
      f"platform={_plat.platform()}", flush=True)

# Vendored dependencies for Catalyst AppSail: shipped as a single compressed
# deps.zip (few files upload fast), extracted once at startup. Must land on
# sys.path before any third-party import. Harmless locally (no deps.zip there).
_deps = PROJECT / "deps"
_deps_zip = PROJECT / "deps.zip"
if _deps_zip.exists() and not (_deps / ".extracted").exists():
    import zipfile
    print(f"Extracting bundled dependencies from {_deps_zip.name}...", flush=True)
    _deps.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(_deps_zip) as _z:
        _z.extractall(_deps)
    (_deps / ".extracted").touch()
    print("Dependencies extracted.", flush=True)
if _deps.exists():
    sys.path.insert(0, str(_deps))
sys.path.insert(0, str(PROJECT))

from src.chatbot.llm_config import load_env

load_env(PROJECT)

if __name__ == "__main__":
    import os
    import uvicorn

    # Catalyst AppSail provides the port via X_ZOHO_CATALYST_LISTEN_PORT (its default
    # is 9000). Always bind 0.0.0.0 so the platform can reach the container.
    in_catalyst = any(k.startswith(("X_ZOHO", "X_ZC")) for k in os.environ)
    default_port = "9000" if in_catalyst else "8000"
    port = int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT") or os.getenv("PORT") or default_port)
    host = "0.0.0.0"

    print("=" * 60)
    print("KSP Crime Intelligence Web UI")
    print(f"Binding {host}:{port}")
    print("=" * 60, flush=True)

    # Import the app up front so any import error is printed to the logs
    # (instead of a silent 'startup failed / check command or port').
    try:
        from api.main import app  # noqa: F401
    except Exception as exc:
        import traceback
        print("FATAL: failed to import api.main:app", flush=True)
        traceback.print_exc()
        raise

    uvicorn.run(app, host=host, port=port, reload=False)
