# KSP Crime Intelligence

**Conversational crime analytics for the Karnataka State Police.** An officer asks a
question in English or Kannada, by keyboard or voice, and gets an answer from 500,000
FIRs with the SQL attached. When the data cannot support an answer, the system says so
instead of producing a number that looks right.

Built for **Datathon 2026** (Hack2skill x Zoho Catalyst), Challenge 01: Intelligent
Conversational AI for the KSP Crime Database.

**Live:** https://ksp-50044157211.development.catalystappsail.in
(click *Enter as Demo Officer* for full access, no account needed)

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![DuckDB](https://img.shields.io/badge/DuckDB-500k_FIRs-yellow)
![Tests](https://img.shields.io/badge/tests-135_passing-brightgreen)
![Deploy](https://img.shields.io/badge/deploy-Zoho_Catalyst-e42527)

---

## Contents

| Document | What is in it |
|---|---|
| This file | Architecture overview, install, configuration, running, tests, troubleshooting |
| [docs/PRD.md](docs/PRD.md) | Problem, users, success metrics, scope, flows, acceptance criteria, risks |
| [docs/architecture.md](docs/architecture.md) | Schema, endpoints, component boundaries, retrieval flow, routing, security, deployment |
| [docs/design.md](docs/design.md) | UI principles, information architecture, interaction states, responsive and accessibility decisions |
| [docs/agent-transcripts/](docs/agent-transcripts/) | Development logs, including the failures and how they were corrected |
| [tests/MANUAL_TEST_PLAN.md](tests/MANUAL_TEST_PLAN.md) | Browser test plan for what automation cannot cover |
| [demo/DEMO_QA.md](demo/DEMO_QA.md) | Demo questions with verified expected answers |
| [demo/VIDEO_SCRIPT.md](demo/VIDEO_SCRIPT.md) | Shot-by-shot demo recording script |

---

## The problem

The State Crime Records Bureau holds crime data from more than 1,000 police stations.
Getting an answer out of it means writing SQL or requesting a report and waiting. An
investigating officer with a question at 9pm has no way to ask it.

The obvious fix, a chatbot over the database, has a failure mode that matters more here
than in most domains: a language model asked about a district that does not exist will
happily drop the filter and return the statewide total. The officer reads a real number
against the name they asked about. In policing, a confident wrong number is more
dangerous than no answer.

This system is built around that constraint.

---

## Architecture overview

```
                    Officer question (English / Kannada / voice)
                                     |
                    +----------------+----------------+
                    |                                 |
             Smalltalk?                        Honesty guards
             Procedure?                   (run before any SQL, no model call)
                    |                    - names a district we do not have
                    |                    - asks for a year outside coverage
                    |                    - asks for a field or metric not in the schema
                    |                                 |
                    |                          refuse and explain
                    v
              Intent router  -->  picks the database and explains why
                    |
                    v
            RAG value grounding
            question -> exact literals in the data
            ("drug" -> NDPS heads, ಮೈಸೂರಿನಲ್ಲಿ -> Mysuru)
                    |
        +-----------+-----------+
        |                       |
   LLM writes SQL      Deterministic SQL builder
   (grounded prompt)   (no model call, covers common questions)
        |                       |
        +-----------+-----------+
                    v
            SQL safety guard  (single read-only SELECT, no file access)
                    |
                    v
              DuckDB / SQLite
                    |
                    v
       LLM explains the result  -->  answer + SQL + audit row
       (falls back to a plain table when the model is unavailable)
```

Two properties fall out of this shape:

**It degrades instead of failing.** The deterministic builder answers common questions
with no model call at all. With the model's daily token budget fully exhausted, the
evaluation suite still scores 21 out of 21: the figures stay correct and only the prose
gets plainer.

**It refuses before it guesses.** The guards sit ahead of SQL generation, so they hold
whether or not a model is available.

### Feature map

| Area | What it does |
|---|---|
| Conversational query | Bilingual natural language to SQL over 500,000 FIRs, SQL shown with every answer |
| Voice input | Speech to text through Whisper, raw PCM capture in the browser |
| Autonomous Investigation Agent | Given a goal, plans its own next step, runs an intelligence tool, follows the lead, writes a case brief |
| Evidence Intelligence | Statement, document or audio in, named entities cross-referenced against every FIR for priors and gang links |
| AI Intelligence Brief | Executive briefing synthesised from live hotspot, cluster, anomaly, forecast and news signals |
| Analytics | Six charts plus a live Karnataka crime news feed matched to districts |
| Intel Map | District hotspots and a criminal network, suspects revealed on zoom |
| Machine learning | DBSCAN clustering, robust z-score anomalies, OLS forecast, Pearson correlation, implemented in numpy |
| Responsible AI | Queries touching caste, religion or community carry a fairness notice |
| Audit trail | Every question, generated SQL, database and language recorded |

---

## Prerequisites

- **Python 3.12** (3.11 works; 3.12 is what is deployed)
- **~1 GB disk** for the FIR database
- **An LLM API key.** Groq is free and needs no card. Gemini or a local Ollama model
  also work. The app runs without any key, answering from the deterministic path only.

---

## Installation

```bash
git clone https://github.com/bhusareprem/ksp-crime-intelligence.git
cd ksp-crime-intelligence
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then edit, see below
```

The `data/` directory ships with the databases. To rebuild the synthetic FIR corpus:

```bash
python db/generate.py            # regenerates data/ksp_fir.duckdb (500k FIRs)
```

---

## Environment variables

All configuration lives in `.env` (gitignored). Copy `.env.example` and fill in.

| Variable | Required | Purpose |
|---|---|---|
| `LLM_PROVIDER` | yes | `groq`, `gemini`, `openrouter`, `mistral`, `ollama`, or `none` |
| `LLM_MODEL` | yes | Model id for that provider |
| `GROQ_API_KEY` | for Groq | Key from console.groq.com |
| `GROQ_API_KEY_2ND` | optional | Key from a second Groq account, see below |
| `GEMINI_API_KEY` | optional | Cross-provider fallback |
| `OPENAI_BASE_URL` | for Groq | `https://api.groq.com/openai/v1` |
| `LLM_MODEL_FALLBACK` | optional | Cheaper model to try before switching provider |
| `QUERY_TIMEOUT_SECONDS` | no | SQL timeout, default 20 |
| `LLM_TIMEOUT_SECONDS` | no | Model timeout, default 45 |
| `ENABLE_WEB_SEARCH` | no | `0` disables the web fallback entirely |

Never commit a key. `.env`, `app-config.json` and `dist_appsail/app-config.json` are all
gitignored. Before pushing:

```bash
git grep -nE "gsk_|AIza|AQ\."      # must return nothing
```

### Groq key rotation

Groq meters its free tier **per organisation at 200,000 tokens per day**, which is roughly
40 to 80 rich questions. A key from a second Groq account is a second budget. Set both
`GROQ_API_KEY` and `GROQ_API_KEY_2ND` and the app discovers every `gsk_` key in the
environment and rotates to the next one mid-request on a quota **or** authentication
error, so a spent or revoked key never reaches the user. Add more as `GROQ_API_KEY_3`
and so on, no code change needed.

---

## Model setup

### Cloud: Groq (recommended)

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

`openai/gpt-oss-120b` was chosen by measurement, not reputation. A head-to-head on the
three things this app actually does gave:

| Model | Kannada | JSON tool planning | DuckDB SQL |
|---|---|---|---|
| `openai/gpt-oss-120b` | pass | pass | pass |
| `qwen/qwen3.6-27b` | fail | fail | fail |
| `openai/gpt-oss-20b` | fail | fail | pass |

Qwen 3.6 is a reasoning model: it spends hundreds of tokens inside `<think>` and never
reaches an answer, which breaks the agent planner and burns the token budget. If you swap
models, re-run that comparison rather than assuming.

**Groq's model list changes.** `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`,
`mixtral-8x7b-32768` and `gemma2-9b-it` are all retired. Probe before trusting an id:

```bash
curl -H "Authorization: Bearer $GROQ_API_KEY" \
     -H "User-Agent: Mozilla/5.0" \
     https://api.groq.com/openai/v1/models
```

The `User-Agent` header is not optional. Groq returns **403 to Python's default urllib
agent**, which is easily misread as a revoked key.

### Cloud: Gemini

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=...
```

Strong Kannada, but the free tier allows 10 requests per minute and 250 per day, which
the investigation agent alone can exhaust. Best kept as the fallback.

### Local: Ollama

```bash
ollama serve
ollama pull llama3.2
```

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
```

No key, no quota, fully offline. Quality on Kannada and on SQL generation is lower, so
expect the deterministic path to carry more of the load.

### No model at all

```env
LLM_PROVIDER=none
```

The app still runs. Common questions are answered by the deterministic SQL builder, the
honesty guards work, and analytics, ML and the map are unaffected.

---

## Running

```bash
python run_web.py                  # http://localhost:8000
PORT=8080 python run_web.py        # or choose a port
```

First start takes about 30 seconds while langchain and duckdb import. The port is read
from `PORT`, or `X_ZOHO_CATALYST_LISTEN_PORT` when deployed.

Interactive API docs at `/docs`.

---

## Tests

```bash
python -m pytest                                        # 135 tests, ~18s, no model calls
python scripts/qa_smoke.py http://localhost:8080 --no-llm   # 32 endpoint checks, no tokens
python scripts/eval_nlsql.py                            # 21 gold questions, spends tokens
```

| Suite | Covers | Spends tokens |
|---|---|---|
| `pytest` | Routing, retrieval and grounding, SQL safety, persistence, honesty guards, API contract | no |
| `qa_smoke.py --no-llm` | All 42 HTTP endpoints, analytics, ML, network graph, news, security, concurrency | no |
| `qa_smoke.py` | The above plus the agent, evidence analysis and briefing | yes |
| `eval_nlsql.py` | End-to-end accuracy against ground truth computed live from the database | yes |
| [Manual plan](tests/MANUAL_TEST_PLAN.md) | Rendering, map, voice, responsive, accessibility | no |

The default `--no-llm` mode exists because routine QA should not consume the daily token
budget. Save the token-spending runs for a release gate.

---

## Deployment

Zoho Catalyst AppSail. See [DEPLOY_CATALYST.md](DEPLOY_CATALYST.md) for the full recipe.

```bash
cd dist_appsail && catalyst deploy
```

Five things that are easy to get wrong:

1. The start command must be `python3 run_web.py`. There is no bare `python`.
2. Catalyst does not install `requirements.txt`. Dependencies are vendored into the bundle.
3. Vendored wheels must be **x86_64 Linux**, not aarch64. Wrong architecture surfaces as
   `ModuleNotFoundError: pydantic_core._pydantic_core`.
4. Twenty thousand dependency files fail to upload. They are zipped into `deps.zip` and
   extracted on first boot. **Never commit or upload the extracted `deps/` directory**, it
   inflates the bundle from 171 MB to 478 MB.
5. Keys go in `app-config.json` under `env_variables`. A CLI deploy overwrites console
   environment variables with the file's contents.

First request after a deploy returns 503 for about 40 seconds while `deps.zip` unpacks.
That is expected. Verify with:

```bash
python scripts/qa_smoke.py https://your-app.catalystappsail.in --no-llm
```

---

## Data

500,000 synthetic FIRs on the **real CCTNS schema**, calibrated to NCRB district
proportions. 31 districts, 1,020 police stations, 2020 to 2024.

The records are synthetic. The schema is real, which is what makes the generated SQL
transferable to a production CCTNS instance. State this plainly in any demo.

| Database | Contents |
|---|---|
| `ksp_fir.duckdb` | The CCTNS corpus: CaseMaster, Accused, Unit, District, CrimeSubHead, gangs, arrests |
| `ksp_crime.db` | NCRB national and city statistics, plus a smaller FIR set from 2018 |
| `cases.db` | Court and case-status reference data |
| `case_knowledge.db` | 52 solved Indian cases used by the Case Solver |
| `chats.db`, `audit.db` | Conversation history and the audit trail |

---

## Troubleshooting

**Server appears not to start.** Imports take about 30 seconds. Check for a bound port
before assuming failure.

**`Address already in use`.** On Windows, Docker Desktop commonly holds port 8000. Use
`PORT=8080`.

**All Groq models return 403.** Almost certainly the missing `User-Agent` header, not a
revoked key. Retry with a browser agent before regenerating anything.

**`ModuleNotFoundError: pydantic_core._pydantic_core`.** Wrong wheel architecture in the
deployment bundle. Re-vendor with `--platform manylinux2014_x86_64`.

**`Can't open a connection to same database file with a different configuration`.**
Every DuckDB reader must use the identical config. All runtime readers use
`{"enable_external_access": False}`. A mismatch is swallowed by an exception handler and
surfaces as silently empty ML results, not as an error.

**Rate limited, or answers arrive as plain tables.** The daily token budget is spent. The
figures are still correct. Add a second Groq key, or wait for the reset.

**Map tiles show a watermark.** A tile provider started requiring an API key. The app uses
keyless Esri dark canvas with an OpenStreetMap fallback; see `addBasemap` in the frontend.

**Kannada questions return the wrong district.** Check the SQL in the answer. The district
filter should name the district you asked about. Regression coverage is in
`tests/test_retrieval.py::TestDistrictMatching`.

---

## Project layout

```
api/            FastAPI app and analytics endpoints
src/chatbot/    Engine, agent, router, RAG, guards, persistence
src/ml/         Clustering, anomalies, forecasting (numpy only)
src/news/       Live crime news ingestion
frontend/       Single-page UI
tests/          Automated suite and the manual test plan
scripts/        Evaluation harness, QA smoke suite, build tooling
docs/           PRD, architecture, design, agent transcripts
demo/           Demo Q&A sheet and evidence upload files
```

---

## Licence and status

Prototype built for Datathon 2026. Not a production police system: the data is synthetic,
authentication is a demo shim, and the deployment is a free tier. See
[docs/PRD.md](docs/PRD.md) for what production would require.
