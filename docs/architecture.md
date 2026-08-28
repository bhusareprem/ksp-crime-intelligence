# Architecture

How the system is put together, and why the pieces sit where they do.

---

## 1. Component boundaries

```
frontend/index.html          Single-page UI. No build step, no framework.
        |  HTTP/JSON
api/main.py                  FastAPI app: routing, validation, sessions, audit
api/analytics.py             Aggregate SQL endpoints (charts, hotspots, network)
        |
src/chatbot/engine.py        Orchestration. Owns the order guards and paths run in.
        |
        +-- router.py                which database, and why
        +-- rag/                     schema, examples, value grounding
        +-- agent.py                 LLM SQL generation and summarisation
        +-- fallback_sql.py          deterministic SQL, no model call
        +-- sql_fix.py               execution safety guard
        +-- responsible_ai.py        protected-attribute notice
        +-- db_manager.py            the only path to a database
        +-- chat_store.py            sessions and messages
        |
src/chatbot/investigator.py  Autonomous agent (own tool loop)
src/chatbot/evidence.py      Statement and document analysis
src/ml/patterns.py           Clustering, anomalies, forecasting (numpy only)
src/news/live_news.py        Open-source news ingestion
```

**Rules that hold across the codebase:**

- `db_manager` is the only component that executes SQL against the FIR corpus, and it
  applies the safety guard on every call.
- `engine` decides *order*. It does not generate SQL or format answers itself.
- `llm_config` is the only component that knows a provider exists. Everything else asks
  for "an LLM" and receives an object with `.invoke()`.
- Guards run **before** SQL generation, so they work with or without a model.

---

## 2. Database schema

### The FIR corpus, `ksp_fir.duckdb` (CCTNS)

The logical structure of a real CCTNS instance. 500,000 FIRs, 2020 to 2024.

```
District (31)                    CrimeSubHead (38)
  DistrictID PK                    CrimeSubHeadID PK
  DistrictName                     CrimeHeadName
  Latitude, Longitude              CrimeHeadID, MotiveType
  Population
      ^                                  ^
      | DistrictID                       | CrimeMinorHeadID
      |                                  |
Unit (1,020)                       CaseMaster (500,000)
  UnitID PK  <----------------------  PoliceStationID
  UnitName, TypeID                    CaseMasterID PK
  DistrictID FK                       CrimeNo, CaseNo
  Latitude, Longitude                 CrimeRegisteredDate
                                      CaseStatusID FK
                                            ^
                    +-----------------------+-----------------------+
                    | CaseMasterID          | CaseMasterID          | CaseStatusID
                    |                       |                       |
            Accused (895,927)       Victim (662,284)      CaseStatusMaster (7)
              AccusedMasterID PK      VictimMasterID PK     Registered
              CaseMasterID FK         CaseMasterID FK       Under Investigation
              AccusedName             VictimName            Charge Sheeted
              AgeYear, District                             Final Report Filed
              ReligionID, CasteID                           Referred to Court
              OccupationID                                  Closed/Disposed
                    ^                                       Pending
                    | AccusedMasterID
                    |
     +--------------+--------------+
     |                             |
AccusedGangLink (2,000)     ArrestSurrender (526,784)
  AccusedMasterID FK          CaseMasterID FK
  GangID FK -> CrimeGang(16)  AccusedMasterID FK
  Role, JoinedYear            ArrestSurrenderDate, BailGranted
```

**The grain trap.** `Accused` holds **one row per person per case**, and
`AccusedMasterID` is unique per row: 895,927 rows, 895,927 distinct ids. The identity
that repeats across cases is `AccusedName` (3,525 distinct). Grouping a repeat-offender
query by `AccusedMasterID` therefore gives every person a count of exactly one, and
`HAVING COUNT(*) > 1` returns nothing at all.

This is the single most important fact about this schema. It is asserted in
`tests/test_honesty_guards.py::test_repeat_offenders_are_grouped_by_person_not_row` and
documented inline in the RAG examples so the model is not taught the wrong pattern.

**What the schema does not contain**, and the system says so when asked: court verdicts
(status stops at disposal), phone numbers, addresses, Aadhaar, email, IMEI, bank details,
photographs and biometrics.

**Standard joins**

```sql
-- geography
CaseMaster cm
  JOIN Unit u     ON cm.PoliceStationID = u.UnitID
  JOIN District d ON u.DistrictID       = d.DistrictID
-- crime type
  JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
-- year
WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
```

### Supporting databases

| File | Engine | Contents |
|---|---|---|
| `ksp_crime.db` | SQLite | NCRB national and city statistics, plus 25,000 FIRs from 2018 |
| `cases.db` | DuckDB | Court and case-status reference data |
| `case_knowledge.db` | SQLite | 52 solved Indian cases for the Case Solver |
| `chats.db` | SQLite | Sessions and messages |
| `audit.db` | SQLite | One row per question with the SQL generated |

