"""Case Intelligence Engine — cross-references solved cases to help investigators."""

import json
import re
import sqlite3
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SimilarCase:
    title: str
    year: str
    location: str
    crime_type: str
    breakthrough: str
    investigation_tips: list[str]
    outcome: str
    relevance_score: float


class CaseIntelligence:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._available = db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Crime-type keyword synonyms for boosted matching
    _CRIME_SYNONYMS: dict[str, list[str]] = {
        "rape": ["rape", "sexual assault", "victim", "attacker"],
        "murder": ["murder", "killed", "dead", "death", "homicide", "stabbed", "shot"],
        "kidnap": ["kidnap", "missing", "abduct", "ransom", "van", "school"],
        "cyber": ["cyber", "WhatsApp", "online", "sextortion", "morphed", "OTP", "fraud", "phishing"],
        "stalking": ["stalk", "threatening", "ex", "harassment", "message", "tyre"],
        "fraud": ["fraud", "scam", "money", "bank", "OTP", "transfer", "invest", "ponzi"],
        "burglary": ["burglary", "theft", "robbed", "stolen", "gold", "window", "vacation"],
        "missing": ["missing", "disappeared", "abandoned", "business dispute", "cash withdrawal"],
        "acid": ["acid", "attack", "disfigure"],
        "gang": ["gang", "organized", "network", "shooting"],
        "terrorism": ["terror", "bomb", "blast", "explosion"],
        "corruption": ["corruption", "bribe", "officer", "scam", "procurement"],
    }

    def _extract_crime_keywords(self, query: str) -> tuple[list[str], str | None]:
        """Return (important words, detected_crime_type) from query text."""
        q_lower = query.lower()
        # Remove very common words that cause false positives
        STOPWORDS = {
            "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
            "or", "was", "she", "he", "his", "her", "they", "them", "has", "have",
            "from", "with", "that", "this", "also", "but", "not", "by", "be", "are",
            "been", "had", "who", "which", "year", "old", "man", "woman", "person",
        }
        words = [w for w in re.findall(r'\w+', q_lower) if w not in STOPWORDS and len(w) > 2]

        detected_type = None
        best_match_count = 0
        for crime_type, synonyms in self._CRIME_SYNONYMS.items():
            count = sum(1 for s in synonyms if s in q_lower)
            if count > best_match_count:
                best_match_count = count
                detected_type = crime_type

        return words, detected_type

    def search_similar(self, query: str, limit: int = 5) -> list[dict]:
        """Full-text search for similar solved cases with crime-type boosting."""
        if not self._available:
            return []

        words, detected_type = self._extract_crime_keywords(query)
        if not words:
            return []

        # Fetch more than needed so we can re-rank
        fetch_limit = min(limit * 4, 20)
        fts_query = " OR ".join(words[:12])

        try:
            conn = self._connect()

            # Primary FTS search
            rows = conn.execute(
                """SELECT sc.*, bm25(solved_cases_fts) AS score
                   FROM solved_cases_fts
                   JOIN solved_cases sc ON sc.id = solved_cases_fts.rowid
                   WHERE solved_cases_fts MATCH ?
                   ORDER BY score
                   LIMIT ?""",
                (fts_query, fetch_limit),
            ).fetchall()

            if not rows and detected_type:
                # Fallback: search by crime type keyword in crime_type column
                rows = conn.execute(
                    "SELECT *, 0 as score FROM solved_cases WHERE crime_type LIKE ? LIMIT ?",
                    (f"%{detected_type}%", fetch_limit),
                ).fetchall()

            conn.close()
            candidates = [dict(r) for r in rows]

            if not candidates:
                return []

            # Re-rank: boost cases whose crime_type matches the detected type
            q_lower = query.lower()
            for c in candidates:
                boost = 0.0
                ct = (c.get("crime_type") or "").lower()
                tags = (c.get("tags") or "[]").lower()

                if detected_type and detected_type in ct:
                    boost -= 2.0  # bm25 is negative; lower = better
                if detected_type and detected_type in tags:
                    boost -= 1.0

                # Boost if any key words from query appear in crime_type or modus_operandi
                mo = (c.get("modus_operandi") or "").lower()
                query_words_in_mo = sum(1 for w in words[:8] if w in mo)
                boost -= query_words_in_mo * 0.3

                c["_rank"] = (c.get("score") or 0) + boost

            candidates.sort(key=lambda x: x["_rank"])
            return candidates[:limit]

        except Exception:
            return []

    def get_by_crime_type(self, crime_type: str, limit: int = 5) -> list[dict]:
        """Fetch cases by crime type keyword."""
        if not self._available:
            return []
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM solved_cases WHERE crime_type LIKE ? ORDER BY year DESC LIMIT ?",
            (f"%{crime_type}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def build_investigation_brief(self, case_facts: str, llm=None) -> str:
        """
        Given free-text case facts, find similar solved cases and build an
        AI-powered investigation brief with:
        - Similar cases and their breakthroughs
        - Consolidated evidence checklist
        - Suspect profiling guidance
        - Priority investigation steps
        """
        similar = self.search_similar(case_facts, limit=5)
        if not similar:
            similar = []

        # Build context from similar cases
        case_context = ""
        all_tips: list[str] = []
        breakthroughs: list[str] = []

        for c in similar:
            case_context += (
                f"\n\n--- {c['title']} ({c['year']}, {c['location']}) ---\n"
                f"Crime: {c['crime_type']}\n"
                f"Modus Operandi: {c['modus_operandi']}\n"
                f"Key Breakthrough: {c['breakthrough']}\n"
                f"How Solved: {c['how_solved']}\n"
                f"Outcome: {c['outcome']}\n"
            )
            if c.get("investigation_tips"):
                try:
                    tips = json.loads(c["investigation_tips"])
                    all_tips.extend(tips)
                    breakthroughs.append(c["breakthrough"])
                except Exception:
                    pass

        if llm is None:
            # Without LLM — return structured plain text
            lines = [f"CASE INTELLIGENCE BRIEF\n{'='*40}"]
            lines.append(f"\nQuery: {case_facts[:200]}")
            if similar:
                lines.append(f"\nSIMILAR SOLVED CASES ({len(similar)} found):")
                for c in similar:
                    lines.append(f"  • {c['title']} ({c['year']}, {c['location']})")
                    lines.append(f"    Breakthrough: {c['breakthrough']}")
            if all_tips:
                lines.append(f"\nINVESTIGATION TIPS FROM SIMILAR CASES:")
                seen = set()
                for tip in all_tips[:12]:
                    if tip not in seen:
                        lines.append(f"  • {tip}")
                        seen.add(tip)
            return "\n".join(lines)

        # With LLM — generate full detective brief
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"""You are a senior Karnataka State Police detective advisor with 30 years of experience.

An investigating officer has described a case. Cross-reference with similar solved Indian cases below and produce a structured investigation brief.

CURRENT CASE FACTS:
{case_facts}

SIMILAR SOLVED CASES FOR REFERENCE:
{case_context}

Produce a brief with these sections:
1. **Crime Pattern Assessment** — what type of crime is this, likely motive, risk level
2. **Similar Solved Cases** — 2-3 most relevant cases and what cracked them
3. **Priority Evidence to Collect** — numbered list of most critical items in first 48 hours
4. **Suspect Profile** — likely perpetrator characteristics based on pattern
5. **Common Investigative Mistakes to Avoid** — from the similar cases
6. **Recommended Next Steps** — specific, actionable, ordered by priority

Be direct. No disclaimers. This is for police use."""

        sys_msg = SystemMessage(content="You are a senior detective advisor for Karnataka State Police. Give direct, actionable investigative guidance. No disclaimers.")

        def _try_invoke(model):
            return model.invoke([sys_msg, HumanMessage(content=prompt)]).content

        def _get_groq_llm():
            try:
                from src.chatbot.llm_config import create_llm as _create
                return _create(provider="groq", model="llama-3.3-70b-versatile", temperature=0.3)
            except Exception:
                return None

        # If primary LLM is None (quota exhausted at init), go straight to Groq
        if llm is None:
            groq_llm = _get_groq_llm()
            if groq_llm:
                try:
                    return _try_invoke(groq_llm)
                except Exception:
                    pass
            return f"[LLM unavailable — showing pattern analysis]\n\n{self.build_investigation_brief(case_facts, llm=None)}"

        try:
            return _try_invoke(llm)
        except Exception as e:
            # On any failure (quota, rate limit, network), fall back to Groq
            groq_llm = _get_groq_llm()
            if groq_llm:
                try:
                    return _try_invoke(groq_llm)
                except Exception:
                    pass
            return f"[LLM unavailable — showing pattern analysis]\n\n{self.build_investigation_brief(case_facts, llm=None)}"

    def stats(self) -> dict:
        if not self._available:
            return {"total": 0, "available": False}
        conn = self._connect()
        total = conn.execute("SELECT COUNT(*) FROM solved_cases").fetchone()[0]
        types = conn.execute(
            "SELECT crime_type, COUNT(*) as n FROM solved_cases GROUP BY crime_type ORDER BY n DESC LIMIT 10"
        ).fetchall()
        states = conn.execute(
            "SELECT state, COUNT(*) as n FROM solved_cases GROUP BY state ORDER BY n DESC"
        ).fetchall()
        conn.close()
        return {
            "total": total,
            "available": True,
            "crime_types": [{"type": r["crime_type"], "count": r["n"]} for r in types],
            "states": [{"state": r["state"], "count": r["n"]} for r in states],
        }
