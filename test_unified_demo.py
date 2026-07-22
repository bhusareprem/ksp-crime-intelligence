#!/usr/bin/env python3
"""Verify unified demo database alignment."""

import json
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).parent


def main():
    data_dir = PROJECT / "data" / "unified"
    if not (data_dir / "registry.json").exists():
        data_dir = PROJECT / "data"
    reg_path = data_dir / "registry.json"
    if not reg_path.exists():
        reg_path = PROJECT / "data" / "unified_registry.json"

    ksp = data_dir / "ksp_crime.db"
    criminal = data_dir / "criminal.db"
    cases = data_dir / "cases.db"

    for p in (ksp, criminal, cases):
        if not p.exists():
            print(f"Missing: {p}")
            sys.exit(1)

    import duckdb

    print("=" * 60)
    print("UNIFIED DEMO ALIGNMENT CHECK")
    print("=" * 60)

    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        print(f"Registry: {reg.get('version')} | years {reg.get('years')}")
        print(f"  FIRs: {reg.get('fir_count'):,} | Court cases: {reg.get('court_case_count'):,}")

    sq = sqlite3.connect(ksp)
    ksp_firs = sq.execute("SELECT COUNT(*), MIN(year), MAX(year) FROM fir_records").fetchone()
    ksp_ids = {r[0] for r in sq.execute("SELECT fir_id FROM fir_records LIMIT 5000").fetchall()}
    sq.close()

    cr = duckdb.connect(str(criminal), read_only=True)
    cr_firs = cr.execute("SELECT COUNT(*), MIN(fir_year), MAX(fir_year) FROM fir_details").fetchone()
    persons = cr.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    co_links = cr.execute("SELECT COUNT(*) FROM co_accused_links").fetchone()[0]
    sample_id = cr.execute("SELECT fir_id FROM fir_details LIMIT 1").fetchone()[0]
    cr.close()

    ca = duckdb.connect(str(cases), read_only=True)
    ca_cases = ca.execute("SELECT COUNT(*), MIN(year), MAX(year) FROM cases").fetchone()
    linked = ca.execute("SELECT COUNT(*) FROM cases WHERE linked_fir_id IS NOT NULL").fetchone()[0]
    ca.close()

    print(f"\nksp_crime:     {ksp_firs[0]:,} FIRs ({ksp_firs[1]}-{ksp_firs[2]})")
    print(f"criminal:      {cr_firs[0]:,} FIRs ({cr_firs[1]}-{cr_firs[2]}) | {persons:,} persons | {co_links:,} co-accused links")
    print(f"cases:         {ca_cases[0]:,} cases ({ca_cases[1]}-{ca_cases[2]}) | {linked:,} linked to FIRs")

    # ID alignment spot-check
    sq = sqlite3.connect(ksp)
    in_ksp = sq.execute(f"SELECT COUNT(*) FROM fir_records WHERE fir_id = {sample_id}").fetchone()[0]
    sq.close()
    print(f"\nAlignment: FIR {sample_id} in ksp_crime: {'YES' if in_ksp else 'NO'}")

    if cr_firs[1] >= 2018 and ca_cases[1] >= 2018:
        print("Year alignment: PASS (2018+)")
    else:
        print("Year alignment: FAIL")
        sys.exit(1)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