Coverage differs: the FIR corpus is 2020 to 2024, `ksp_crime` starts in 2018. The
coverage guard uses the widest span so a 2019 question is not wrongly refused.

---

## 3. API surface

42 endpoints. Full interactive documentation at `/docs`.

### Conversation

| Method | Path | Notes |
|---|---|---|
| POST | `/api/chat` | Main entry. `message` (1 to 2000 chars), `language`, `session_id`, `history` |
| GET/POST | `/api/sessions` | List, create |
| GET/DELETE | `/api/sessions/{id}` | Fetch, delete (cascades to messages) |
| GET | `/api/audit` | Audit trail |
| POST | `/api/voice/transcribe` | Audio to text via Whisper |
| POST | `/api/upload` | Attach a case file to a session |

### Intelligence

| Method | Path | Notes |
|---|---|---|
| POST | `/api/investigate` | Autonomous agent. Returns steps, brief, method |
| GET | `/api/investigate/examples` | Suggested goals |
| GET | `/api/evidence/sample` | Sample witness statement |
| POST | `/api/evidence/analyze` | Multipart: `text` or `file`. Returns entities, matches, summary |
| GET | `/api/intelligence/brief` | Synthesised executive briefing plus signal counts |
| GET | `/api/intelligence/patrol` | Patrol deployment recommendation |

### Analytics and ML

`/api/analytics/`: `trends`, `crime-type-trends`, `hotspots`, `district-breakdown`,
`predictions`, `alerts`, `cases-summary`, `behavioral-profile`, `network`
`/api/ml/`: `clusters`, `anomalies`, `forecast`, `socioeconomic`
`/api/news/live` (`?force=1` bypasses the 60 second cache)

### Data access and system

`/api/browse/{db}/schema`, `/api/browse/{db}/{view}`, `/api/case-solver/*`,
`/api/models`, `/api/models/select`, `/api/health`

---

## 4. Retrieval and generation flow

`engine.ask()` runs a fixed order. The order is the design.

```
1  Language directive stripped for analysis, kept for the answer
2  Smalltalk           -> canned reply, no database
3  Explicit web request -> web search, labelled as external
4  Unknown place        -> refuse, name the real districts        no model
5  Year outside coverage
   or absent metric     -> refuse, state the coverage             no model
6  Procedural question  -> investigation guide
7  Known accused named  -> database, not a web lookup
8  Otherwise            -> query path below
```

The query path:

```
route_with_reason(question)
    -> RouteResult(database, reason, confidence, needs_web_search)

retrieve_context(question, database, reason, data_dir)
    -> RAGContext:
         live_schema      introspected from the database, never hand-maintained
         value_hints      row counts, coverage, cardinalities
         value_grounding  question mapped onto exact literals in the data
         examples         3 nearest few-shot pairs, token-overlap scored
         web_snippet      only when the question needs it

agent.decide(...)  -> SQL from the model, grounded by the block above
    on failure or 429 -> fallback_sql.try_fallback_sql()  (deterministic)

is_safe_select(sql) -> single read-only SELECT, no file access

db_manager.execute(db, sql)   with timeout

zero rows?  -> retry with the deterministic builder before the web
agent.summarize(...) -> prose, or a plain table if the model is unavailable
responsible_ai.guard(...) -> appends a fairness notice when relevant
audit row written
```

### Value grounding

The step that prevents most wrong answers. Before any SQL is written, the question is
mapped onto literals that actually exist:

- `"drug"` to `NDPS - Possession`, `NDPS - Trafficking`. There is no `drug` crime head,
  so an ungrounded filter returns zero rows.
- `"Bangalore"`, `"Mangalore"`, `"Hubli"` to their canonical district names.
- `ಮೈಸೂರಿನಲ್ಲಿ` to `Mysuru`. Kannada fuses case endings onto names, so matching is done on
  the consonant stem, which survives every ending.
- `"murders"` to `Murder` only. `Attempt to Murder` is a separate offence, and including
  it inflated the figure by 53%.

Grounding also produces the **negative** signal: a place named in the question that is
not a district in the data raises a hard warning, which is what stops a fictional
district being answered with the statewide total.

---

## 5. Agent routing

Two independent agents.

**Query agent** (`agent.py`) is single-shot: question in, SQL out, then results in and
prose out. It never chooses tools.

**Investigation agent** (`investigator.py`) owns a loop over eight deterministic tools:
`spike_alerts`, `anomalies`, `emerging_clusters`, `forecast`, `hotspots`, `top_offenders`,
`crime_by_district`, `offenders_in_district`.

