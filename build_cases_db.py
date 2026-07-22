#!/usr/bin/env python3
"""
Build cases.db — Karnataka criminal judicial cases (DDL dataset 2010-2018)

Criminal cases are identified using judge_case_merge_key.csv, which per the
DDL dataset documentation contains only criminal cases with judge matching.

Usage:
    python build_cases_db.py
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.build_cases_db import build_cases_db


def main():
    parser = argparse.ArgumentParser(description="Build Karnataka criminal cases database")
    parser.add_argument(
        "--cases-dir",
        default=str(PROJECT_ROOT / "cases"),
        help="Directory with DDL CSV files",
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "cases.db"),
        help="Output DuckDB path",
    )
    args = parser.parse_args()

    cases_dir = Path(args.cases_dir)
    db_path = Path(args.db)

    if not cases_dir.exists():
        print(f"ERROR: cases directory not found at {cases_dir}")
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("KSP Cases Database Builder (Karnataka Criminal 2010-2018)")
    print("=" * 60)
    print(f"Source: {cases_dir}")
    print(f"Output: {db_path}")
    print()

    stats = build_cases_db(cases_dir, db_path)

    print("\n" + "=" * 60)
    print("CASES DATABASE SUMMARY")
    print("=" * 60)
    for key, val in stats.items():
        print(f"  {key}: {val:,}" if isinstance(val, int) else f"  {key}: {val}")

    db_size = db_path.stat().st_size / 1_048_576
    print(f"\nDatabase size: {db_size:.1f} MB")
    print(f"Database ready at: {db_path}")


if __name__ == "__main__":
    main()
