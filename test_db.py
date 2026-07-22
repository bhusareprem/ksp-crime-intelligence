#!/usr/bin/env python3
"""Quick health check for ksp_crime.db (SQLite) and criminal.db (DuckDB)."""

import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).parent


def test_ksp_crime(db_path: Path) -> bool:
    print("=" * 60)
    print("KSP_CRIME.DB (SQLite)")
    print("=" * 60)
    if not db_path.exists():
        print(f"  FAIL: not found at {db_path}")
        return False

    print(f"  Size: {db_path.stat().st_size / 1e6:.1f} MB")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"  Tables: {len(tables)}")
    for (name,) in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"    {name}: {count:,}")

    thefts = cur.execute("""
        SELECT COUNT(*) FROM fir_records f
        JOIN police_stations ps ON f.station_id = ps.station_id
        JOIN districts d ON ps.district_id = d.district_id
        JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
        WHERE d.name LIKE '%Bengaluru%' AND ch.name LIKE '%Theft%' AND f.year = 2024
    """).fetchone()[0]

    cyber = cur.execute("""
        SELECT total_cases FROM ncrb_city_stats
        WHERE city='Bengaluru' AND state='Karnataka' AND year=2024 AND stat_type='cyber'
    """).fetchone()

    conn.close()
    print(f"\n  Query test — Bengaluru thefts 2024: {thefts}")
    print(f"  Query test — NCRB Bengaluru cyber 2024: {cyber[0] if cyber else 'N/A'}")
    print("  Status: OK\n")
    return True


def test_criminal(db_path: Path) -> bool:
    print("=" * 60)
    print("CRIMINAL.DB (DuckDB)")
    print("=" * 60)
    if not db_path.exists():
        print(f"  FAIL: not found at {db_path}")
        return False

    try:
        import duckdb
    except ImportError:
        print("  FAIL: duckdb not installed (pip install duckdb)")
        return False

    print(f"  Size: {db_path.stat().st_size / 1e6:.1f} MB")
    con = duckdb.connect(str(db_path), read_only=True)

    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    print(f"  Tables: {len(tables)}")
    for (name,) in tables:
        count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        print(f"    {name}: {count:,}")

    firs = con.execute("SELECT COUNT(*) FROM fir_details").fetchone()[0]
    profiles = con.execute("SELECT COUNT(*) FROM criminal_profiles").fetchone()[0]
    links = con.execute("SELECT COUNT(*) FROM co_accused_links").fetchone()[0]
    top = con.execute("""
        SELECT district_name, primary_crime_head, total_firs, risk_level
        FROM criminal_profiles ORDER BY repeat_offender_score DESC LIMIT 1
    """).fetchone()

    con.close()
    print(f"\n  Query test — total FIRs: {firs:,}")
    print(f"  Query test — criminal profiles: {profiles:,}")
    print(f"  Query test — co-accused links: {links:,}")
    print(f"  Query test — top profile: {top}")
    print("  Status: OK\n")
    return True


def test_cases(db_path: Path) -> bool:
    print("=" * 60)
    print("CASES.DB (DuckDB) — Karnataka Criminal Judicial Cases")
    print("=" * 60)
    if not db_path.exists():
        print(f"  FAIL: not found at {db_path}")
        return False

    try:
        import duckdb
    except ImportError:
        print("  FAIL: duckdb not installed (pip install duckdb)")
        return False

    print(f"  Size: {db_path.stat().st_size / 1e6:.1f} MB")
    con = duckdb.connect(str(db_path), read_only=True)

    cases = con.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    years = con.execute("SELECT MIN(year), MAX(year) FROM cases").fetchone()
    top = con.execute("""
        SELECT district_name, COUNT(*) AS cnt FROM cases
        GROUP BY district_name ORDER BY cnt DESC LIMIT 3
    """).fetchall()

    con.close()
    print(f"  Query test — criminal cases: {cases:,}")
    print(f"  Query test — years: {years[0]}-{years[1]}")
    print(f"  Query test — top districts: {top}")
    print("  Status: OK\n")
    return True


def main():
    ksp = PROJECT / "data" / "ksp_crime.db"
    criminal = PROJECT / "data" / "criminal.db"
    cases = PROJECT / "data" / "cases.db"

    ok1 = test_ksp_crime(ksp)
    ok2 = test_criminal(criminal)
    ok3 = test_cases(cases)

    if ok1 and ok2 and ok3:
        print("All databases passed.")
        sys.exit(0)
    print("One or more databases failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
