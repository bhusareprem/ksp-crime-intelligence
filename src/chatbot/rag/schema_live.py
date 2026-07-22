"""Live schema introspection from SQLite / DuckDB files."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

import duckdb

# Tables the LLM should use most often (full list appended from DB)
KSP_CORE_TABLES = (
    "districts", "police_stations", "crime_heads", "fir_records",
    "criminals", "fir_criminal_link", "ncrb_city_stats", "ncrb_national_stats",
    "ncrb_crime_stats", "ncrb_complaint_stats", "ncrb_economic_headwise",
)

CRIMINAL_CORE_TABLES = (
    "districts", "crime_heads", "fir_details", "criminal_profiles",
    "accused_persons", "co_accused_links", "criminal_signatures",
)

CASES_CORE_TABLES = ("cases",)

VALUE_HINTS = {
    "ksp_crime": """
Data coverage: demo FIRs 2022–2024; NCRB tables 2022–2024.
District names (districts.name): title case — 'Bengaluru Urban', 'Bagalkot', 'Gadag', 'Mysuru'.
  → User says Bangalore/Bengaluru: use WHERE d.name LIKE '%Bengaluru%'
Engine: SQLite — use LIKE (not ILIKE).
Join keys: fir_records.station_id→police_stations; crime_head_id→crime_heads.crime_head_id;
  criminals.district_id→districts.district_id.
Person NAMES only in criminals table (synthetic demo data).
""",
    "criminal": """
Data coverage: real Karnataka FIRs 2016–2024 (1.67M rows).
District names (districts.name): title case — 'Bagalkot', 'Bengaluru', 'Gadag'.
  → Use d.name ILIKE '%Bagalkot%' (case-insensitive).
Engine: DuckDB — use ILIKE.
Join keys: fir_details.district_id→districts; crime_head_id→crime_heads.head_id (NOT ipc_section).
NO person names — use criminal_profiles for repeat-offender area profiles.
Tables: fir_details (main), criminal_profiles (aggregated profiles), accused_persons (no name column).
""",
    "cases": """
Data coverage: e-Courts criminal cases 2010–2018 only.
District names (cases.district_name): UPPERCASE — 'BAGALKOT', 'BENGALURU', 'GADAG'.
  → Use district_name ILIKE '%BAGALKOT%'
Engine: DuckDB — use ILIKE.
Key columns: type_name_s (case type), disp_name_s (disposition), year, case_duration_days.
For convictions: disp_name_s ILIKE '%convict%'. For acquittals: ILIKE '%acquit%'.
""",
}


@lru_cache(maxsize=3)
def _cached_schema(db_path: str, db_name: str) -> str:
    path = Path(db_path)
    if not path.exists():
        return f"(database file not found: {path})"

    if db_name == "ksp_crime":
        return _sqlite_schema(path, KSP_CORE_TABLES)
    return _duckdb_schema(path, _core_tables(db_name))


def _core_tables(db_name: str) -> tuple[str, ...]:
    if db_name == "cases":
        return CASES_CORE_TABLES
    return CRIMINAL_CORE_TABLES


def _sqlite_schema(path: Path, prefer_tables: tuple[str, ...]) -> str:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        all_tables = [r[0] for r in rows if not r[0].startswith("sqlite_")]
        ordered = [t for t in prefer_tables if t in all_tables]
        ordered += [t for t in all_tables if t not in ordered]

        parts = []
        for table in ordered[:14]:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_str = ", ".join(f"{c[1]} ({c[2]})" for c in cols)
            parts.append(f"  {table}: {col_str}")
        return "Live schema (SQLite):\n" + "\n".join(parts)
    finally:
        conn.close()


def _duckdb_schema(path: Path, prefer_tables: tuple[str, ...]) -> str:
    conn = duckdb.connect(str(path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
        all_tables = [r[0] for r in rows]
        ordered = [t for t in prefer_tables if t in all_tables]
        ordered += [t for t in all_tables if t not in ordered]

        parts = []
        for table in ordered[:14]:
            cols = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            col_str = ", ".join(f"{c[0]} ({c[1]})" for c in cols)
            parts.append(f"  {table}: {col_str}")
        return "Live schema (DuckDB):\n" + "\n".join(parts)
    finally:
        conn.close()


def get_live_schema(db_path: Path, db_name: str) -> str:
    return _cached_schema(str(db_path.resolve()), db_name)


def get_value_hints(db_name: str) -> str:
    return VALUE_HINTS.get(db_name, "").strip()
