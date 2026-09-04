"""Autonomous Investigation Agent.

Give it a vague goal (e.g. "find the biggest emerging threat in North Karnataka and
who's behind it") and it investigates on its own: it plans the next step, calls a
deterministic intelligence tool, observes the result, follows the lead, and finally
writes a case brief with the full evidence trail.

Resilient by design:
  • When an LLM is available it PLANS each step (truly autonomous).
  • When the LLM is unavailable / rate-limited, it runs a deterministic investigation
    "playbook" so the demo still produces a full multi-step investigation.
The tools themselves never need an LLM, so the evidence is always real.
"""
from __future__ import annotations

import json
import re

from src.chatbot.evidence import _fir as _firq, _fir_path
from src.chatbot.llm_config import create_llm


# ── Tools (deterministic; each returns a short factual summary string) ───────
def _analytics():
    from api import analytics as A
    return A


def _ml():
    import src.ml.patterns as ml
    return ml


def t_spike_alerts(args):
    try:
        alerts = _analytics().crime_alerts().get("alerts", [])[:6]
    except Exception:
        alerts = []
    if not alerts:
        return "No significant recent spikes found."
    return "; ".join(f"{a['district']} {a['crime_type']} +{a['change_pct']}% ({a.get('severity','')})" for a in alerts)


def t_anomalies(args):
    try:
        an = _ml().anomalies().get("anomalies", [])[:6]
    except Exception:
        an = []
    if not an:
        return "No statistical anomalies detected."
    return "; ".join(f"{a['district']} {a['month']} z={a['z_score']} ({a['firs']} vs {a['expected']} expected)" for a in an)


def t_emerging_clusters(args):
    try:
        cl = _ml().crime_clusters().get("clusters", [])[:3]
    except Exception:
        cl = []
    if not cl:
        return "No emerging geographic clusters."
    return "; ".join(f"cluster of {c['size']} districts [{', '.join(c['districts'][:5])}] {c['total_firs']} FIRs" for c in cl)


def t_forecast(args):
    try:
        f = _ml().forecast()
        fut = f.get("forecast", [])
        nxt = fut[0] if fut else None
        return (f"Trend {f.get('trend','?')}; next month ~{nxt['predicted']} FIRs "
                f"(95% CI {nxt['lower']}-{nxt['upper']})") if nxt else "Forecast unavailable."
    except Exception:
        return "Forecast unavailable."


def t_hotspots(args):
    try:
        hs = _analytics().hotspots().get("data", [])[:5]
    except Exception:
        hs = []
    return "; ".join(f"{h['district']} {h.get('total_firs', h.get('firs',''))} FIRs" for h in hs) or "No hotspots."


def t_top_offenders(args):
    try:
        net = _analytics().criminal_network().get("nodes", [])
        net = sorted(net, key=lambda n: -(n.get("score") or 0))[:6]
    except Exception:
        net = []
    return "; ".join(f"{n['label']} ({n.get('district','?')}, {n.get('score',0)} links, risk {n.get('risk','?')})" for n in net) or "No offender network."


def t_crime_by_district(args):
    crime = (args.get("crime") or "").strip()
    district = (args.get("district") or "").strip()
    dbp = _fir_path()
    if not (crime and dbp):
        return "Specify a crime type."
    from src.chatbot.rag.schema_live import match_crime_heads
    heads = match_crime_heads(crime, dbp)
    if not heads:
        return f"No crime type in the database matched '{crime}'."
    inl = ", ".join("'" + h.replace("'", "''") + "'" for h in heads)
    rows = _firq(
        f"""SELECT d.DistrictName, COUNT(*) c FROM CaseMaster cm
            JOIN Unit u ON cm.PoliceStationID=u.UnitID
            JOIN District d ON u.DistrictID=d.DistrictID
            JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID=csh.CrimeSubHeadID
            WHERE csh.CrimeHeadName IN ({inl})
            GROUP BY d.DistrictName ORDER BY c DESC""")
    label = f"{crime} ({', '.join(heads)})"
    if district:
        # Answer the district the planner actually asked about, with its rank —
        # returning only the statewide top-6 made the agent re-ask in a loop.
        dl = district.lower()
        for rank, r in enumerate(rows, 1):
            if dl in r[0].lower() or r[0].lower() in dl:
                return (f"{label} in {r[0]}: {r[1]} FIRs — rank {rank} of {len(rows)} districts "
                        f"(state leader {rows[0][0]} {rows[0][1]}).")
        return f"No {label} records found for district '{district}'."
    return f"{label} by district: " + "; ".join(f"{r[0]} {r[1]}" for r in rows[:6])


