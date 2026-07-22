"""Quick test for analytics endpoints."""
import threading, time, requests, sys

import uvicorn
from api.main import app

def run():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="error")

t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(3)

ENDPOINTS = [
    "/api/analytics/trends",
    "/api/analytics/hotspots",
    "/api/analytics/network",
    "/api/analytics/predictions",
    "/api/analytics/district-breakdown",
    "/api/analytics/cases-summary",
    "/api/analytics/behavioral-profile",
    "/api/audit",
    "/api/health",
]

all_ok = True
for ep in ENDPOINTS:
    try:
        r = requests.get(f"http://127.0.0.1:8765{ep}", timeout=15)
        status = "OK" if r.status_code == 200 else f"FAIL {r.status_code} {r.text[:80]}"
        print(f"  {ep}: {status}")
        if r.status_code != 200:
            all_ok = False
    except Exception as e:
        print(f"  {ep}: ERROR {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