```
goal
 |
 +-> plan(goal, steps_so_far, banned_calls)   model picks the next tool as JSON
 |      |
 |      +-> "conclude"  -> stop
 |      +-> duplicate   -> re-plan with that call ruled out
 |      +-> tool        -> execute, append (thought, tool, args, observation)
 |
 +-> repeat to a maximum of five steps
 |
 +-> synthesize(goal, steps)  -> case brief with the evidence trail
```

Two properties worth noting. **The tools never need a model**, so the evidence is always
real even when the planning is not. And when the model is unavailable, a deterministic
five-step playbook runs instead, so an investigation always completes. The response
reports `method: autonomous` or `method: playbook` honestly.

Duplicate suppression exists because without it the planner looped, spending three of
five steps re-running one call.

---

## 6. Model abstraction and toggle

`llm_config.py` is the only module that knows providers exist.

```
create_llm()
   -> get_active()        runtime selection from /api/models/select
   -> detect_provider()   falls back to LLM_PROVIDER in the environment
   -> driver per provider:
        groq, openrouter  OpenAI-compatible
        gemini            google-genai SDK, wrapped to the same interface
        mistral, ollama   native clients
   -> wrapped in _CleanChat
```

`_CleanChat` is a thin proxy over `.invoke()` that does three jobs:

1. **Strips `<think>` blocks.** Reasoning models emit them, and left in place they poison
   SQL and JSON parsing.
2. **Normalises exotic Unicode whitespace.** Models emit narrow no-break spaces inside
   names (`Bengaluru Urban`), which breaks search and copy-paste into other systems.
3. **Rotates API keys.** On a quota or authentication error it moves to the next `gsk_`
   key found in the environment and retries the same request. Groq meters per
   organisation at 200,000 tokens per day, so a key from a second account is a second
   budget. The user never sees the failure.

Above that, `api/main.py` catches quota errors on the chat path and switches to a
different *provider* entirely, passing that provider's own model id.

Switching provider is a configuration change. No code path outside this module changes.

---

## 7. Security

**SQL execution.** Every query passes `is_safe_select` before reaching a database:
single statement only, must begin with `SELECT` or `WITH`, no DDL or DML keywords, and no
filesystem functions. DuckDB can read local files from SQL, so `read_csv`, `read_parquet`,
`glob`, `ATTACH` and `COPY` are rejected explicitly. All connections are opened read-only
with `enable_external_access: False`.

**Prompt injection.** The guard sits after generation, so an injected instruction that
persuades the model to emit `DROP TABLE` still cannot execute. Covered in
`tests/test_sql_safety.py`.

**Input validation.** Chat messages are 1 to 2000 characters, enforced by the request
model. Uploads are capped at 25 MB.

**Untrusted content.** News headlines come from an external RSS feed and are HTML-escaped
before rendering. Web search results are labelled as external and never merged into
database answers.

**Personal data.** The schema carries no phone numbers, addresses, Aadhaar, biometrics or
bank details, and the system names those as absent rather than approximating them.

**Secrets.** Keys live in `.env` and `app-config.json`, both gitignored. Verified with
`git grep -nE "gsk_|AIza|AQ\."` before every push.

**Audit.** Every question is recorded with the SQL generated, the database used and the
language, giving an after-the-fact record of what was actually run.

**Not production-grade:** authentication is a demo shim with no real authorisation, and
there is no rate limiting per user. Both are listed in the PRD as production work.

---

## 8. Deployment topology

```
Browser
   |  HTTPS
Zoho Catalyst AppSail
   |
   run_web.py
     - extracts deps.zip to deps/ on first boot, prepends to sys.path
     - binds 0.0.0.0 on X_ZOHO_CATALYST_LISTEN_PORT
     - uvicorn serving api.main:app
   |
   +-- data/  read-only DuckDB and SQLite, shipped in the bundle
   +-- outbound HTTPS:
         api.groq.com            inference and Whisper
         generativelanguage.googleapis.com   fallback
         news.google.com         RSS
         services.arcgisonline.com  map tiles (browser side)
```

Single container, no external database, no object store. Everything the app reads ships
with it, which is what keeps it on a free tier and makes a cold start self-contained.

**Bundle:** 58 files, 171 MB, of which `deps.zip` is 94 MB. Dependencies are vendored as
x86_64 Linux wheels because Catalyst does not install `requirements.txt`. They are zipped
because 20,000 loose files fail to upload.

**Cold start** is about 40 seconds while `deps.zip` unpacks, during which the app returns
503. This is the largest known operational weakness.

**Configuration** is in `app-config.json` under `env_variables`. A CLI deploy overwrites
console environment variables with the contents of that file, so it is the single source
of truth.