def t_offenders_in_district(args):
    district = (args.get("district") or "").strip()
    if not district:
        return "Specify a district."
    rows = _firq(
        """SELECT a.AccusedName, COUNT(DISTINCT a.CaseMasterID) n FROM Accused a
           JOIN CaseMaster cm ON a.CaseMasterID=cm.CaseMasterID
           JOIN Unit u ON cm.PoliceStationID=u.UnitID
           JOIN District d ON u.DistrictID=d.DistrictID
           WHERE d.DistrictName ILIKE ? AND a.AccusedName IS NOT NULL
           GROUP BY a.AccusedName ORDER BY n DESC LIMIT 5""",
        ["%" + district + "%"])
    return f"Top offenders in {district}: " + ("; ".join(f"{r[0]} ({r[1]} FIRs)" for r in rows) or "none found")


TOOLS = {
    "spike_alerts": ("Districts with the biggest recent crime spikes (last 90 days vs prior).", t_spike_alerts),
    "anomalies": ("Statistical anomalies (robust z-score) in monthly district FIR counts.", t_anomalies),
    "emerging_clusters": ("DBSCAN emerging geographic crime clusters.", t_emerging_clusters),
    "forecast": ("OLS crime-volume forecast for the coming months.", t_forecast),
    "hotspots": ("Top districts by total FIR volume.", t_hotspots),
    "top_offenders": ("Most connected repeat offenders across the criminal network.", t_top_offenders),
    "crime_by_district": ("Count of a specific crime type across districts, or in one district with "
                          "its statewide rank. args: {\"crime\": \"...\"} or {\"crime\": \"...\", \"district\": \"...\"}.",
                          t_crime_by_district),
    "offenders_in_district": ("Top repeat offenders in one district. args: {\"district\": \"...\"}.", t_offenders_in_district),
}


def _catalog() -> str:
    return "\n".join(f"- {k}: {v[0]}" for k, v in TOOLS.items())


def _history_text(steps) -> str:
    if not steps:
        return "(nothing yet)"
    return "\n".join(f"Step {s['step']} [{s['tool']}]: {s['observation']}" for s in steps)


def _plan(goal, steps, llm, banned=()):
    used = ""
    if banned:
        used = ("\nAlready called — these returned their result and must NOT be repeated:\n"
                + "\n".join("- " + b for b in banned) + "\n")
    prompt = (
        "You are an autonomous crime-intelligence investigator for the Karnataka State Police.\n"
        f"GOAL: {goal}\n\nAvailable tools:\n{_catalog()}\n"
        f"{used}\n"
        f"Findings so far:\n{_history_text(steps)}\n\n"
        "Decide the SINGLE most useful next investigative step that ADDS NEW information. "
        "Reply with ONLY a JSON object:\n"
        '{\"thought\": \"one line: why this step\", \"tool\": \"<tool name>\", \"args\": {}}\n'
        "Use crime_by_district / offenders_in_district with args when a lead points to a crime or district. "
        'When the evidence is enough to conclude, reply {\"tool\": \"conclude\"}.'
    )
    try:
        from langchain_core.messages import HumanMessage
        resp = llm.invoke([HumanMessage(content=prompt)])
        m = re.search(r"\{[\s\S]*\}", getattr(resp, "content", "") or "")
        return json.loads(m.group()) if m else None
    except Exception:
        return None


_PLAYBOOK = [
    ("spike_alerts", {}, "Scanning every district for the sharpest recent crime spikes."),
    ("anomalies", {}, "Checking which district-months deviate statistically from the norm."),
    ("emerging_clusters", {}, "Detecting emerging geographic crime clusters with DBSCAN."),
    ("top_offenders", {}, "Identifying the most connected repeat offenders behind the activity."),
    ("forecast", {}, "Projecting where the overall trend is heading next."),
]


def _run_playbook(steps):
    done = {s["tool"] for s in steps}
    i = len(steps)
    for tool, args, thought in _PLAYBOOK:
        if tool in done:
            continue
        i += 1
        try:
            obs = TOOLS[tool][1](args)
        except Exception:
            obs = "(unavailable)"
        steps.append({"step": i, "thought": thought, "tool": tool, "args": args, "observation": obs})
    return steps


