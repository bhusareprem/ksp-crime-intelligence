#!/usr/bin/env python3
"""Start the KSP Crime Intelligence web server (FastAPI + chat UI)."""

import sys
from pathlib import Path

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))

from src.chatbot.llm_config import load_env

load_env(PROJECT)

if __name__ == "__main__":
    import os
    import uvicorn

    # Catalyst AppSail provides the port via X_ZOHO_CATALYST_LISTEN_PORT;
    # locally we default to 8000 on loopback.
    port = int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT", "8000"))
    host = "0.0.0.0" if "X_ZOHO_CATALYST_LISTEN_PORT" in os.environ else "127.0.0.1"

    print("=" * 60)
    print("KSP Crime Intelligence Web UI")
    print("=" * 60)
    print(f"Open in browser: http://127.0.0.1:{port}")
    print(f"API docs:        http://127.0.0.1:{port}/docs")
    print()
    print("LLM setup: copy .env.example to .env and add your API key")
    print("Press Ctrl+C to stop\n")
    uvicorn.run("api.main:app", host=host, port=port, reload=False)
