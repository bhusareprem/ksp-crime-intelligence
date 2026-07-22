#!/usr/bin/env python3
"""Stage a lean AppSail deployment bundle in dist_appsail/.

Copies only what the app needs at runtime (code + frontend + compacted DBs),
leaving behind the 16 GB of raw source CSVs, archives, and build scripts.

Usage:  python scripts/build_appsail.py
Then:   cd dist_appsail && catalyst deploy   (after `catalyst init` once)
"""

import os
import shutil
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist_appsail"

# Code shipped as-is
CODE = ["api", "src", "frontend", "run_web.py"]

# Small DBs shipped as-is (path → path inside dist/data)
DATA_FILES = [
    ("data/unified/ksp_crime.db", "data/unified/ksp_crime.db"),
    ("data/unified/criminal.db", "data/unified/criminal.db"),
    ("data/unified/cases.db", "data/unified/cases.db"),
    ("data/unified/registry.json", "data/unified/registry.json"),
    ("data/case_knowledge.db", "data/case_knowledge.db"),
]

# Runtime-only deps (build/generation tools like faker/openpyxl stay out)
REQUIREMENTS = """\
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.0.0
python-multipart>=0.0.9
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
duckdb>=1.0.0
duckdb-engine>=0.13.0
sqlalchemy>=2.0.0
requests>=2.31.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-community>=0.3.0
langchain-openai>=0.2.0
langchain-mistralai>=0.2.0
google-genai>=2.0.0
ddgs>=9.0.0
duckduckgo-search>=6.0.0
pypdf>=4.0.0
python-docx>=1.1.0
"""


def compact_fir(src: Path, dst: Path):
    """Copy ksp_fir.duckdb table-by-table into a fresh file (~10% of original size)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    con = duckdb.connect(str(dst))
    con.execute(f"ATTACH '{src.as_posix()}' AS src (READ_ONLY)")
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = 'src' AND table_type = 'BASE TABLE' ORDER BY 1"
    ).fetchall()]
    for t in tables:
        con.execute(f'CREATE TABLE "{t}" AS SELECT * FROM src."{t}"')
    con.execute("CHECKPOINT")
    rows = con.execute('SELECT COUNT(*) FROM "CaseMaster"').fetchone()[0]
    con.close()
    print(f"  compacted {len(tables)} tables, CaseMaster rows: {rows:,}")


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    print("Copying code...")
    for item in CODE:
        src = ROOT / item
        dst = DIST / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)

    print("Copying small databases...")
    for rel_src, rel_dst in DATA_FILES:
        src = ROOT / rel_src
        if not src.exists():
            print(f"  WARN missing: {rel_src}")
            continue
        dst = DIST / rel_dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    print("Compacting ksp_fir.duckdb (500k FIRs)...")
    compact_fir(ROOT / "data" / "ksp_fir.duckdb", DIST / "data" / "ksp_fir.duckdb")

    (DIST / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"\nBundle ready: {DIST}")
    print(f"Total size: {total / 1e6:.1f} MB")
    print("\nNext:")
    print("  cd dist_appsail")
    print("  catalyst init   (first time: choose AppSail -> Python, point at this dir)")
    print("  catalyst deploy")


if __name__ == "__main__":
    sys.exit(main())
