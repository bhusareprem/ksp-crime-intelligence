#!/usr/bin/env python3
"""
KSP Crime Database Builder — Phase 1
Parse NCRB XLSX → generate synthetic Karnataka FIR data → load SQLite

Usage:
    python build_db.py
    python build_db.py --firs 8000 --stations 1200
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse_ncrb import parse_all_ncrb
from src.generate_synthetic import generate_all
from src.load_db import init_schema, load_dataframes, verify_database


def main():
    parser = argparse.ArgumentParser(description="Build KSP Crime Database")
    parser.add_argument("--firs", type=int, default=5500, help="Number of synthetic FIR records")
    parser.add_argument("--stations", type=int, default=1150, help="Number of police stations")
    parser.add_argument("--criminals", type=int, default=1200, help="Number of criminal profiles")
    parser.add_argument("--data-dir", type=str, default=str(PROJECT_ROOT), help="Directory with XLSX files")
    parser.add_argument("--db", type=str, default=str(PROJECT_ROOT / "data" / "ksp_crime.db"), help="SQLite DB path")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    db_path = Path(args.db)
    schema_path = PROJECT_ROOT / "schema.sql"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("KSP Crime Database Builder — Phase 1")
    print("=" * 60)

    # Step 1: Parse NCRB XLSX files
    print("\n[1/4] Parsing NCRB XLSX files...")
    ncrb_data = parse_all_ncrb(data_dir)
    for name, df in ncrb_data.items():
        out = processed_dir / f"{name}.csv"
        df.to_csv(out, index=False)
        print(f"  Saved {out.name}")

    # Step 2: Generate synthetic Karnataka data
    print("\n[2/4] Generating synthetic Karnataka crime data...")
    synthetic = generate_all(
        n_firs=args.firs,
        n_stations=args.stations,
        n_criminals=args.criminals,
    )
    for name, df in synthetic.items():
        out = processed_dir / f"{name}.csv"
        df.to_csv(out, index=False)

    # Step 3: Load into SQLite
    print(f"\n[3/4] Loading into SQLite: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    init_schema(db_path, schema_path)

    all_tables = {**synthetic}
    ncrb_tables = [
        "ncrb_crime_stats",
        "ncrb_city_stats",
        "ncrb_complaint_stats",
        "ncrb_national_stats",
        "ncrb_economic_headwise",
    ]
    for table in ncrb_tables:
        if table in ncrb_data:
            all_tables[table] = ncrb_data[table]

    load_dataframes(db_path, all_tables)

    # Step 4: Verify
    print("\n[4/4] Verifying database...")
    stats = verify_database(db_path)
    print("\n" + "=" * 60)
    print("DATABASE SUMMARY")
    print("=" * 60)
    for key, val in stats.items():
        if key == "top_crimes_2024_detail":
            print("\n  Top 5 crimes in 2024:")
            for crime, cnt in val:
                print(f"    {crime}: {cnt}")
        elif key != "top_crimes_2024":
            print(f"  {key}: {val}")

    print(f"\nDatabase ready at: {db_path}")
    print("Sample query:")
    print('  sqlite3 data/ksp_crime.db "SELECT COUNT(*) FROM fir_records WHERE year=2024"')


if __name__ == "__main__":
    main()
