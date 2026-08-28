"""KSP Crime Chatbot — conversational agent with NL→SQL."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.chatbot.agent import ConversationalAgent
from src.chatbot.db_manager import DatabaseManager, QueryTimeoutError
from src.chatbot.fallback_sql import expand_question_with_history, try_fallback_sql
from src.chatbot.llm_config import create_llm, get_llm_config
from src.chatbot.normalize import normalize_question
from src.chatbot.router import route_question, route_with_reason, is_investigative_question
from src.chatbot.rag.retriever import retrieve_context
from src.chatbot.rag.web_search import needs_web_search, search_web
from src.chatbot.responsible_ai import guard as _responsible_guard
from src.chatbot.schemas import DB_DESCRIPTIONS
from src.chatbot.smalltalk import detect_smalltalk
from src.chatbot.sql_fix import fix_sql_for_dialect, is_safe_select


# Personal identifiers a question may ask for that the CCTNS schema does not carry.
_MISSING_FIELDS = [
    (r"phone|mobile|contact number|whatsapp", "phone or mobile numbers"),
    (r"home address|residential address|\baddress\b", "home addresses"),
    (r"aadhaar|aadhar|\buid\b", "Aadhaar numbers"),
    (r"email|e-mail", "email addresses"),
    (r"\bimei\b", "IMEI numbers"),
    (r"bank account|account number|ifsc", "bank account details"),
    (r"photo|photograph|mugshot|fingerprint|biometric", "photographs or biometrics"),
]


# Outcomes the CCTNS schema simply does not carry. CaseStatusMaster records how far
# a case has progressed (Registered → Charge Sheeted → Referred to Court →
# Closed/Disposed), never what the court decided.
_MISSING_METRICS = [
    (r"convict|acquit|verdict|sentenc|guilty|jail\s*term|imprisonment", "conviction and acquittal outcomes"),
    (r"\bbail\s*(rate|outcome|granted)\b", "bail outcomes"),
    (r"trial\s*(outcome|result)|court\s*(judgment|judgement|verdict|ruling)", "court judgments"),
]


def _missing_metrics(question: str) -> str:
    q = (question or "").lower()
    hits = [label for pat, label in _MISSING_METRICS if re.search(pat, q)]
    if not hits:
        return ""
    return hits[0] if len(hits) == 1 else ", ".join(hits[:-1]) + " or " + hits[-1]


def _missing_fields(question: str) -> str:
    """Personal-identifier fields the question asks for that the schema lacks."""
    q = (question or "").lower()
    hits = [label for pat, label in _MISSING_FIELDS if re.search(pat, q)]
    if not hits:
        return ""
    if len(hits) == 1:
        return hits[0]
    return ", ".join(hits[:-1]) + " or " + hits[-1]


def _db_gap_suggestion(question: str, df) -> str:
    """Return DB schema improvement suggestions when data is missing or sparse."""
    q = question.lower()
    is_empty = df is None or (hasattr(df, "empty") and df.empty)
    is_sparse = not is_empty and len(df) < 3

    hints = []

    if re.search(r"hate\s*crime|communal|religious|sectarian|minority|caste\s*attack|mob\s*lynching", q):
        if not is_empty:
            hints.append(
                "**DB Note — Communal / Caste Motive:**\n"
                "The KSP FIR DB tracks motive in `CrimeSubHead.MotiveType` "
                "('communal', 'caste', 'gender', 'economic'). "
                "Filter: `WHERE csh.MotiveType IN ('communal','caste')` or "
                "`WHERE csh.CrimeHeadName ILIKE '%riot%'`."
            )
        else:
            hints.append(
                "**DB Gap — Detailed Hate-Crime Target Data:**\n"
                "While `CrimeSubHead.MotiveType` captures motive category, "
                "the `CaseMaster` table has no `target_community` or `victim_religion` column. "
                "Recommended:\n"
                "```sql\nALTER TABLE CaseMaster ADD COLUMN TargetCommunity VARCHAR;\n"
                "ALTER TABLE CaseMaster ADD COLUMN IncidentMotive VARCHAR;\n```"
            )

    if re.search(r"gang|organized\s*crime|syndicate|cartel|network|group.*crime|crime.*group", q):
        if not is_empty:
            hints.append(
                "**DB Note — Gang Data Available:**\n"
                "The `CrimeGang` and `AccusedGangLink` tables contain 16 named gangs "
                "with specialization, member roles, and linked FIRs. "
                "Query: `AccusedGangLink JOIN CrimeGang JOIN Accused`."
            )

    if re.search(r"address|gps|coordinates|latitude|longitude|residence|home\s*address|pincode", q):
        hints.append(
            "**DB Gap — Accused Address Data:**\n"
            "The `Accused` table stores `District` (home district string) but no street address or PIN. "
            "Recommended:\n"
            "```sql\nALTER TABLE Accused ADD COLUMN AddressLine VARCHAR;\n"
            "ALTER TABLE Accused ADD COLUMN Pincode VARCHAR(6);\n"
            "ALTER TABLE Accused ADD COLUMN Latitude FLOAT;\n"
            "ALTER TABLE Accused ADD COLUMN Longitude FLOAT;\n```"
        )

    if re.search(r"phone|mobile|contact|number|sim|imei", q):
        hints.append(
            "**DB Gap — Phone / IMEI Data:**\n"
            "No contact or IMEI data exists in current schema. "
            "Recommended:\n"
            "```sql\nCREATE TABLE AccusedContact (\n"
            "  AccusedMasterID INTEGER REFERENCES Accused(AccusedMasterID),\n"
            "  PhoneNumber VARCHAR,\n"
            "  IMEI VARCHAR,\n"
            "  Carrier VARCHAR\n"
            ");\n```"
        )

    if re.search(r"vehicle|car|bike|motorcycle|registration|number\s*plate|rto", q):
        hints.append(
            "**DB Gap — Vehicle Data:**\n"
            "No vehicle or RTO data linked to accused. "
            "Recommended:\n"
            "```sql\nCREATE TABLE AccusedVehicle (\n"
            "  AccusedMasterID INTEGER REFERENCES Accused(AccusedMasterID),\n"
            "  RegistrationNumber VARCHAR,\n"
            "  VehicleType VARCHAR,\n"
            "  MakeModel VARCHAR,\n"
            "  RTODistrict VARCHAR\n"
            ");\n```"
        )

    if (is_empty or is_sparse) and not hints:
        return ""

    if not hints:
        return ""

    return "---\n💡 **Database Improvement Suggestions:**\n\n" + "\n\n".join(hints)


@dataclass
class ChatResponse:
    answer: str
    sql: str
    database: str
    data: str
    source: str
    original_question: str = ""
    normalized_question: str = ""
    correction_note: str | None = None


class CrimeChatbot:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / "data"
        self.db = DatabaseManager(self.data_dir)
        self.agent = ConversationalAgent(self.db)
        self._llm_checked = False
        self._llm_available = False

    def _llm_enabled(self) -> bool:
        if not self._llm_checked:
            self._llm_checked = True
            self._llm_available = create_llm() is not None
        return self._llm_available

    def llm_status(self) -> dict:
        return get_llm_config()

    def _format_dataframe(self, df) -> str:
        if df is None or df.empty:
            return "No results found."
        if len(df) == 1 and len(df.columns) == 1:
            return str(df.iloc[0, 0])
        return df.head(50).to_string(index=False)

    # Matches the prefix main.py injects when language=kn: "[Respond in Kannada language. ...]"
    _LANG_PREFIX = re.compile(r'^\[Respond in \w+ language\.[^\]]*\]\s*', re.I)

    def ask(self, question: str, history: list[dict] | None = None) -> ChatResponse:
        history = history or []
        original = question.strip()
        if not original:
            return ChatResponse("How can I help you with Karnataka crime data?", "", "", "", "chat")

        # Strip any language-instruction prefix so smalltalk/routing see only the user's words
        user_q = self._LANG_PREFIX.sub("", original).strip() or original

        # --- Smalltalk shortcut (greetings, name, thanks, bye) ---
        st = detect_smalltalk(user_q)
        if st:
            return ChatResponse(answer=st, sql="", database="", data="", source="chat")

        # --- Officer explicitly asked us to go online → honour it ---
        # Checked before the honesty guards: those are the right default, but the
        # officer overriding them is a direct instruction, not a question to answer.
        if self._wants_web(user_q):
            return self._ask_web_explicit(user_q, history)

        # --- Unknown place named → refuse before any SQL runs ---
        # Deterministic on purpose: if the district does not exist we must never
        # drop the filter and hand back a statewide figure the reader will take
        # as that place's. Runs with or without an LLM.
        unknown = self._unknown_places(user_q)
        if unknown:
            return self._ask_unknown_place(original, unknown)

        # --- Year outside coverage, or a metric the schema never records ---
        # Also deterministic: searching the open web for "2017 conviction rate"
        # returns foreign statistics that have nothing to do with Karnataka.
        _years = self._out_of_range_years(user_q)
        _metric = _missing_metrics(user_q)
        if _years or _metric:
            return self._ask_coverage_gap(original, _years, _metric)

        # --- Investigative procedure questions → Case Intelligence brief ---
        if is_investigative_question(user_q):
            return self._ask_investigation_guide(original)

        # --- Specific named-case lookup → case_knowledge + web search ---
        # But a name we actually hold FIRs on belongs to the database, not the web:
        # answering "who is <accused>" from a news search when we have 260 of their
        # FIRs on file is the wrong source.
        if self._is_specific_case_lookup(user_q) and not self._is_known_accused(user_q):
            return self._ask_specific_case(original)

        # --- LLM conversational mode (ChatGPT-like) ---
        if self._llm_enabled():
            return self._ask_with_agent(original, history)

        # --- Fallback mode (no API key) ---
        return self._ask_fallback(original)

    # The officer explicitly asking us to go online. The coverage guard is the
    # right default, but it must never override a direct instruction.
    _WEB_REQUEST = re.compile(
        r"\b(check|search|look|try|use|browse|google)\b[^.?!]{0,20}\b(web|online|internet|google|net)\b"
        r"|\bweb\s*search\b|\bsearch\s+(the\s+)?(web|internet|online)\b"
        r"|\bfrom\s+the\s+(web|internet)\b|\bgoogle\s+it\b|\blook\s+it\s+up\b",
        re.I)

    def _wants_web(self, question: str) -> bool:
        return bool(self._WEB_REQUEST.search(question or ""))

    def _ask_web_explicit(self, question: str, history: list[dict]) -> ChatResponse:
        """Officer asked us to go online. Search, and label the source plainly."""
        from src.chatbot.rag.web_search import search_web, _web_enabled

        # "check web" on its own refers to the previous question — carry it over.
        topic = self._WEB_REQUEST.sub("", question).strip(" ?.!,:")
        if len(topic) < 12:
            for turn in reversed(history[-8:]):
                if turn.get("role") != "user":
                    continue
                prev = self._LANG_PREFIX.sub("", turn.get("content", "")).strip()
                if prev and not self._wants_web(prev):
                    topic = prev
                    break
        topic = topic or question

        if not _web_enabled():
            return ChatResponse(
                answer="Web search is disabled on this deployment (`ENABLE_WEB_SEARCH=0`).",
                sql="", database="", data="", source="chat", original_question=question)
        # Keep the Karnataka/India framing unless the officer already supplied a
        # place — a bare "conviction rate by district 2017" returns Pakistani and
        # Canadian court statistics, which are worse than useless here.
        _has_place = re.search(r"karnataka|india|bengaluru|bangalore|mysuru|ncrb", topic, re.I)
        try:
            hits = search_web(topic, max_results=5, bare=bool(_has_place))
        except Exception:
            hits = None
        if not hits or len(hits.strip()) < 25:
            return ChatResponse(
                answer=(f"I searched the web for **{topic}** but found nothing usable. "
                        "Published Karnataka figures of this kind are usually in the NCRB "
                        "*Crime in India* report."),
                sql="", database="web", data="", source="web_search", original_question=question)

        answer = None
        llm = create_llm(temperature=0.3) if self._llm_enabled() else None
        if llm is not None:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage
                resp = llm.invoke([
                    SystemMessage(content=(
                        "You are KSP Crime Intelligence. Answer ONLY from the web results given. "
                        "These are external public sources, NOT the KSP database — say so. "
                        "If the results do not actually answer the question, say that plainly "
                        "instead of substituting a different country's or year's figures. "
                        "Cite the source names. Under 200 words.")),
                    HumanMessage(content=f"Question: {topic}\n\nWeb results:\n{hits[:4000]}"),
                ])
                answer = (getattr(resp, "content", "") or "").strip()
            except Exception:
                answer = None
        if not answer:
            answer = hits[:1500]
        return ChatResponse(
            answer="🌐 **From a web search** (external sources, not KSP data):\n\n" + answer,
            sql="", database="web", data="", source="web_search", original_question=question)

    _YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

    def _data_year_range(self) -> tuple[int, int] | None:
        """Widest year span any database can answer for."""
        if getattr(self, "_yr_range", None) is not None:
            return self._yr_range
        lo = hi = None
        for db, sql in (
            ("criminal", "SELECT MIN(EXTRACT(YEAR FROM CrimeRegisteredDate))::INT, "
                         "MAX(EXTRACT(YEAR FROM CrimeRegisteredDate))::INT FROM CaseMaster"),
            ("ksp_crime", "SELECT MIN(year), MAX(year) FROM fir_records"),
        ):
            try:
                row = self.db.execute(db, sql).iloc[0]
                a, b = int(row.iloc[0]), int(row.iloc[1])
                lo = a if lo is None else min(lo, a)
                hi = b if hi is None else max(hi, b)
            except Exception:
                continue
        self._yr_range = (lo, hi) if lo is not None else None
        return self._yr_range

    def _out_of_range_years(self, question: str) -> list[int]:
        """Years the question asks about that no database covers."""
        rng = self._data_year_range()
        if not rng:
            return []
        lo, hi = rng
        out = []
        for m in self._YEAR_RE.finditer(question or ""):
            y = int(m.group(1))
            if (y < lo or y > hi) and y not in out:
                out.append(y)
        return out

    def _ask_coverage_gap(self, question: str, years: list[int], metric: str) -> ChatResponse:
        """Explain exactly what is missing and name what can be answered instead."""
        rng = self._data_year_range()
        lines: list[str] = []
        if years:
            ys = ", ".join(str(y) for y in years)
            span = f"{rng[0]}-{rng[1]}" if rng else "the loaded years"
            lines.append(
                f"The KSP data covers **{span}**, so there are no records for **{ys}** — "
                "I have not estimated a figure for a year we hold no data on."
            )
        if metric:
            if lines:
                lines.append("")
                opener = f"Separately, **{metric}** are not recorded in this schema at all."
            else:
                opener = f"This database does not record **{metric}** at all."
            lines.append(
                opener + " `CaseStatusMaster` tracks how far a case has progressed — Registered, "
                "Under Investigation, Charge Sheeted, Referred to Court, Closed/Disposed — "
                "but never the court's decision, so this cannot be derived for any year."
            )
            lines += [
                "",
                "**What I can give you instead:** chargesheet and disposal rate by district "
                f"({rng[0]}-{rng[1]} FIR data), the closest available measure of case progression. "
                "Ask for *\"chargesheet rate by district\"* and I will pull it."
                if rng else "",
            ]
        elif years:
            lines += ["", f"Ask again for a year in {rng[0]}-{rng[1]} and I will pull the figures."]
        lines += ["", "_Want published figures from outside our records? Say **\"search the web\"** "
                      "and I will look them up, clearly labelled as an external source._"]
        return ChatResponse(
            answer="\n".join(x for x in lines if x is not None), sql="", database="criminal",
            data="", source="chat", original_question=question,
        )

    def _is_known_accused(self, question: str) -> bool:
        """True when the question names someone the FIR database has records for."""
        try:
            from src.chatbot.fallback_sql import _extract_person_name
            name = _extract_person_name(question)
            if not name or len(name) < 4:
                return False
            df = self.db.execute(
                "criminal",
                "SELECT 1 FROM Accused WHERE AccusedName ILIKE '%{}%' LIMIT 1".format(
                    name.replace("'", "''")))
            return df is not None and not df.empty
        except Exception:
            return False

    def _unknown_places(self, question: str) -> list[str]:
        """Districts/taluks the question names that are absent from the FIR database."""
        try:
            from src.chatbot.rag.schema_live import unknown_places
            path = getattr(self.db, "fir_path", None)
            if not path or not Path(path).exists():
                return []
            return unknown_places(question, str(path))
        except Exception:
            return []

    def _ask_unknown_place(self, question: str, unknown: list[str]) -> ChatResponse:
        """Say plainly that the place is not on record — and give no number."""
        names = ", ".join(f"**{u}**" for u in unknown)
        verb = "is not a district" if len(unknown) == 1 else "are not districts"
        try:
            from src.chatbot.rag.schema_live import _fir_vocab
            districts = _fir_vocab(str(self.db.fir_path))[0]
        except Exception:
            districts = ()
        lines = [
            f"{names} {verb} in the KSP FIR database, so there are **no records** to report.",
            "",
            "I have deliberately not given you a number here. Reporting the statewide total "
            "against a district name that does not exist would read as that district's count.",
        ]
        if districts:
            lines += [
                "",
                f"**The {len(districts)} districts on record are:** " + ", ".join(districts) + ".",
                "",
                "Ask again with one of these and I will pull the figures.",
            ]
        return ChatResponse(
            answer="\n".join(lines), sql="", database="criminal", data="",
            source="chat", original_question=question,
        )

    def _ask_investigation_guide(self, question: str) -> ChatResponse:
        """Handle 'how to investigate X' questions using Case Intelligence + LLM."""
        try:
            from src.chatbot.case_intelligence import CaseIntelligence
            ci = CaseIntelligence(self.data_dir / "case_knowledge.db")
            llm = create_llm() if self._llm_enabled() else None
            brief = ci.build_investigation_brief(question, llm=llm)
            if not brief or brief.startswith("[LLM unavailable"):
                # LLM gave up — build a plain guidance answer
                brief = self._plain_investigation_guide(question)
        except Exception:
            brief = self._plain_investigation_guide(question)
        return ChatResponse(answer=brief, sql="", database="case_knowledge", data="", source="investigation_guide")

    def _plain_investigation_guide(self, question: str) -> str:
        """Keyword-based investigation guidance when LLM/case_knowledge is unavailable."""
        q = question.lower()
        if re.search(r"murder|homicide|kill|dead body", q):
            crime = "murder"
            steps = [
                "Secure and document the crime scene — prevent contamination",
                "Conduct postmortem via government forensic surgeon within 24 hours",
                "Record statements from first informant and eyewitnesses (Section 161 CrPC)",
                "Collect physical evidence: weapon, fingerprints, blood samples, CCTV",
                "Establish victim's last known movements and timeline",
                "Identify motive: property dispute, family rivalry, love triangle, contract killing",
                "Map accused's alibi with corroborating witnesses",
                "File charge-sheet under IPC Section 302 within 60 days",
            ]
        elif re.search(r"rape|sexual assault|pocso", q):
            crime = "sexual assault"
            steps = [
                "Record survivor's statement with female officer present (mandatory)",
                "Medical examination within 72 hours — preserve forensic samples",
                "Collect DNA evidence and chain-of-custody documentation",
                "Issue Section 164 CrPC magistrate statement for survivor",
                "CCTV, call records, and digital forensics on accused's devices",
                "Check for prior offences by accused in criminal.db",
                "Coordinate with Child Welfare Committee if victim is a minor",
            ]
        elif re.search(r"kidnap|abduct|missing", q):
            crime = "kidnapping/missing person"
            steps = [
                "Register FIR immediately — no 24-hour wait for missing persons",
                "Circulate description to all checkpoints within 1 hour",
                "Pull call detail records (CDR) of victim and suspected persons",
                "Check last known location — CCTV, toll, GPS trail",
                "Alert railway, bus, and airport authorities with photo",
                "Coordinate with neighbouring district police",
                "CCTNS missing person alert activation",
            ]
        elif re.search(r"fraud|scam|cyber|phishing|sextortion|otp", q):
            crime = "fraud/cyber crime"
            steps = [
                "Register FIR under BNS Section 318 (Cheating) / IT Act Section 66C/D",
                "Freeze accused's bank account immediately via nodal officer",
                "Obtain call records and IP logs from telecom/ISP within 24 hours",
                "Cybercrime.gov.in complaint and NCRP portal registration",
                "Identify mule accounts — trace withdrawal chain",
                "Coordinate with Cyber Crime Police Station for digital forensics",
            ]
        else:
            crime = "crime"
            steps = [
                "Secure the scene and prevent evidence contamination",
                "Record all witness statements under Section 161 CrPC",
                "Collect physical, digital, and forensic evidence",
                "Establish timeline of events and suspect movements",
                "Cross-reference with prior FIRs in criminal.db",
                "Use Case Solver tab to find similar solved cases",
                "File charge-sheet with all collected evidence",
            ]
        lines = [f"**Investigation Guide — {crime.title()} Case**\n"]
        for i, s in enumerate(steps, 1):
            lines.append(f"{i}. {s}")
        lines.append("\n*Tip: Use the **Case Solver** tab to cross-reference similar solved cases and get a full AI investigation brief.*")
        return "\n".join(lines)

    # Patterns that indicate a user wants details on a specific named case/person
    _CASE_LOOKUP = re.compile(
        r"\b(give\s+(me\s+)?details?|tell\s+(me\s+)?about|show\s+(me\s+)?details?|"
        r"details?\s+of|info(rmation)?\s+(on|about)|explain|describe|"
        r"what\s+(happened|is|was)\s+(in|with|to|about)|background\s+on|"
        r"case\s+details?|find\s+(me\s+)?details?|search\s+(for\s+)?details?)\b",
        re.I,
    )
    # Contains a capitalized proper noun that looks like a case/person name
    _PROPER_NOUN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

    def _is_specific_case_lookup(self, question: str) -> bool:
        """True when the question is about a specific named case or person — not a DB stat query."""
        if not self._CASE_LOOKUP.search(question):
            return False
        # Must also contain a specific name OR year — otherwise it's too vague
        has_name = bool(self._PROPER_NOUN.search(question))
        has_year = bool(re.search(r"\b(19|20)\d{2}\b", question))
        has_case_word = bool(re.search(r"\b(murder|rape|kidnap|fraud|bombing|scam|shooting|"
                                       r"blast|attack|robbery|heist|scandal)\b", question, re.I))
        return has_name or (has_year and has_case_word)

    def _ask_specific_case(self, question: str) -> ChatResponse:
        """For specific named cases: search case_knowledge.db first, then web search."""
        answer_parts: list[str] = []

        # 1. Search our solved-cases database
        try:
            from src.chatbot.case_intelligence import CaseIntelligence
            ci = CaseIntelligence(self.data_dir / "case_knowledge.db")
            matches = ci.search_similar(question, limit=3)
            if matches:
                answer_parts.append("**From Case Knowledge Base:**\n")
                for c in matches[:2]:
                    answer_parts.append(
                        f"**{c['title']}** ({c.get('year','?')}, {c.get('location','?')})\n"
                        f"- Crime: {c.get('crime_type','')}\n"
                        f"- Breakthrough: {c.get('breakthrough','')}\n"
                        f"- Outcome: {c.get('outcome','')}\n"
                    )
        except Exception:
            pass

        # 2. Web search for live/detailed information
        try:
            web = search_web(question, max_results=5, bare=True)
            if web:
                answer_parts.append("\n**From Web Search:**\n" + web)
        except Exception:
            pass

        # 3. If we have content, ask LLM to synthesize it
        if answer_parts and self._llm_enabled():
            combined = "\n".join(answer_parts)
            llm = create_llm(temperature=0.3)
            if llm:
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage
                    resp = llm.invoke([
                        SystemMessage(content=(
                            "You are KSP Crime Intelligence, a police AI. "
                            "Summarize the case details below in a clear, factual format for an investigating officer. "
                            "Include: case name, year, location, crime type, key facts, how it was solved, and outcome. "
                            "Be direct and concise."
                        )),
                        HumanMessage(content=f"Question: {question}\n\nAvailable information:\n{combined}"),
                    ])
                    return ChatResponse(
                        answer=resp.content, sql="", database="web+case_knowledge",
                        data="", source="web_search", original_question=question,
                    )
                except Exception:
                    pass

        if answer_parts:
            return ChatResponse(
                answer="\n".join(answer_parts), sql="", database="web+case_knowledge",
                data="", source="web_search", original_question=question,
            )

        # 4. Nothing found anywhere
        return ChatResponse(
            answer=(
                f"I couldn't find details on that specific case in our database or via web search. "
                f"Try the **Case Solver** tab to search our 52 solved Indian cases, "
                f"or rephrase your question with the full case name and year."
            ),
            sql="", database="", data="", source="chat", original_question=question,
        )

    def _ask_with_agent(self, original: str, history: list[dict]) -> ChatResponse:
        normalized, correction_note = normalize_question(original)
        contextual = expand_question_with_history(original, history)
        if contextual != original:
            normalized_ctx, _ = normalize_question(contextual)
        else:
            normalized_ctx = normalized

        routing = route_with_reason(normalized_ctx)
        decision = self.agent.decide(original, history, routing=routing)

        _REFUSAL = re.compile(
            r"i\s+can'?t\s+provide|cannot\s+provide|i\s+am\s+not\s+able|i'?m\s+not\s+able|"
            r"personal\s+information|privacy|not\s+authorized|sensitive\s+(data|info)|"
            r"i\s+won'?t|protect\s+(the\s+)?privacy|not\s+appropriate|ethical",
            re.I,
        )

        if decision.action == "chat":
            # If LLM issued a refusal, override to a direct DB query
            if _REFUSAL.search(decision.message):
                decision.action = "query"
                decision.database = routing.database
                decision.question = normalized
            else:
                return ChatResponse(
                    answer=decision.message,
                    sql="",
                    database="",
                    data="",
                    source="groq" if get_llm_config()["provider"] == "groq" else get_llm_config()["provider"],
                    original_question=original,
                    normalized_question=original,
                )

        db_name = decision.database if decision.database in ("ksp_crime", "criminal", "cases") else routing.database
        query_q = decision.question or normalized_ctx
        sql = ""
        source = get_llm_config()["provider"]
        data_note = None

        if re.search(r"\bname", query_q, re.I) and re.search(r"criminal|offender", query_q, re.I):
            db_name = "ksp_crime"
            routing = route_with_reason(query_q)

        # Prefer high-confidence router over LLM guess when they disagree
        if routing.confidence == "high" and db_name != routing.database:
            db_name = routing.database

        web_snippet = None
        if needs_web_search(original) or needs_web_search(query_q):
            web_snippet = search_web(query_q)

        rag = retrieve_context(
            query_q,
            db_name,
            routing.reason,
            self.data_dir,
            web_snippet=web_snippet,
        )

        # 1) Try smart fallback first (reliable for common patterns)
        fb = (
            try_fallback_sql(normalized_ctx, history)
            or try_fallback_sql(normalized, history)
            or try_fallback_sql(original, history)
        )
        if fb:
            if routing.confidence == "high" and fb.db != routing.database:
                fb = None
            else:
                db_name, sql = fb.db, fb.sql
                data_note = fb.note

        # 2) LLM SQL with RAG context if no fallback matched
        if not sql:
            try:
                sql = self.agent.generate_sql(query_q, db_name, rag=rag)
                sql = fix_sql_for_dialect(sql, db_name)
                if not sql or not is_safe_select(sql):
                    sql = ""
            except Exception:
                sql = ""

        # 3) Retry fallback if LLM SQL failed. The deterministic fallback is the
        # quota-proof path, so use it when it fires instead of apologising.
        if not sql:
            fb = try_fallback_sql(normalized_ctx, history) or try_fallback_sql(normalized, history)
            if fb:
                db_name, sql = fb.db, fb.sql
                data_note = fb.note
            else:
                missing = _missing_fields(original)
                if missing:
                    answer = (
                        "The KSP FIR database has no " + missing + " — those fields do not exist "
                        "in the CCTNS schema, so there is nothing to report.\n\n"
                        "What it does hold: FIR numbers and dates, district and police station, "
                        "crime head, accused names and their prior cases, gang links, and case status."
                    )
                else:
                    answer = ("I understand your question but couldn't generate a query. Could you rephrase it? "
                              "For example: 'How many thefts in Bengaluru in 2024?'")
                return ChatResponse(
                    answer=answer,
                    sql="", database=db_name, data="", source=source,
                    original_question=original, normalized_question=normalized,
                    correction_note=correction_note,
                )

        # Run the query. On timeout/error, try a fallback SQL; if that also
        # fails, leave df=None and remember the message — the web fallback
        # below gets a chance before we give up.
        df = None
        query_error = None
        try:
            df = self.db.execute(db_name, sql)
        except QueryTimeoutError as e:
            fb = (
                try_fallback_sql(normalized_ctx, history)
                or try_fallback_sql(normalized, history)
                or try_fallback_sql(original, history)
            )
            if fb and fb.sql.strip() != sql.strip():
                try:
                    db_name, sql = fb.db, fb.sql
                    data_note = fb.note
                    df = self.db.execute(db_name, sql)
                except Exception:
                    query_error = str(e)
            else:
                query_error = str(e)
        except Exception as e:
            fb = (
                try_fallback_sql(normalized_ctx, history)
                or try_fallback_sql(normalized, history)
                or try_fallback_sql(original, history)
            )
            if fb:
                db_name, sql = fb.db, fb.sql
                data_note = fb.note
                try:
                    df = self.db.execute(db_name, sql)
                except QueryTimeoutError as te:
                    query_error = str(te)
                except Exception as e2:
                    query_error = (
                        f"I couldn't run that query. Try rephrasing.\n\nTechnical detail: {e2}"
                    )
            else:
                query_error = (
                    "I couldn't run that query. Try rephrasing — e.g. 'Top crimes in Gadag "
                    f"district' or 'Murder FIRs by district in 2023'.\n\nTechnical detail: {e}"
                )

        # Zero rows from the LLM's SQL does not mean the data is absent — the
        # deterministic builder often has a correct query for the same question.
        # Try it before falling back to the open web.
        is_empty_df = df is None or (hasattr(df, "empty") and df.empty)
        if is_empty_df:
            fb2 = try_fallback_sql(normalized_ctx, history) or try_fallback_sql(original, history)
            if fb2 and fb2.sql.strip() != (sql or "").strip():
                try:
                    df2 = self.db.execute(fb2.db, fb2.sql)
                    if df2 is not None and not df2.empty:
                        df, sql, db_name = df2, fb2.sql, fb2.db
                        data_note = fb2.note
                        is_empty_df = False
                except Exception:
                    pass

        if is_empty_df:
            web_ans = self._web_fallback_answer(original, query_q)
            if web_ans:
                return ChatResponse(
                    answer=web_ans,
                    sql=sql.strip() if sql else "",
                    database="web",
                    data="",
                    source="web_search",
                    original_question=original,
                    normalized_question=normalized,
                    correction_note=correction_note,
                )

        # DB failed and the web had nothing useful → return the error message.
        if df is None:
            return ChatResponse(
                answer=query_error or "I couldn't run that query. Please rephrase.",
                sql=sql, database=db_name, data="", source=source,
                original_question=original, normalized_question=normalized,
                correction_note=correction_note,
            )

        note_prefix = f"Note: {data_note}\n\n" if data_note else ""
        answer = note_prefix + self.agent.summarize(query_q, df, db_name, history, rag=rag)
        db_gap = _db_gap_suggestion(original, df)
        if db_gap:
            answer += "\n\n" + db_gap
        if correction_note:
            answer = f"*(Understood your question as: {normalized})*\n\n{answer}"

        # Responsible-AI guard: flag analyses touching protected attributes.
        _notice = _responsible_guard(original, answer)
        if _notice:
            answer += "\n\n" + _notice

        return ChatResponse(
            answer=answer,
            sql=sql.strip(),
            database=db_name,
            data=self._format_dataframe(df),
            source=source,
            original_question=original,
            normalized_question=normalized,
            correction_note=correction_note,
        )

    def _web_fallback_answer(self, original: str, query_q: str) -> str | None:
        """When the crime DB has no rows, search the open web and synthesize a
        clearly-labeled answer. Returns None if the web has nothing useful."""
        from src.chatbot.rag.web_search import search_web, _web_enabled

        if not _web_enabled():
            return None
        try:
            web = search_web(query_q, max_results=5, bare=True)
        except Exception:
            web = None
        # Treat empty / boilerplate "no result" strings as nothing found.
        if not web or len(web.strip()) < 25 or web.lower().startswith("no good"):
            return None

        header = "🌐 *Not found in the KSP crime database — answering from a web search:*\n\n"

        if self._llm_enabled():
            llm = create_llm(temperature=0.3)
            if llm:
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage
                    resp = llm.invoke([
                        SystemMessage(content=(
                            "You are KSP Crime Intelligence, a police AI assistant. The internal "
                            "crime database had NO records for the officer's question, so you are "
                            "answering from the web search results below. Summarize concisely and "
                            "factually for an investigating officer. Cite what the sources say. "
                            "If the results do not actually answer the question, say so plainly "
                            "instead of guessing."
                        )),
                        HumanMessage(content=f"Question: {original}\n\nWeb search results:\n{web}"),
                    ])
                    if resp and getattr(resp, "content", "").strip():
                        return header + resp.content.strip()
                except Exception:
                    pass

        # No LLM or synthesis failed — return the raw snippets, still labeled.
        return header + web.strip()

    def _ask_fallback(self, original: str) -> ChatResponse:
        smalltalk = detect_smalltalk(original)
        if smalltalk:
            return ChatResponse(smalltalk, "", "", "", "chat", original_question=original)

        normalized, correction_note = normalize_question(original)
        db_name = route_question(normalized)

        fb = try_fallback_sql(normalized)
        if not fb:
            return ChatResponse(
                answer=(
                    "I'm running in offline mode (no API key). I can answer specific crime questions.\n\n"
                    "Try:\n"
                    "• How many thefts in Bengaluru in 2024?\n"
                    "• NCRB cyber crimes in Bengaluru 2024\n"
                    "• Top repeat offender profiles\n\n"
                    "Add your Groq/OpenAI key in `.env` for full ChatGPT-style conversation."
                ),
                sql="", database=db_name, data="", source="fallback",
                original_question=original, normalized_question=normalized,
            )

        df = self.db.execute(fb.db, fb.sql)
        data_str = self._format_dataframe(df)
        answer = f"Results from {fb.db} ({DB_DESCRIPTIONS[fb.db]}):\n{data_str}"
        if correction_note:
            answer = f"({correction_note})\n\n{answer}"

        return ChatResponse(
            answer=answer, sql=fb.sql.strip(), database=fb.db, data=data_str,
            source="fallback", original_question=original,
            normalized_question=normalized, correction_note=correction_note,
        )
