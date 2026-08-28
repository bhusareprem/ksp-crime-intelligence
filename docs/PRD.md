# Product Requirements: KSP Crime Intelligence

**Status:** Prototype, deployed
**Context:** Datathon 2026 (Hack2skill x Zoho Catalyst), Challenge 01
**Owner:** Prem Bhusare

---

## 1. The user

**Primary: the investigating officer (PSI to Inspector, district or station level).**
Holds a live caseload. Needs a specific figure or a lead now, not a monthly report.
Comfortable with WhatsApp and Google, not with SQL. Often more fluent writing Kannada
than English. Frequently working from a phone, at odd hours, without a records clerk.

**Secondary: the district SP or SCRB analyst.** Needs the picture across districts:
where crime is rising, which networks are active, where to send patrols this week.
Answers to seniors and to the press, so every figure must be defensible.

**Tertiary: the SCRB data administrator.** Cares about what the system is allowed to
touch, what it logs, and whether an officer can extract personal data through it.

**Explicitly not a user:** the public. This is an internal tool over sensitive records.

---

## 2. The problem

Karnataka Police register roughly one lakh FIRs a year across more than 1,000 stations.
The data is in CCTNS. Three things follow:

1. **Questions go unasked.** Getting a figure means a request to someone who writes SQL.
   An officer with a hypothesis at 9pm cannot test it, so they stop having hypotheses.
2. **Patterns stay invisible.** A repeat offender active across eight districts looks
   like eight unrelated local nuisances. Nobody is looking across the boundary.
3. **Dashboards answer yesterday's question.** A fixed dashboard answers what its author
   anticipated. Real investigation is a chain of follow-ups.

The obvious solution, a language model over the database, introduces a worse problem. Ask
one about a district that does not exist and it will typically drop the filter and return
the statewide total. The officer reads a real, specific number against the name they
asked about. That is worse than the status quo, because the status quo does not lie
fluently.

**The product thesis:** the value is not in answering questions. It is in answering them
in a way an officer can trust, and refusing clearly when it cannot.

---

## 3. Success metrics

| Metric | Target | How measured | Now |
|---|---|---|---|
| Answer accuracy on gold questions | 100% | `scripts/eval_nlsql.py` against ground truth computed live from the database | 21/21 |
| Accuracy with the model unavailable | no regression | Same suite with the token budget exhausted | 21/21 |
| Fabricated figures | zero | Honesty cases in the gold set and in `tests/test_honesty_guards.py` | 0 |
| Kannada parity | equal to English | Kannada cases in the gold set | 5/5 |
| Time to an answer | under 10s typical | Timings in `scripts/qa_smoke.py` | 2 to 6s |
| Endpoint health | 100% | `qa_smoke.py --no-llm` | 32/32 |
| Cost to operate | zero | Free tiers only | 0 |

**The metric that matters most is the second one.** A system that is accurate only while
its API quota holds is not deployable in a police station.

**Counter-metric:** refusal rate on legitimate questions. The honesty guards must not
over-fire. `tests/test_retrieval.py::TestUnknownPlaceDetection` asserts nine real
phrasings are never flagged.

---

## 4. Assumptions

1. Officers will type or speak natural language if the answer arrives in seconds.
2. Showing the SQL builds trust rather than confusing people. It also gives a records
   clerk something to verify.
3. Kannada input matters more than Kannada output. An officer who writes the question in
   Kannada can read an English number.
4. Synthetic data on the real schema is enough to prove transferability. The generated
   SQL is what would move to production, not the rows.
5. Free-tier infrastructure is a real constraint, not a demo shortcut. A department will
   not adopt a tool with a per-question cost attached.
6. The model will be unavailable some of the time. Design for it rather than around it.

Assumption 6 was validated the hard way: the free tier ran out mid-development, which is
what produced the deterministic fallback layer.

---

## 5. Scope

### In scope

- Natural language to SQL over the FIR corpus, English and Kannada, keyboard and voice
- Generated SQL shown with every answer
- Honesty guards: unknown places, out-of-coverage years, absent fields and metrics
- Autonomous investigation agent that plans and chains its own analysis steps
- Evidence intelligence: statement or document in, prior records out
- Analytics, machine learning signals, criminal network, district map
- Live open-source crime news matched to districts
- Responsible AI notice on queries touching protected attributes
- Audit trail of every question and the SQL it generated
- Conversation history with follow-up resolution

### Out of scope for this prototype

- Real CCTNS data or a live CCTNS connection
- Production authentication, RBAC, or per-officer permissions
- Writing to any record. The system is read-only by construction
- Case management, FIR filing, or any workflow action
- Mobile applications. The web UI is responsive, but there is no native app
- Personal identifiers. Phone numbers, addresses and biometrics are deliberately absent
  from the schema, and the system says so when asked

### Deliberately rejected

**A conviction-rate feature.** CCTNS records how far a case has progressed, never the
court's verdict. Rather than approximate it, the system explains the gap and offers
chargesheet rate instead. Approximating would have produced a number that senior officers
would quote.

**Free-text answers without SQL.** Every figure is traceable or it is not shown.

---

## 6. Key flows

### 6.1 Ask a question

1. Officer types or speaks a question in English or Kannada
2. Smalltalk and procedural questions are handled without touching the database
3. Honesty guards run. If the question names an unknown place, a year outside coverage,
   or a field the schema lacks, the system explains and stops here