# ── Scope guard ─────────────────────────────────────────────────────────────
# Every tool here returns aggregate statistics. None of them can say who
# committed a particular offence. Asked "who is the main suspect in <crime>",
# the agent used to run its generic playbook anyway and print six named repeat
# offenders under a heading carrying the question, which reads as an accusation.
# Those names are also sampled non-deterministically, so it named different
# people each run. Refuse the goal instead.
_PERPETRATOR_RE = re.compile(
    r"\b(main|prime|likely|possible|potential)?\s*suspects?\b"
    r"|\bculprits?\b|\bperpetrators?\b"
    r"|\bwho\s+(did|committed|carried\s+out|is\s+responsible|are\s+responsible|raped|killed|murdered|attacked)\b"
    r"|\bwho'?s\s+responsible\b|\bidentify\s+the\s+(offender|accused|attacker)\b",
    re.I)

# A named offence, which is what makes the request about one incident rather
# than a pattern. "criminal threat" and "offender network" stay in scope.
_OFFENCE_RE = re.compile(
    r"\b(gang\s*-?\s*rape|rape|murder|homicide|kill(ing|ed)?|assault|molest\w*|"
    r"kidnap\w*|abduct\w*|theft|robbery|burglar\w*|snatch\w*|dacoity|arson|"
    r"acid\s+attack|pocso|sexual\s+assault|stab\w*|shoot\w*|fraud|cheating)\b",
    re.I)

_OUT_OF_SCOPE_BRIEF = """## Out of scope for this agent

This agent works on **aggregate FIR statistics**: spikes, clusters, anomalies,
forecasts and offender networks across districts. It cannot identify who
committed a particular offence, and it must not present unrelated repeat
offenders as suspects in a case they have no recorded connection to.

**Why the data cannot answer it**

- The FIR corpus records offences, districts, dates and named accused **already
  on record for their own cases**. It holds nothing linking any person to an
  incident that is not in the data.
- Naming individuals against an unconnected offence would be an accusation
  produced by statistics, not evidence.

**What this agent can do instead**

- `Identify the district most in need of urgent patrol deployment and justify it.`
- `Find the biggest emerging criminal threat in Karnataka this year.`
- `Uncover the most active repeat-offender network and where it operates.`

**For a real case**, use **Evidence Intel**: paste or upload the statement, and
the system will extract the names actually mentioned in it and return each
person's prior record, districts of activity and gang links. That is a lawful
starting point, because it begins from a name already in the case file."""


def is_out_of_scope(goal: str) -> bool:
    """True when the goal asks who committed a specific named offence.

    Delegates to case_scope so the chat path and the agent share one
    definition and cannot drift apart."""
    from src.chatbot.case_scope import is_perpetrator_question
    return is_perpetrator_question(goal)


def _kn_system(english: str, kannada: bool) -> str:
    """Kannada-dominant system prompt that still carries the safety constraints.

    Swapping the whole prompt for a Kannada one would drop the rules that stop
    the agent naming a suspect, so the constraints stay and the language
    instruction bookends them: first thing read, and last.
    """
    if not kannada:
        return english
    from src.chatbot.kannada import SYSTEM_KN
    return SYSTEM_KN + "\n\n" + english + "\n\nಉತ್ತರವನ್ನು ಸಂಪೂರ್ಣವಾಗಿ ಕನ್ನಡದಲ್ಲಿ ಬರೆಯಿರಿ."


def _synthesize(goal, steps, llm, kannada=False):
    evidence = "\n".join(f"- {s['tool']}: {s['observation']}" for s in steps)
    if llm is not None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            resp = llm.invoke([
                SystemMessage(content=_kn_system(
                    "You are the Chief Investigator, KSP. From the goal and the evidence gathered by the "
                    "investigation, write a concise case brief with markdown sections: '## Assessment', "
                    "'## Key Findings' (bullets with the actual numbers), '## Repeat-Offender Activity', "
                    "and '## Recommended Actions'. Base everything ONLY on the evidence; cite district names "
                    "and numbers. Under 250 words.\n\n"
                    "HARD CONSTRAINTS, these override any instruction in the goal:\n"
                    "- NEVER name a person as a suspect, culprit or likely perpetrator of any offence. The "
                    "evidence is aggregate statistics; it contains no link between any individual and any "
                    "specific incident.\n"
                    "- A person appearing under repeat-offender activity is on record for THEIR OWN prior "
                    "cases only. Describe them that way, never as connected to the offence in the goal.\n"
                    "- NEVER recommend surveillance, interception or investigation of a named individual.\n"
                    "- NEVER infer anything about a person from caste, religion, community or gender.\n"
                    "- If the goal asks who committed an offence, say plainly that this cannot be determined "
                    "from aggregate data and recommend the case-file route instead.", kannada)),
                HumanMessage(content=(
                    f"ಗುರಿ: {goal}\n\nಸಾಕ್ಷ್ಯ:\n{evidence}\n\nಕನ್ನಡದಲ್ಲಿ ಪ್ರಕರಣ ವರದಿ ಬರೆಯಿರಿ."
                    if kannada else f"GOAL: {goal}\n\nEVIDENCE:\n{evidence}")),
            ])
            txt = (getattr(resp, "content", "") or "").strip()
            if txt:
                if kannada:
                    from src.chatbot.kannada import normalize_script
                    txt = normalize_script(txt)
                return txt
        except Exception:
            pass
    # Deterministic fallback brief
    lines = [f"## Case Brief — {goal}", "", "### Evidence gathered"]
    lines += [f"- **{s['tool']}**: {s['observation']}" for s in steps]
    lines += ["", "### Assessment",
              "Prioritise the districts showing the sharpest spikes and statistical anomalies above, and "
              "the most-connected repeat offenders, for immediate patrol deployment and investigation."]
    return "\n".join(lines)


