#!/usr/bin/env python3
"""
KSP Crime Intelligence Chatbot — Phase 2
Natural language → SQL over ksp_crime, criminal, and cases databases.

Usage:
    python chat.py
    python chat.py "How many thefts in Bengaluru in 2024?"
    python chat.py --show-sql

Environment:
    OPENAI_API_KEY   — enables full LangChain NL→SQL (optional)
    OPENAI_MODEL     — default gpt-4o-mini
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))

from src.chatbot.engine import CrimeChatbot


def main():
    parser = argparse.ArgumentParser(description="KSP Crime Chatbot")
    parser.add_argument("question", nargs="?", help="Single question (omit for interactive mode)")
    parser.add_argument("--show-sql", action="store_true", help="Show generated SQL")
    parser.add_argument("--db", type=str, help="Force database: ksp_crime, criminal, cases")
    args = parser.parse_args()

    bot = CrimeChatbot()

    available = bot.db.available()
    missing = [k for k, v in available.items() if not v]
    if missing:
        print(f"Warning: missing databases: {', '.join(missing)}")
        print("Run build_db.py / build_criminal_db.py / build_cases_db.py first.\n")

    if not any(available.values()):
        print("No databases found in data/. Exiting.")
        sys.exit(1)

    print("=" * 60)
    print("KSP Crime Intelligence Chatbot")
    print("=" * 60)
    print("Databases:", ", ".join(k for k, v in available.items() if v))
    if bot._get_llm():
        print("Mode: LangChain + OpenAI (full NL-to-SQL)")
    else:
        print("Mode: Rule-based fallback (set OPENAI_API_KEY for full NL-to-SQL)")
    print("Type 'quit' to exit.\n")

    def handle(question: str):
        if args.db:
            from src.chatbot.router import route_question
            import src.chatbot.router as router_mod
            original = router_mod.route_question
            router_mod.route_question = lambda q: args.db
            resp = bot.ask(question)
            router_mod.route_question = original
        else:
            resp = bot.ask(question)

        print(f"\n[{resp.database}] ({resp.source})")
        print(resp.answer)
        if args.show_sql and resp.sql:
            print(f"\nSQL:\n{resp.sql}")

    if args.question:
        handle(args.question)
        return

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        handle(question)
        print()


if __name__ == "__main__":
    main()
