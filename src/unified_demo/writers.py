"""Write unified master data to ksp_crime.db, criminal.db, cases.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb
import pandas as pd

from src.unified_demo.generator import UnifiedMaster


def _duck_insert(conn: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    conn.register("_tmp_df", df)
    cols = ", ".join(df.columns)
    conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _tmp_df")
    conn.unregister("_tmp_df")


def _write_sqlite_ksp(master: UnifiedMaster, db_path: Path, schema_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    d = master.districts[
        ["district_id", "name", "name_kn", "latitude", "longitude", "population", "zone"]
    ]
    d.to_sql("districts", conn, if_exists="append", index=False)

    master.police_stations[
        ["station_id", "name", "district_id", "latitude", "longitude", "station_code"]
    ].to_sql("police_stations", conn, if_exists="append", index=False)

    master.crime_heads[
        ["crime_head_id", "name", "category", "ipc_section", "severity"]
    ].to_sql("crime_heads", conn, if_exists="append", index=False)

    fir = master.firs.rename(columns={"year": "year"})
    fir_ksp = fir[[
        "fir_id", "fir_number", "station_id", "crime_head_id", "date_registered",
        "year", "month", "accused_count",
        "latitude", "longitude", "is_cyber", "is_economic", "chargesheet_filed",
    ]].copy()
    fir_ksp["status"] = fir["status"]
    fir_ksp["description"] = fir["place_of_offence"]
    fir_ksp["victim_age"] = None
    fir_ksp["victim_gender"] = None
    fir_ksp.to_sql("fir_records", conn, if_exists="append", index=False)

    master.ksp_criminals[
        ["criminal_id", "name", "alias", "age", "gender", "district_id", "status"]
    ].to_sql("criminals", conn, if_exists="append", index=False)

    if not master.fir_criminal_link.empty:
        master.fir_criminal_link[["link_id", "fir_id", "criminal_id", "role"]].to_sql(
            "fir_criminal_link", conn, if_exists="append", index=False
        )

    ncrb = master.ncrb_city.copy()
    ncrb["stat_id"] = range(1, len(ncrb) + 1)
    ncrb.to_sql("ncrb_city_stats", conn, if_exists="append", index=False)

    nat = master.ncrb_national.copy()
    nat["stat_id"] = range(1, len(nat) + 1)
    nat.to_sql("ncrb_national_stats", conn, if_exists="append", index=False)

    pd.DataFrame([{
        "stat_id": 1,
        "complaint_type": "General Crime",
        "num_complaints": len(master.firs),
        "num_firs": len(master.firs),
        "num_online_efir": int(len(master.firs) * 0.12),
        "year": master.config.year_end,
    }]).to_sql("ncrb_complaint_stats", conn, if_exists="append", index=False)

    conn.commit()
    conn.close()


def _apply_duckdb_schema(conn: duckdb.DuckDBPyConnection, schema_path: Path) -> None:
    conn.execute(schema_path.read_text(encoding="utf-8"))


def _write_duckdb_criminal_v2(master: UnifiedMaster, db_path: Path, schema_path: Path) -> None:
    """Write criminal.db with person_id on accused via join table."""
    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    _apply_duckdb_schema(conn, schema_path)

    _duck_insert(conn, "districts", master.districts[["district_id", "name"]])
    _duck_insert(conn, "police_units", master.police_units)
    _duck_insert(conn, "crime_groups", master.crime_groups)
    _duck_insert(conn, "crime_heads", master.crime_heads[["head_id", "name", "group_id"]])

    _duck_insert(conn, "persons", master.persons[[
        "person_id", "name", "alias", "age", "gender", "caste_category",
        "education", "occupation", "district_id", "district_name", "status",
        "repeat_offender_score", "risk_level",
    ]])

    fir_c = master.firs[[
        "fir_id", "district_id", "unit_id", "crime_group_id", "crime_head_id",
        "fir_year", "fir_month", "fir_day", "fir_stage", "complaint_mode",
        "latitude", "longitude", "place_of_offence", "village_area_name",
        "male_victims", "female_victims", "victim_count", "accused_count",
        "arrested_male", "arrested_female", "arrested_count",
        "chargesheeted_count", "conviction_count",
    ]].copy()
    fir_c["fir_type"] = "Regular"
    fir_c["offence_duration"] = 30
    fir_c["distance_from_ps"] = "0-5 km"
    fir_c["beat_name"] = fir_c["village_area_name"]
    fir_c["io_id"] = None
    _duck_insert(conn, "fir_details", fir_c)

    _duck_insert(conn, "accused_persons", master.accused[[
        "accused_id", "fir_id", "person_id", "accused_seq", "signature_id",
        "was_arrested", "was_chargesheeted", "was_convicted",
    ]])
    _duck_insert(conn, "co_accused_links", master.co_accused)
    _duck_insert(conn, "criminal_signatures", master.signatures[[
        "signature_id", "district_id", "village_area_name", "crime_head_id",
        "fir_count", "total_accused", "total_convictions", "first_year",
        "last_year", "repeat_offender_score",
    ]])
    _duck_insert(conn, "criminal_profiles", master.profiles[[
        "profile_id", "signature_id", "district_name", "village_area_name",
        "primary_crime_head", "primary_crime_group", "total_firs", "total_accused",
        "avg_accused_per_fir", "arrest_rate", "conviction_rate", "chargesheet_rate",
        "heinous_ratio", "peak_month", "active_span_years", "repeat_offender_score",
        "risk_level", "behavioral_tags",
    ]])
    if not master.behavior.empty:
        _duck_insert(conn, "behavior_features", master.behavior)

    conn.execute("""
        CREATE OR REPLACE VIEW accused_with_names AS
        SELECT a.accused_id, a.fir_id, a.person_id, p.name AS accused_name,
               p.age, p.gender, p.caste_category, p.education, p.occupation,
               p.district_name, p.risk_level, a.was_arrested, a.was_convicted
        FROM accused_persons a
        JOIN persons p ON a.person_id = p.person_id
    """)
    conn.close()


def _write_duckdb_cases(master: UnifiedMaster, db_path: Path, schema_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    _apply_duckdb_schema(conn, schema_path)

    _duck_insert(conn, "cases", master.court_cases)
    _duck_insert(conn, "fir_case_link", master.fir_case_link)

    conn.execute("""
        CREATE OR REPLACE VIEW cases_with_fir AS
        SELECT c.*, l.fir_id AS linked_fir_id
        FROM cases c
        LEFT JOIN fir_case_link l ON c.ddl_case_id = l.ddl_case_id
    """)
    conn.close()


__all__ = ["_write_sqlite_ksp", "_write_duckdb_criminal_v2", "_write_duckdb_cases"]