4. The router picks a database and records why
5. Value grounding maps the question onto exact literals present in the data
6. SQL is generated, by the model when available, by the deterministic builder otherwise
7. The safety guard admits only a single read-only SELECT
8. Results are explained, or shown as a table if the model is unavailable
9. The question, SQL, database and language are written to the audit log

**Acceptance:** an officer asking "ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು
ದಾಖಲಾಗಿವೆ?" gets 1,089 with a SQL filter naming Mysuru, in under 10 seconds.

### 6.2 Run an investigation

1. Officer gives a goal, not a query ("which district most needs patrols")
2. The agent selects a tool, runs it, reads the result, and picks the next step in light
   of it, to a maximum of five steps
3. Repeated identical calls are blocked so each step adds something
4. It writes a case brief with the full evidence trail attached

**Acceptance:** five distinct steps and a brief. When the model is rate limited, a
deterministic playbook still produces a complete investigation.

### 6.3 Check a statement against records

1. Officer uploads a statement, document or audio, or pastes text
2. Names are extracted and cross-referenced against every FIR
3. Priors, districts of operation and gang links are returned, with a risk flag

**Acceptance:** a statement naming an offender with 260 priors returns that record and
flags it. A person with no record returns no record rather than a weak guess.

### 6.4 Work while the model is down

1. Officer asks a common question with the token budget exhausted
2. The deterministic builder answers it with no model call
3. Results render as a table with the figures intact

**Acceptance:** the gold suite scores 21/21 in this state.

---

## 7. Acceptance criteria

**Correctness**

- [x] Gold suite 21/21, ground truth computed live from the database
- [x] Kannada questions keep their district and crime filters
- [x] "Attempt to Murder" is not counted under "murders"
- [x] Repeat-offender queries group by person, not by row

**Honesty**

- [x] A fictional district is refused with no figure offered
- [x] A year outside coverage names the range actually held
- [x] Absent fields and metrics are named as absent
- [x] Nine legitimate phrasings are never refused
- [x] Web results are labelled as external and never blended into database answers

**Resilience**

- [x] 21/21 with the model quota exhausted
- [x] Multiple API keys rotate on quota or authentication failure
- [x] The investigation agent completes without a model
- [x] A failing news feed does not break the analytics page

**Security**

- [x] Only single read-only SELECTs execute
- [x] Filesystem access from SQL is rejected
- [x] Prompt injection does not produce destructive SQL
- [x] No key is committed
- [x] External headlines are escaped before rendering

**Operability**

- [x] 135 automated tests, no model calls, under 20 seconds
- [x] QA suite runs without spending tokens
- [x] Every question is audited with its SQL
- [x] Deployed and reachable

---

## 8. Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Model invents a figure | Severe. An officer acts on a false number | Medium without guards | Guards ahead of SQL; SQL shown; every figure traceable |
| Free-tier quota exhausted mid-demo | High | High, it happened | Deterministic layer, two rotating keys, cross-provider fallback |
| Provider retires a model id | High | High, four already retired | Provider abstraction, probe endpoint, fallback ids |
| Kannada handled as an afterthought | High. Half the users | Was actual | Case-ending aware grounding, Kannada in the gold suite |
| Third-party service adds a key requirement | Medium | Happened with map tiles | Keyless providers with automatic fallback |
| Synthetic data mistaken for real | Severe if it reaches a decision | Medium | Stated in the README, the PRD and the demo script |
| Bias in arrest data read as offending data | Severe | Medium | Fairness notice on protected-attribute queries |
| Silent failure from a swallowed exception | High. Empty results look like real zeros | Happened twice | Tests assert non-empty; concurrency check in QA |

**The two that actually bit us.** Free-tier exhaustion drove the entire deterministic
layer. Silent exception swallowing hid a DuckDB configuration conflict that made machine
learning results empty under concurrent load, which is exactly what a judge clicking
between tabs produces.

---

## 9. Implementation plan

**Phase 1, foundation (done).** Schema, 500k synthetic FIRs, FastAPI, routing, SQL
generation, chat UI, deployment.

**Phase 2, reliability (done).** Evaluation harness with live ground truth. Deterministic
fallback. RAG value grounding. Kannada grounding. Graceful degradation on quota errors.

**Phase 3, differentiation (done).** Autonomous investigation agent, evidence
intelligence, responsible-AI guard, machine learning signals, criminal network, live news.

**Phase 4, trust (done).** Honesty guards for unknown places, coverage windows and absent
schema. 135 automated tests. QA suite. Manual test plan.

**Phase 5, production readiness (not started).** What a real deployment needs:

- Live CCTNS connection, replacing synthetic data
- Real authentication and per-officer authorisation, replacing the demo shim
- Self-hosted or departmentally licensed model, removing the third-party dependency
- Audit log retention and review policy agreed with SCRB
- Kannada output quality raised to Kannada input quality
- Load testing at station scale, and a cold-start budget under five seconds
- Formal bias review of anything touching protected attributes

**Known gaps to close first:** the model sometimes answers in English when Kannada is
selected; the criminal network samples nodes non-deterministically; cold start is about
40 seconds; chargesheet rate can answer from either dataset and should be pinned to one.