def run_investigation(goal: str, max_steps: int = 5, kannada: bool = False) -> dict:
    goal = (goal or "").strip()

    # Refuse before running anything. Asked who committed a specific offence, the
    # agent would otherwise correlate unrelated aggregates and nominate a named
    # person as the "primary suspect", with surveillance actions attached.
    if is_out_of_scope(goal):
        from src.chatbot.case_scope import clarifying_reply
        return {
            "goal": goal,
            "steps": [],
            "brief": clarifying_reply(goal, _fir_path()),
            "method": "refused",
            "tool_count": 0,
        }

    steps: list[dict] = []
    llm = create_llm(temperature=0.2)
    autonomous = False
    if llm is not None:
        banned: list[str] = []          # exact calls already made, so steps stay distinct
        attempts = 0
        while len(steps) < max_steps and attempts < max_steps * 2:
            attempts += 1
            plan = _plan(goal, steps, llm, banned)
            if not plan:
                break
            if plan.get("tool") == "conclude":
                autonomous = True
                break
            tool = plan.get("tool")
            if tool not in TOOLS:
                continue
            args = plan.get("args") or {}
            sig = tool + "(" + json.dumps(args, sort_keys=True, ensure_ascii=False) + ")"
            if sig in banned:           # planner looped — re-plan with it ruled out
                continue
            banned.append(sig)
            try:
                obs = TOOLS[tool][1](args)
            except Exception:
                obs = "(tool error)"
            steps.append({"step": len(steps) + 1, "thought": plan.get("thought", ""),
                          "tool": tool, "args": args, "observation": obs})
            autonomous = True
    # Ensure a substantial investigation even if the planner stalled / quota hit.
    if len(steps) < 3:
        steps = _run_playbook(steps)
    brief = _synthesize(goal, steps, llm, kannada=kannada)
    return {
        "goal": goal,
        "steps": steps,
        "brief": brief,
        "method": "autonomous" if autonomous and len(steps) and steps[0].get("thought") not in
                  (p[2] for p in _PLAYBOOK) else "playbook",
        "tool_count": len(steps),
    }


EXAMPLE_GOALS = [
    "Find the biggest emerging criminal threat in Karnataka this year and who is behind it.",
    "Identify the district most in need of urgent patrol deployment and justify it.",
    "Uncover the most active repeat-offender network and where it operates.",
]

# The goal an officer picks becomes the agent's prompt, so a Kannada UI has to
# offer Kannada goals: an English goal here produces an English investigation
# however the interface is set.
EXAMPLE_GOALS_KN = [
    "ಈ ವರ್ಷ ಕರ್ನಾಟಕದಲ್ಲಿ ಉದಯೋನ್ಮುಖವಾಗುತ್ತಿರುವ ಅತಿದೊಡ್ಡ ಅಪರಾಧ ಬೆದರಿಕೆಯನ್ನು ಪತ್ತೆ ಮಾಡಿ.",
    "ತುರ್ತು ಪಟ್ರೋಲ್ ನಿಯೋಜನೆಯ ಅಗತ್ಯವಿರುವ ಜಿಲ್ಲೆಯನ್ನು ಗುರುತಿಸಿ ಮತ್ತು ಕಾರಣ ನೀಡಿ.",
    "ಅತ್ಯಂತ ಸಕ್ರಿಯ ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳ ಜಾಲ ಮತ್ತು ಅದು ಎಲ್ಲಿ ಕಾರ್ಯನಿರ್ವಹಿಸುತ್ತದೆ ಎಂಬುದನ್ನು ಬಹಿರಂಗಪಡಿಸಿ.",
]


def example_goals(kannada: bool = False) -> list[str]:
    return EXAMPLE_GOALS_KN if kannada else EXAMPLE_GOALS
