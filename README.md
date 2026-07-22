# 🔵 KSP Crime Intelligence

**Conversational AI & Crime Analytics Platform for the Karnataka State Police**

Query 500,000 crime records in plain English or Kannada, uncover criminal networks, detect hotspots, and get predictive early-warning intelligence — all from one AI-powered platform.

> Built for **Datathon 2026** (Hack2skill × Zoho Catalyst) — addressing both *Challenge 01: Intelligent Conversational AI for KSP Crime Database* and *Challenge 02: AI-Driven Crime Analytics & Visualization Platform*.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![DuckDB](https://img.shields.io/badge/DuckDB-500k_FIRs-yellow)
![LLM](https://img.shields.io/badge/LLM-Groq_·_Gemini_·_Ollama-orange)
![Deploy](https://img.shields.io/badge/Deploy-Zoho_Catalyst_AppSail-e42527)

---

## The Problem

The State Crime Records Bureau manages crime data from **1,100+ police stations** across Karnataka. Current systems rely on static dashboards and manual SQL queries — limiting deep analysis and real-time insight. Investigators can't simply *ask* the data a question.

## The Solution

An intelligent platform where an investigator types (or speaks) a natural-language question and gets an evidence-backed answer, a network graph, or a predictive alert — with the underlying query shown for full transparency.

```
Officer question (English / Kannada / voice)
        │
        ▼
   Intent router  ──►  picks the right database
        │
        ▼
   LLM writes SQL  ──►  runs on DuckDB / SQLite  ──►  LLM explains the result
        │                                                    │
        │ (if the DB has no answer)                          ▼
        └──────────►  Web search fallback              Answer + SQL + audit log
```

---

## Key Features

### 🗣️ Conversational Crime Intelligence
- **Natural-language chatbot** — ask about FIRs, accused, victims, locations, investigation status
- **Bilingual** — full **English + ಕನ್ನಡ (Kannada)** support
- **Voice interaction** — speech-to-text input and text-to-speech output
- **Context-aware** — follow-up questions without repeating context
- **PDF export** — download the full conversation as a branded report
- **Web fallback** — searches the internet when a question falls outside the records

### 🕸️ Criminal Network & Relationship Analysis
- Co-accused and gang-membership network graphs
- Organized-crime group and repeat-offender detection
- Interactive map visualization across all 31 districts

### 📊 Crime Pattern & Trend Analytics
- Year-wise trends, top districts, crime-type breakdowns
- **Hotspot detection** — station-level crime concentration
- Interactive dashboards and geospatial maps

### 🧠 Sociological & Criminological Insights
- Demographic profiling (age, gender, occupation, socio-economic attributes)
- **Offender risk scoring** to prioritize investigation
- Behavioral analysis based on crime history

### 🚨 Forecasting & Early Warning
- Predictive next-year crime forecasts
- **Live early-warning alerts** — auto-detects district crime spikes (e.g. *"Gadag: Abetment to Suicide +800%"*)

### 🔍 Investigator Decision Support
- **Case Solver** — paste case facts, get an AI investigation brief + similar solved cases
- Automated case summaries and investigation timelines

### 🔒 Explainable AI & Secure Governance
- **Every answer shows its SQL** — full evidence trail
- **Audit log** of all queries with timestamps
- **Role-based access** — Superintendent / Inspector / Viewer

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **Databases** | DuckDB (500k-FIR analytics store), SQLite (NCRB stats, chats, audit) |
| **AI / LLM** | Groq (LLaMA 3.3 70B), Google Gemini 2.5 Flash, Ollama (offline) — swappable via LangChain |
| **NL→SQL** | LangChain + custom RAG (schema retrieval, few-shot examples, safety guard) |
| **Web search** | `ddgs` (DuckDuckGo) |
| **Frontend** | Vanilla JavaScript, HTML5, CSS3 (single-file SPA, no framework) |
| **Visualization** | Leaflet.js (maps), Chart.js (analytics), jsPDF (report export) |
| **Voice** | Browser Web Speech API |
| **Deployment** | Zoho Catalyst AppSail (managed Python runtime) |

---

## Dataset

| Source | Coverage |
|---|---|
| **KSP FIR Database** | 500,000 FIRs · 895,927 accused · 662,284 victims · 906 stations · 31 districts (2020–2024) |
| **NCRB Statistics** | National & metro crime rates, benchmarks |
| **Court Cases** | Convictions, acquittals, dispositions (2010–2018) |
| **Case Knowledge Base** | 50+ solved Indian cases for investigator reference |

> **Note:** The full FIR database (`ksp_fir.duckdb`, ~460 MB) is **not** in this repo due to GitHub's file-size limits. Smaller demo databases are included so the app runs out of the box. The full dataset is generated from raw records via the scripts in `scripts/` and `src/`.

---

## Getting Started

### Prerequisites
- Python 3.10–3.13
- A free LLM API key ([Groq](https://console.groq.com/keys) recommended, or [Gemini](https://aistudio.google.com/apikey)) — the app also runs in offline/fallback mode without one

### Install & Run
```bash
# 1. Clone
git clone https://github.com/<your-username>/ksp-crime-intelligence.git
cd ksp-crime-intelligence

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your LLM key
cp .env.example .env      # then edit .env and add your key

# 4. Launch
python run_web.py
```

Open **http://localhost:8000** and sign in with a demo account:

| Officer ID | Password | Role |
|---|---|---|
| `SP001` | `sp@ksp2024` | Superintendent (full access) |
| `INS001` | `ins@ksp2024` | Inspector |
| `VIEW01` | `view@ksp2024` | Viewer (read-only) |

### Try asking
- *"How many theft FIRs in Mysuru in 2023?"*
- *"Show me cyber crime trends in Karnataka"*
- *"Top repeat offenders by district"*
- *"ಬೆಂಗಳೂರಿನಲ್ಲಿ 2024 ರಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು?"* (Kannada)

---

## Project Structure

```
KSP/
├── api/                    # FastAPI backend
│   ├── main.py             # routes: chat, browse, upload, models, audit
│   └── analytics.py        # trends, hotspots, network, predictions, alerts
├── src/chatbot/            # conversational engine
│   ├── engine.py           # orchestration: route → SQL → execute → explain
│   ├── router.py           # picks the right database per question
│   ├── llm_config.py       # multi-provider LLM (Groq/Gemini/Ollama/…)
│   ├── db_manager.py       # safe read-only SQL execution
│   ├── sql_fix.py          # SQL safety guard (SELECT-only, no file reads)
│   ├── case_intelligence.py# Case Solver
│   └── rag/                # schema retrieval, examples, web search
├── frontend/index.html     # single-file SPA (chat, map, analytics, browse)
├── data/                   # databases (large FIR DB excluded — see note above)
├── scripts/                # data build + deployment tooling
├── run_web.py              # entry point
└── requirements.txt
```

---

## Deployment (Zoho Catalyst)

The platform deploys to **Catalyst AppSail** (managed Python runtime). A build script stages a lean bundle (code + compacted databases, ~76 MB):

```bash
python scripts/build_appsail.py     # stages dist_appsail/
cd dist_appsail
catalyst init appsail               # Python 3.12, use existing code
catalyst deploy
```

API keys are set as **environment variables in the Catalyst console** — never in files. See [`DEPLOY_CATALYST.md`](DEPLOY_CATALYST.md) for the full runbook.

---

## Security

This platform handles sensitive law-enforcement data and has been hardened:
- **SQL injection** — parameterized queries; a strict SELECT-only guard blocks writes, DDL, and file-read functions
- **DuckDB filesystem lockdown** — `enable_external_access=False` prevents reading local files via SQL
- **CORS** — restricted to trusted origins (no wildcard-with-credentials)
- **Prompt-injection resistant** — the SQL guard holds even if the LLM is steered
- **Audit trail** — every query is logged
- **No secrets in code** — API keys live only in `.env` (gitignored) or the Catalyst console

---

## License & Attribution

Built for Datathon 2026. Crime data is synthetic/derived for demonstration; no real personal records are exposed.

---

<div align="center">
🔵 <b>Karnataka State Police — Crime Intelligence Platform</b><br>
<sub>Turning fragmented records into actionable intelligence</sub>
</div>
