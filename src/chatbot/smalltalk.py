"""Detect greetings, help requests, and small talk."""

import re

GREETING = re.compile(
    r"^(hi|hello|hey|howdy|hola|good\s*(morning|evening|afternoon|day)|sup|yo|"
    r"namaste|vanakkam|namaskara|namaskaara|shubhodaya|shubha\s*sandya)[!.?\s]*$",
    re.I,
)
THANKS = re.compile(r"^(thanks|thank you|thx|ty|thank\s*u)[!.?\s]*$", re.I)
HELP = re.compile(
    r"^(help|\?|what can you do|how does this work|how to use|what do you do)[?.!\s]*$",
    re.I,
)
BYE = re.compile(r"^(bye|goodbye|see you|exit|quit|cya)[!.?\s]*$", re.I)

WHO_AM_I = re.compile(
    r"(what(\'?s|\s+is)\s+your\s+name|who\s+are\s+you|what\s+are\s+you|ur\s+name|your\s+name|"
    r"introduce\s+yourself|tell\s+me\s+about\s+yourself|who\s+r\s+u|"
    # Kannada romanized: "yaru ninu/neenu/neevu" = who are you
    r"yaru\s+ni(nu|nnu|vu|vu)|neevu\s+yaru|neenu\s+yaru|ninu\s+yaru|"
    r"nimage\s+hesaru|ninna\s+hesaru|nim\s+hesaru)",
    re.I,
)

HOW_ARE_YOU = re.compile(
    r"^(how\s+are\s+you|how\s+r\s+u|how\s+are\s+u|how\s+you\s+doing|you\s+good|hows\s+it|"
    r"what\'?s\s+up|wassup|whats\s+good)[?.!\s]*$",
    re.I,
)

LANGUAGE_Q = re.compile(
    r"\b(speak|understand|know|use|write\s+in|respond\s+in|reply\s+in|can\s+you)\b.{0,30}"
    r"\b(kannada|hindi|telugu|tamil|urdu|marathi|english)\b|"
    r"\b(kannada|hindi|telugu|tamil|urdu|marathi)\b.{0,20}\b(speak|understand|know|support)\b",
    re.I,
)

WELCOME_MESSAGE = """Hello! I'm **KSP Crime Intelligence** — your AI assistant for Karnataka State Police.

Ask me in **English or ಕನ್ನಡ**, by text or voice. I'll pull from our crime databases — and search the web when something isn't on file.

I can query crime data across three databases:
  • FIR records (2020–2024) — 500,000 FIRs across 31 districts, crime types, arrests
  • NCRB national statistics — benchmarks, rates, metro comparisons
  • Court cases (2010–2018) — convictions, acquittals, durations

Try asking:
  • How many thefts in Bengaluru in 2024?
  • Show me cyber crime trends in Karnataka
  • Top repeat offender profiles
  • Convicted cases in Hassan district 2017"""

HELP_MESSAGE = """Here's what I can help with:

**FIR & Crime Data**
  • Crime counts by district, year, crime type
  • Arrest and chargesheet rates
  • Repeat offender profiles

**NCRB Statistics**
  • National and city-level crime rates
  • Cyber, economic, women & children crime stats

**Court Cases (2010–2018)**
  • Convictions and acquittals by district
  • Case duration analysis

**Case Intelligence**
  • Cross-reference with 50+ solved Indian cases
  • Investigation brief generation

**Browse Records**
  • Scroll through 500,000 FIRs and 895,000+ accused persons

I can also search the web when a question falls outside our records."""


def detect_smalltalk(text: str) -> str | None:
    """Return response text for greetings/help/smalltalk, or None if it's a data question."""
    q = text.strip()
    if GREETING.match(q):
        return WELCOME_MESSAGE
    if WHO_AM_I.search(q):
        # Detect Kannada romanized "yaru" to reply in Kannada
        if re.search(r"\byaru\b|\bninage\b|\bninna\b", q, re.I):
            return (
                "ನಾನು **KSP Crime Intelligence** — ಕರ್ನಾಟಕ ರಾಜ್ಯ ಪೊಲೀಸ್‌ಗಾಗಿ ನಿರ್ಮಿಸಲಾದ AI ಸಹಾಯಕ. "
                "FIR ದಾಖಲೆಗಳು, NCRB ಅಂಕಿಅಂಶಗಳು ಮತ್ತು ನ್ಯಾಯಾಲಯ ಪ್ರಕರಣಗಳನ್ನು ಪ್ರಶ್ನಿಸಲು ನನ್ನನ್ನು ಬಳಸಿ. "
                "500,000 FIR ದಾಖಲೆಗಳು, ಅಪರಾಧ ಜಾಲ ವಿಶ್ಲೇಷಣೆ ಮತ್ತು ಮುನ್ಸೂಚನೆ ಒಳನೋಟಗಳಲ್ಲಿ ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ."
            )
        return (
            "I'm **KSP Crime Intelligence**, an AI assistant built for Karnataka State Police. "
            "I help investigators query FIR records, NCRB statistics, court case data, "
            "cross-reference solved cases, and search the web when something isn't on file."
        )
    if HOW_ARE_YOU.match(q):
        return "I'm operational and ready to assist! Ask me anything about Karnataka crime data."
    if LANGUAGE_Q.search(q):
        return (
            "Yes! I support both **English** and **ಕನ್ನಡ (Kannada)**.\n\n"
            "To use Kannada, switch the language toggle in the top bar to **KN** — "
            "I will then respond in Kannada.\n\n"
            "You can also just type your question in Kannada directly and I will understand it."
        )
    if THANKS.match(q):
        return "You're welcome! Let me know if you need anything else."
    if HELP.match(q):
        return HELP_MESSAGE
    if BYE.match(q):
        return "Goodbye! Stay safe."
    return None
