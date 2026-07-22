"""Load parsed NCRB data and synthetic records into SQLite."""

import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


def init_schema(db_path: Path, schema_path: Path):
    """Create tables from schema.sql."""
    conn = sqlite3.connect(db_path)
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()


def load_dataframes(db_path: Path, tables: dict[str, pd.DataFrame], if_exists: str = "replace"):
    """Load dict of DataFrames into SQLite."""
    engine = create_engine(f"sqlite:///{db_path}")
    for table_name, df in tables.items():
        df.to_sql(table_name, engine, if_exists=if_exists, index=False)
        print(f"  Loaded {table_name}: {len(df)} rows")
    engine.dispose()


def verify_database(db_path: Path) -> dict:
    """Run verification queries and return summary stats."""
    engine = create_engine(f"sqlite:///{db_path}")
    queries = {
        "districts": "SELECT COUNT(*) as cnt FROM districts",
        "police_stations": "SELECT COUNT(*) as cnt FROM police_stations",
        "crime_heads": "SELECT COUNT(*) as cnt FROM crime_heads",
        "fir_records": "SELECT COUNT(*) as cnt FROM fir_records",
        "criminals": "SELECT COUNT(*) as cnt FROM criminals",
        "fir_criminal_links": "SELECT COUNT(*) as cnt FROM fir_criminal_link",
        "ncrb_crime_stats": "SELECT COUNT(*) as cnt FROM ncrb_crime_stats",
        "ncrb_city_stats": "SELECT COUNT(*) as cnt FROM ncrb_city_stats",
        "ncrb_complaint_stats": "SELECT COUNT(*) as cnt FROM ncrb_complaint_stats",
        "ncrb_national_stats": "SELECT COUNT(*) as cnt FROM ncrb_national_stats",
        "ncrb_economic_headwise": "SELECT COUNT(*) as cnt FROM ncrb_economic_headwise",
        "thefts_bengaluru_2024": """
            SELECT COUNT(*) as cnt FROM fir_records f
            JOIN police_stations ps ON f.station_id = ps.station_id
            JOIN districts d ON ps.district_id = d.district_id
            JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
            WHERE d.name LIKE '%Bengaluru%'
              AND ch.name LIKE '%Theft%'
              AND f.year = 2024
        """,
        "top_crimes_2024": """
            SELECT ch.name, COUNT(*) as cnt FROM fir_records f
            JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
            WHERE f.year = 2024
            GROUP BY ch.name ORDER BY cnt DESC LIMIT 5
        """,
        "repeat_offenders": """
            SELECT COUNT(*) as cnt FROM (
                SELECT criminal_id FROM fir_criminal_link
                GROUP BY criminal_id HAVING COUNT(*) > 1
            )
        """,
    }
    results = {}
    with engine.connect() as conn:
        for key, sql in queries.items():
            try:
                row = conn.execute(text(sql)).fetchone()
                results[key] = row[0] if row else 0
            except Exception as e:
                results[key] = f"ERROR: {e}"

        # Top crimes as list
        try:
            rows = conn.execute(text(queries["top_crimes_2024"])).fetchall()
            results["top_crimes_2024_detail"] = [(r[0], r[1]) for r in rows]
        except Exception:
            pass

    engine.dispose()
    return results
