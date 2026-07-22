#!/usr/bin/env python3
"""
Build criminal.db (DuckDB) from FIR_Details_Data.csv
Fast vectorized pipeline for network analysis and behavioral profiling.

Usage:
    python build_criminal_db.py
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.build_criminal_db import build_criminal_db


def main():
    parser = argparse.ArgumentParser(description="Build KSP Criminal Database (DuckDB)")
    parser.add_argument(
        "--csv",
        default=str(PROJECT_ROOT / "FIR_Details_Data.csv" / "FIR_Details_Data.csv"),
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "criminal.db"),
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    db_path = Path(args.db)

    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("KSP Criminal Database Builder (DuckDB)")
    print("=" * 60)
    print(f"Source: {csv_path}")
    print(f"Output: {db_path}")
    print(f"Size:   {csv_path.stat().st_size / 1_048_576:.1f} MB")
    print()

    stats = build_criminal_db(csv_path, db_path)

    print("\n" + "=" * 60)
    print("CRIMINAL DATABASE SUMMARY")
    print("=" * 60)
    for key, val in stats.items():
        print(f"  {key}: {val:,}")

    db_size = db_path.stat().st_size / 1_048_576
    print(f"\nDatabase size: {db_size:.1f} MB")
    print(f"Database ready at: {db_path}")
    print("\nQuery example (Python):")
    print("  import duckdb")
    print(f"  con = duckdb.connect('{db_path.as_posix()}')")
    print("  con.execute('SELECT * FROM criminal_profiles ORDER BY repeat_offender_score DESC LIMIT 10').df()")


if __name__ == "__main__":
    main()
