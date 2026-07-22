#!/usr/bin/env python3
"""End-to-end chatbot smoke tests — SQL, routing, multi-turn context."""

from __future__ import annotations

import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))

from src.chatbot.engine import CrimeChatbot
from src.chatbot.llm_config import load_env

load_env(PROJECT)


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    error: str = ""


@dataclass
class TestReport:
    results: list[TestResult] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        self.results.append(TestResult(name, True, detail))

    def fail(self, name: str, detail: str = "", error: str = "") -> None:
        self.results.append(TestResult(name, False, detail, error))

    def summary(self) -> tuple[int, int]:
        passed = sum(1 for r in self.results if r.passed)
        return passed, len(self.results)


def count_districts_in_data(data: str) -> int:
    """Rough count of Karnataka district names in formatted dataframe output."""
    known = [
        "Bagalkot", "Ballari", "Belagavi", "Bengaluru", "Bidar", "Chamarajanagar",
        "Chikkaballapur", "Chikkamagaluru", "Chitradurga", "Davanagere", "Dharwad",
        "Dakshina Kannada", "Gadag", "Hassan", "Haveri", "Kalaburagi", "Kodagu",
        "Kolar", "Koppal", "Mandya", "Mysuru", "Raichur", "Ramanagara", "Shivamogga",
        "Tumakuru", "Udupi", "Uttara Kannada", "Vijayapura", "Vijayanagara", "Yadgir",
    ]
    return sum(1 for d in known if d in data)


def run_tests() -> TestReport:
    report = TestReport()
    bot = CrimeChatbot(data_dir=PROJECT / "data")

    dbs = bot.db.available()
    if not any(dbs.values()):
        report.fail("databases available", error="No databases found in data/")
        return report
    report.ok("databases available", str(dbs))

    llm = bot.llm_status()
    report.ok("llm config", f"enabled={llm['enabled']} provider={llm['provider']}")

    # --- Single-turn tests ---
    singles = [
        ("greeting", "hi", lambda r: r.source == "groq" or "Hello" in r.answer or "KSP" in r.answer),
        ("typo normalize", "five me top criminal in Bagalkot", lambda r: r.database == "ksp_crime" and bool(r.sql)),
        ("top names gadag", "top 10 criminal names in Gadag district", lambda r: r.database == "ksp_crime" and bool(r.data) and bool(r.sql)),
        ("every district", "give me top criminal in every district", lambda r: count_districts_in_data(r.data) >= 25),
        ("person details", "give me details about rudra narang", lambda r: r.database == "criminal" and "Rudra" in r.data and r.data.count("fir_id") >= 0 or "100" in r.data),
        ("pocso by district", "how many POCSO cases in each district", lambda r: bool(r.sql) and len(r.data) > 50),
        ("murder rate", "top districts by murder rate in 2023", lambda r: r.database == "ksp_crime" and bool(r.sql)),
        ("ncrb cyber", "NCRB cyber crimes in Bengaluru 2024", lambda r: r.database == "ksp_crime" and bool(r.data)),
        ("theft bengaluru", "how many thefts in Bengaluru in 2024", lambda r: r.database == "criminal" and bool(r.sql)),
        ("convictions", "convicted cases in Bengaluru 2017", lambda r: r.database == "cases" and bool(r.sql)),
        ("repeat offenders", "top repeat offender profiles", lambda r: r.database == "criminal" and bool(r.data)),
        ("district overview", "crime overview in Dharwad", lambda r: r.database == "criminal" and bool(r.data)),
    ]

    for name, question, check in singles:
        try:
            resp = bot.ask(question)
            if not resp.answer.strip():
                report.fail(name, question, "Empty answer")
            elif not check(resp):
                report.fail(
                    name,
                    f"db={resp.database} sql_len={len(resp.sql)} data_len={len(resp.data)}",
                    resp.answer[:200],
                )
            else:
                report.ok(name, f"db={resp.database}")
        except Exception as e:
            report.fail(name, question, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    # --- Multi-turn tests ---
    try:
        history: list[dict] = []
        r1 = bot.ask("give me top criminal in every district", history)
        history.append({"role": "user", "content": "give me top criminal in every district"})
        history.append({"role": "assistant", "content": r1.answer})
        if count_districts_in_data(r1.data) < 25:
            report.fail("multi-turn turn1", "expected >=25 districts", r1.data[:300])
        else:
            report.ok("multi-turn turn1", f"districts~{count_districts_in_data(r1.data)}")

        r2 = bot.ask("where are other districts", history)
        if count_districts_in_data(r2.data) < 25 and count_districts_in_data(r2.answer) < 15:
            report.fail("multi-turn follow-up", "other districts", r2.answer[:300])
        elif re.search(r"would you like me", r2.answer, re.I):
            report.fail("multi-turn follow-up", "asked clarifying question instead of answering", r2.answer[:200])
        else:
            report.ok("multi-turn follow-up", f"db={r2.database}")

        history.append({"role": "user", "content": "where are other districts"})
        history.append({"role": "assistant", "content": r2.answer})
        r3 = bot.ask("give me details about rudra narang", history)
        if r3.database != "criminal" or "Rudra" not in (r3.data + r3.answer):
            report.fail("multi-turn person", f"db={r3.database}", r3.answer[:200])
        else:
            report.ok("multi-turn person", f"rows in data={r3.data.count(chr(10))}")
    except Exception as e:
        report.fail("multi-turn session", error=f"{type(e).__name__}: {e}")

    # --- Name follow-up from history ---
    try:
        hist = [
            {"role": "user", "content": "top criminal in Bagalkot district"},
            {"role": "assistant", "content": "Rudra Narang has 26 linked FIRs in Bagalkot."},
        ]
        r = bot.ask("give me names", hist)
        if r.database != "ksp_crime":
            report.fail("name follow-up routing", f"db={r.database}", r.answer[:200])
        elif not r.data.strip() or "linked_firs" not in r.data:
            report.fail("name follow-up data", "expected name list with linked_firs", r.data[:200])
        else:
            report.ok("name follow-up", f"db={r.database}")
    except Exception as e:
        report.fail("name follow-up", error=str(e))

    # --- Edge cases ---
    edges = [
        ("empty-ish invalid district", "crimes in Atlantis district", lambda r: bool(r.answer)),
        ("nonsense person", "details about Zzzzz Nonexistent Person", lambda r: bool(r.answer)),
    ]
    for name, question, check in edges:
        try:
            resp = bot.ask(question)
            if not check(resp):
                report.fail(name, "unexpected empty", resp.answer[:100])
            else:
                report.ok(name, "handled gracefully")
        except Exception as e:
            report.fail(name, error=str(e))

    return report


def main() -> int:
    print("=" * 60)
    print("KSP Chatbot Test Suite")
    print("=" * 60)
    report = run_tests()
    passed, total = report.summary()

    for r in report.results:
        icon = "PASS" if r.passed else "FAIL"
        line = f"[{icon}] {r.name}"
        if r.detail:
            line += f" — {r.detail}"
        print(line)
        if not r.passed and r.error:
            print(f"       {r.error[:400]}")

    print("-" * 60)
    print(f"Results: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
