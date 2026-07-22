# Deploying KSP Crime Intelligence to Zoho Catalyst

Datathon 2026 — deployment via Catalyst is **mandatory**. This guide gets the app
live on **AppSail (managed Python runtime)** in the **Development environment**
(do NOT push to Production — it requires a credit card; Development is enough
for the hackathon).

---

## Architecture on Catalyst

| Piece | Where it runs |
|---|---|
| FastAPI backend + web UI | **AppSail** (managed Python runtime, one service) |
| 500k-FIR analytics DB | Compacted `ksp_fir.duckdb` (48 MB) bundled with the app |
| NCRB / court / case-knowledge DBs | Bundled SQLite/DuckDB files (~27 MB) |
| LLM | Groq/Gemini via env keys today → **QuickML LLM Serving** (Qwen 2.5-14B) as Catalyst-native provider |
| Chats / audit persistence | SQLite on instance disk (hackathon OK) → **Data Store** for finale |
| Kannada OCR (roadmap) | **Zia OCR** (supports Kannada) |

---

## One-time setup

1. **Sign up** at https://catalyst.zoho.com — pick the **IN data center**
   (QuickML LLM serving is available in IN; also lowest latency for judges).
2. Create a project, e.g. `ksp-crime-intelligence`. Stay in **Development**.
3. Install the CLI (needs Node.js ≥ 14):
   ```bash
   npm install -g zcatalyst-cli
   catalyst login
   ```

## Build the deploy bundle

From the repo root:

```bash
python scripts/build_appsail.py
```

This stages `dist_appsail/` (~76 MB): `api/`, `src/`, `frontend/`, `run_web.py`,
a lean `requirements.txt`, and the databases — with `ksp_fir.duckdb` compacted
from 482 MB → 48 MB. The 16 GB of raw source CSVs stay behind.

## Initialize + deploy

```bash
cd dist_appsail
catalyst init        # choose: AppSail → Python 3.12 → source dir = . (this folder)
```

Edit the generated `app-config.json`:

```jsonc
{
  "command": "python run_web.py",     // startup command
  "memory": 1024                      // 512 default is tight for 500k-row pandas queries
}
```

**API keys: set them in the Catalyst console, NOT in files.**
Console → your project → AppSail → your app → Configuration → Environment
Variables → add:
- `LLM_PROVIDER` = `groq`  (do NOT set `LLM_MODEL` — the provider default is used)
- `GROQ_API_KEY` = your key
- `GEMINI_API_KEY` = your key (auto-fallback if Groq is rate-limited)
- `CORS_ORIGINS` = your deployed URL, e.g.
  `https://ksp-crime-intelligence-xxxxx.development.catalystappsail.in`
  (locks the API to your own frontend; without it, only localhost is allowed
  and the browser app on the Catalyst domain would be blocked by CORS)

Keys never touch the repo or the deploy zip that way. `.gitignore` also blocks
`.env` and `app-config.json` as a second line of defense.

Notes:
- The app already reads Catalyst's port from `X_ZOHO_CATALYST_LISTEN_PORT`
  (see `run_web.py`) — don't set the port yourself.

Deploy:

```bash
catalyst deploy
```

You get a URL like `https://ksp-crime-intelligence-1234567.development.catalystappsail.in`.
That URL is the datathon submission link.

## Smoke-test the deployment

```
GET  /api/health                      → all 4 databases true
GET  /api/analytics/alerts            → 20 live alerts
GET  /api/browse/fir/FIR%20Records    → total: 500000
POST /api/chat                        → answer with SQL shown
```

(These were verified locally against the exact bundle on the AppSail port
mechanism before first deploy.)

---

## Catalyst services checklist (for the submission form)

| Requirement row | Service | Status |
|---|---|---|
| Full web app in managed runtime | AppSail | ✅ this deploy |
| Text LLMs / RAG | QuickML LLM Serving | 🔜 add `catalyst` provider in `src/chatbot/llm_config.py` |
| User auth | Catalyst Authentication | 🔜 replace demo login |
| Relational DB | Data Store | 🔜 chats + audit tables |
| Object storage | Stratus | 🔜 case-file uploads |
| OCR (Kannada!) | Zia OCR | 🔜 scan-FIR feature |
| Cron | Catalyst Cron | optional: hourly alert precompute |
| Voice STT/TTS | (no Zia equivalent) | browser Web Speech API — no conflict |

## Known hackathon-scope caveats

- **Instance disk is ephemeral**: chat history / audit rows written to SQLite
  reset when the instance recycles. Fine for demos; migrate to Data Store
  before the finale for durability.
- **Ollama tab** shows "not running" in the cloud (it's a local-only provider) —
  the UI handles this gracefully.
- Development environment URLs sleep on inactivity; first request after idle
  may take a few seconds (cold start).
