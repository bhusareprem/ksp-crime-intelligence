"""Scope guard for "who committed this offence" questions.

Neither the chat path nor the investigation agent can answer that. The FIR corpus
records offences, and the accused already on record for *their own* cases. It
holds nothing linking any person to an incident that is not in the data.

Unguarded, both paths produced an accusation rather than an answer:

  * the agent correlated unrelated aggregates and named an individual as the
    "primary suspect", with surveillance actions attached
  * the chat path wrote SQL hunting for accused names, found nothing, fell
    through to a web search, and returned school staff from an unrelated case in
    another state as the "typical suspects"

Refusing flatly is correct but unhelpful, so this module builds a reply that asks
for the details that would make the question answerable, and offers what the data
can show immediately.
"""
from __future__ import annotations

import re

# Asking for the person responsible.
_PERPETRATOR_RE = re.compile(
    r"\b(main|prime|likely|possible|potential)?\s*suspects?\b"
    r"|\bculprits?\b|\bperpetrators?\b"
    r"|\bwho\s+(did|committed|carried\s+out|is\s+responsible|are\s+responsible|"
    r"raped|killed|murdered|attacked|stole|robbed)\b"
    r"|\bwho'?s\s+responsible\b"
    # "Who is behind the murder in Belagavi" and "name the person responsible
    # for the theft in Hubli" both asked the guard's question and both got
    # through: the first because "behind" was missing, the second because only
    # "identify the offender" was covered and not "name the person".
    r"|\bwho(?:\s+is|'?s|\s+are|\s+was|\s+were)?\s+behind\b"
    # Requires a word for a *person* after the verb. A bare "responsible for the"
    # was tried and rejected: it also refused "which district is responsible for
    # the highest theft rate", which is an ordinary analytical question.
    r"|\b(name|identify|tell\s+me)\s+(the\s+|who\s+the\s+)?"
    r"(person|people|man|men|woman|women|individual|offender|accused|attacker|"
    r"culprit|suspect|perpetrator)s?\b",
    re.I)

# A named offence, which is what makes it about one incident rather than a
# pattern. "criminal threat" and "offender network" stay in scope deliberately.
# Verb forms matter as much as nouns: "who stole the bike" is the same request as
# "who is the suspect in the theft", so past tenses are included.
_OFFENCE_RE = re.compile(
    r"\b(gang\s*-?\s*rape|rape\w*|murder\w*|homicide|kill\w*|assault\w*|molest\w*|"
    r"kidnap\w*|abduct\w*|theft\w*|stole|stolen|steal\w*|robber\w*|robbed|"
    r"burglar\w*|snatch\w*|dacoity|arson|acid\s+attack|pocso|sexual\s+assault|"
    r"stab\w*|shoot\w*|shot\b|fraud\w*|cheating|attack\w*)\b",
    re.I)

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


# An FIR or case number in the question. The guard stands down when one is
# present, because the objection it enforces no longer applies.
_CASE_NO_RE = re.compile(
    r"\b(?:fir|case|crime)\s*(?:no\.?|number|#)?\s*[:#]?\s*(?:\d{6,20}|\d{1,5}\s*/\s*\d{4})\b",
    re.I)


def has_case_number(text: str) -> bool:
    return bool(_CASE_NO_RE.search(text or ""))


def is_perpetrator_question(text: str) -> bool:
    """True when the text asks who committed a specific named offence.

    A supplied FIR number is the exception. The guard exists because aggregate
    statistics cannot link a person to an incident, so picking a name out of
    them would be an accusation produced by arithmetic. An FIR number is that
    link: the case record already names who is on record for it, and reading a
    record back is not inference.

    Without this the system contradicted itself. It told the officer "give me
    the FIR number and I can pull that case and everyone recorded on it", and
    then refused again when they did, because the words "who committed" were
    still in the question they had been asked to add details to.
    """
    t = text or ""
    if has_case_number(t):
        return False
    return bool(_PERPETRATOR_RE.search(t) and _OFFENCE_RE.search(t))


def _known_signals(text: str, fir_path: str | None):
    """What the question already tells us, so we only ask for what is missing."""
    heads, districts = [], []
    if fir_path:
        try:
            from src.chatbot.rag.schema_live import match_crime_heads, match_districts
            heads = match_crime_heads(text, fir_path)[:3]
            districts = match_districts(text, fir_path)[:2]
        except Exception:
            pass
    year = _YEAR_RE.search(text or "")
    return heads, districts, (year.group(1) if year else None)


def _counts_for(heads: list[str], districts: list[str], fir_path: str | None):
    """Real figures for the offence asked about, so the reply is useful, not just a refusal."""
    if not (heads and fir_path):
        return None, []
    try:
        import duckdb
        inl = ", ".join("'" + h.replace("'", "''") + "'" for h in heads)
        con = duckdb.connect(fir_path, read_only=True,
                             config={"enable_external_access": False})
        try:
            base = ("FROM CaseMaster cm JOIN Unit u ON cm.PoliceStationID=u.UnitID "
                    "JOIN District d ON u.DistrictID=d.DistrictID "
                    "JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID=csh.CrimeSubHeadID "
                    f"WHERE csh.CrimeHeadName IN ({inl})")
            total = con.execute("SELECT COUNT(*) " + base).fetchone()[0]
            top = con.execute("SELECT d.DistrictName, COUNT(*) c " + base +
                              " GROUP BY 1 ORDER BY c DESC LIMIT 3").fetchall()
            return total, top
        finally:
            con.close()
    except Exception:
        return None, []


def clarifying_reply(text: str, fir_path: str | None = None) -> str:
    """Explain what cannot be answered, ask for what would make it answerable,
    and offer what the data can show right now."""
    heads, districts, year = _known_signals(text, fir_path)
    label = heads[0] if heads else "this offence"
    total, top = _counts_for(heads, districts, fir_path)

    out = [
        "I cannot name a suspect for a specific offence, and I should say why "
        "rather than guess.",
        "",
        "The FIR data records offences and the people already on record for "
        "**their own** past cases. Nothing in it links a person to an incident "
        "that is not in the data. Picking a name out of it would be an "
        "accusation produced by statistics.",
        "",
        "**To take this further I need a few details:**",
    ]

    asks = []
    if not districts:
        asks.append("Which **district or police station** is the case registered in?")
    if not year:
        asks.append("**When** was it reported? A date or even the year is enough.")
    asks.append("Do you have the **FIR number**? I can pull that case and everyone "
                "recorded on it.")
    asks.append("Do you have the **complaint or witness statement**? Paste it into "
                "**Evidence Intel** and I will return the prior record, districts of "
                "activity and gang links for every person named in it.")
    out += [f"{i}. {a}" for i, a in enumerate(asks, 1)]

    out += ["", "**What I can show you right now:**"]
    if total:
        where = ""
        if top:
            where = " Highest counts: " + ", ".join(f"{d} {c}" for d, c in top) + "."
        out.append(f"- **{total:,} {label} FIRs** are on record for 2020 to 2024.{where}")
        if districts:
            out.append(f"- The same broken down for **{districts[0]}**, by year or by police station.")
        else:
            out.append("- The same broken down by district, by year, or by police station.")
        # "cases on record", never "convictions": the schema stops at case status
        # and never records a verdict.
        out.append(f"- People with prior **{label}** cases on record in a district you name.")
    else:
        out.append("- Case counts by district, year and crime type across 500,000 FIRs.")
        out.append("- People with prior records on file in a district you name.")
    out.append("- Recent spikes and emerging clusters, if you want the wider pattern.")

    out += ["", "_Ask any of those and I will run it against the records._"]
    return "\n".join(out)
