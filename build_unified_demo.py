#!/usr/bin/env python3
"""
Build unified aligned demo databases for KSP Crime Intelligence.

Generates ksp_crime.db, criminal.db, and cases.db with:
  - Shared district IDs and FIR IDs (2018-2024)
  - Named persons, co-accused networks, behavioral profiles
  - Court cases linked to FIRs via linked_fir_id
  - NCRB stats derived from the same FIR universe

Usage:
    python build_unified_demo.py
    python build_unified_demo.py --install          # copy to data/ (backs up originals)
    python build_unified_demo.py --firs 50000
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))

from src.unified_demo import write_all_databases
from src.unified_demo.generator import UnifiedConfig, generate_unified_master


def main():
    parser = argparse.ArgumentParser(description="Build unified aligned KSP demo databases")
    parser.add_argument("--firs", type=int, default=35_000, help="Number of FIR records")
    parser.add_argument("--persons", type=int, default=3_000, help="Named persons in network")
    parser.add_argument("--output", type=str, default=str(PROJECT / "data" / "unified"))
    parser.add_argument(
        "--install",
        action="store_true",
        help="Copy built DBs to data/ (backs up existing files to data/archive/)",
    )
    args = parser.parse_args()

    cfg = UnifiedConfig(n_firs=args.firs, n_persons=args.persons)
    output_dir = Path(args.output)

    print("=" * 60)
    print("KSP Unified Demo Database Builder")
    print("=" * 60)
    print(f"  FIRs:    {cfg.n_firs:,}")
    print(f"  Persons: {cfg.n_persons:,}")
    print(f"  Years:   {cfg.year_start}-{cfg.year_end}")
    print(f"  Output:  {output_dir}")
    print()

    print("[1/3] Generating aligned master data...")
    master = generate_unified_master(cfg)
    print(f"  FIRs: {len(master.firs):,} | Persons: {len(master.persons):,}")
    print(f"  Court cases: {len(master.court_cases):,} | Co-accused links: {len(master.co_accused):,}")
    print(f"  Profiles: {len(master.profiles):,}")

    print("\n[2/3] Writing databases...")
    paths = write_all_databases(master, output_dir, PROJECT)
    for name, p in paths.items():
        mb = p.stat().st_size / 1e6
        print(f"  {name}: {p} ({mb:.1f} MB)")

    print(f"\n  Registry: {output_dir / 'registry.json'}")

    if args.install:
        print("\n[3/3] Installing to data/ (with backup)...")
        data_dir = PROJECT / "data"
        archive = data_dir / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
        archive.mkdir(parents=True, exist_ok=True)
        for key, src in paths.items():
            dest = data_dir / f"{key}.db"
            if dest.exists():
                shutil.copy2(dest, archive / dest.name)
                print(f"  Backed up {dest.name} -> {archive}")
            shutil.copy2(src, dest)
            print(f"  Installed {dest.name}")
        shutil.copy2(output_dir / "registry.json", data_dir / "unified_registry.json")
        print("\n  Chatbot will auto-detect unified DBs in data/ when registry present.")
    else:
        print("\n[3/3] To use in chatbot, run with --install or set:")
        print(f"  KSP_DATA_DIR={output_dir}")

    print("\n" + "=" * 60)
    print("Unified demo databases ready.")
    print("=" * 60)
    print("\nAlignment checks:")
    print("  python test_unified_demo.py")


if __name__ == "__main__":
    main()
