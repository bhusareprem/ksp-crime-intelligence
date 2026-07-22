"""Build criminal.db (DuckDB) from FIR Details CSV — fast vectorized pipeline."""

from pathlib import Path

import duckdb


FIR_CSV = "FIR_Details_Data.csv"

COLUMN_RENAME = """
    District_Name AS district_name,
    UnitName AS unit_name,
    FIR_YEAR AS fir_year,
    FIR_MONTH AS fir_month,
    Offence_Duration AS offence_duration,
    FIR_Day AS fir_day,
    "FIR Type" AS fir_type,
    FIR_Stage AS fir_stage,
    Complaint_Mode AS complaint_mode,
    CrimeGroup_Name AS crime_group_name,
    CrimeHead_Name AS crime_head_name,
    Latitude AS latitude,
    Longitude AS longitude,
    ActSection AS act_section,
    IOName AS io_name,
    CAST(KGID AS VARCHAR) AS kgid,
    Internal_IO AS internal_io,
    "Place of Offence" AS place_of_offence,
    "Distance from PS" AS distance_from_ps,
    Beat_Name AS beat_name,
    Village_Area_Name AS village_area_name,
    Male AS male_victims,
    Female AS female_victims,
    Boy AS boy_victims,
    Girl AS girl_victims,
    "Age 0" AS age_0_victims,
    "VICTIM COUNT" AS victim_count,
    "Accused Count" AS accused_count,
    "Arrested Male" AS arrested_male,
    "Arrested Female" AS arrested_female,
    "Arrested Count\tNo." AS arrested_count,
    "Accused_ChargeSheeted Count" AS chargesheeted_count,
    "Conviction Count" AS conviction_count,
    Unit_ID AS unit_id
"""


def build_criminal_db(csv_path: Path, db_path: Path) -> dict:
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    csv_sql = str(csv_path).replace("\\", "/")

    print("  Step 1/8: Loading FIR CSV into staging table...")
    con.execute(f"""
        CREATE TABLE fir_staging AS
        SELECT {COLUMN_RENAME}
        FROM read_csv('{csv_sql}', header=true, ignore_errors=true)
    """)
    fir_count = con.execute("SELECT COUNT(*) FROM fir_staging").fetchone()[0]
    print(f"    Loaded {fir_count:,} FIR rows")

    print("  Step 2/8: Building dimension tables...")
    con.execute("""
        CREATE TABLE districts AS
        SELECT ROW_NUMBER() OVER (ORDER BY district_name) AS district_id,
               district_name AS name
        FROM (SELECT DISTINCT district_name FROM fir_staging WHERE district_name IS NOT NULL)
    """)
    con.execute("""
        CREATE TABLE crime_groups AS
        SELECT ROW_NUMBER() OVER (ORDER BY crime_group_name) AS group_id,
               crime_group_name AS name
        FROM (SELECT DISTINCT crime_group_name FROM fir_staging WHERE crime_group_name IS NOT NULL)
    """)
    con.execute("""
        CREATE TABLE crime_heads AS
        SELECT ROW_NUMBER() OVER (ORDER BY s.crime_head_name) AS head_id,
               s.crime_head_name AS name,
               cg.group_id
        FROM (
            SELECT DISTINCT crime_head_name, crime_group_name
            FROM fir_staging
            WHERE crime_head_name IS NOT NULL
        ) s
        LEFT JOIN crime_groups cg ON cg.name = s.crime_group_name
    """)
    con.execute("""
        CREATE TABLE police_units AS
        SELECT DISTINCT
            CAST(s.unit_id AS INTEGER) AS unit_id,
            s.unit_name AS name,
            d.district_id
        FROM fir_staging s
        JOIN districts d ON d.name = s.district_name
        WHERE s.unit_id IS NOT NULL
    """)
    con.execute("""
        CREATE TABLE investigating_officers AS
        SELECT ROW_NUMBER() OVER (ORDER BY kgid) AS io_id,
               kgid,
               FIRST(io_name) AS name
        FROM fir_staging
        WHERE kgid IS NOT NULL AND kgid != 'nan'
        GROUP BY kgid
    """)

    print("  Step 3/8: Building fir_details...")
    con.execute("""
        CREATE TABLE fir_details AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY s.fir_year, s.fir_month, s.fir_day, s.unit_id, s.kgid) AS fir_id,
            d.district_id,
            CAST(s.unit_id AS INTEGER) AS unit_id,
            cg.group_id AS crime_group_id,
            ch.head_id AS crime_head_id,
            io.io_id,
            CAST(s.fir_year AS INTEGER) AS fir_year,
            CAST(s.fir_month AS INTEGER) AS fir_month,
            CAST(s.fir_day AS INTEGER) AS fir_day,
            CAST(COALESCE(s.offence_duration, 0) AS INTEGER) AS offence_duration,
            s.fir_type,
            s.fir_stage,
            s.complaint_mode,
            TRY_CAST(s.latitude AS DOUBLE) AS latitude,
            TRY_CAST(s.longitude AS DOUBLE) AS longitude,
            s.act_section,
            s.place_of_offence,
            s.distance_from_ps,
            s.beat_name,
            s.village_area_name,
            CAST(COALESCE(s.male_victims, 0) AS INTEGER) AS male_victims,
            CAST(COALESCE(s.female_victims, 0) AS INTEGER) AS female_victims,
            CAST(COALESCE(s.boy_victims, 0) AS INTEGER) AS boy_victims,
            CAST(COALESCE(s.girl_victims, 0) AS INTEGER) AS girl_victims,
            CAST(COALESCE(s.age_0_victims, 0) AS INTEGER) AS age_0_victims,
            CAST(COALESCE(s.victim_count, 0) AS INTEGER) AS victim_count,
            CAST(GREATEST(COALESCE(s.accused_count, 0), 0) AS INTEGER) AS accused_count,
            CAST(COALESCE(s.arrested_male, 0) AS INTEGER) AS arrested_male,
            CAST(COALESCE(s.arrested_female, 0) AS INTEGER) AS arrested_female,
            CAST(GREATEST(COALESCE(s.arrested_count, 0), 0) AS INTEGER) AS arrested_count,
            CAST(GREATEST(COALESCE(s.chargesheeted_count, 0), 0) AS INTEGER) AS chargesheeted_count,
            CAST(GREATEST(COALESCE(s.conviction_count, 0), 0) AS INTEGER) AS conviction_count
        FROM fir_staging s
        JOIN districts d ON d.name = s.district_name
        LEFT JOIN crime_groups cg ON cg.name = s.crime_group_name
        LEFT JOIN crime_heads ch
          ON ch.name = s.crime_head_name
         AND ch.group_id = cg.group_id
        LEFT JOIN investigating_officers io ON io.kgid = CAST(s.kgid AS VARCHAR)
    """)
    con.execute("DROP TABLE fir_staging")

    print("  Step 4/8: Expanding accused persons (vectorized)...")
    con.execute("""
        CREATE TABLE accused_persons AS
        WITH expanded AS (
            SELECT
                f.fir_id,
                unnest(range(1, f.accused_count + 1)) AS accused_seq,
                f.arrested_count,
                f.chargesheeted_count,
                f.conviction_count
            FROM fir_details f
            WHERE f.accused_count > 0
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY fir_id, accused_seq) AS accused_id,
            fir_id,
            accused_seq,
            CAST(NULL AS INTEGER) AS signature_id,
            CASE WHEN accused_seq <= arrested_count THEN 1 ELSE 0 END AS was_arrested,
            CASE WHEN accused_seq <= chargesheeted_count THEN 1 ELSE 0 END AS was_chargesheeted,
            CASE WHEN accused_seq <= conviction_count THEN 1 ELSE 0 END AS was_convicted
        FROM expanded
    """)

    print("  Step 5/8: Building co-accused network links...")
    con.execute("""
        CREATE TABLE co_accused_links AS
        SELECT
            ROW_NUMBER() OVER () AS link_id,
            a1.fir_id,
            a1.accused_id AS accused_id_a,
            a2.accused_id AS accused_id_b,
            1.0 AS link_weight
        FROM accused_persons a1
        JOIN accused_persons a2
          ON a1.fir_id = a2.fir_id
         AND a1.accused_seq < a2.accused_seq
    """)

    print("  Step 6/8: Building criminal signatures + profiles...")
    con.execute("""
        CREATE TABLE criminal_signatures AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS signature_id,
            f.district_id,
            f.village_area_name,
            f.crime_head_id,
            COUNT(*) AS fir_count,
            SUM(f.accused_count) AS total_accused,
            SUM(f.conviction_count) AS total_convictions,
            MIN(f.fir_year) AS first_year,
            MAX(f.fir_year) AS last_year,
            LEAST(100.0, ROUND(
                COUNT(*) * 2.0
                + SUM(f.accused_count) * 0.1
                + (MAX(f.fir_year) - MIN(f.fir_year) + 1) * 3.0
                + SUM(CASE WHEN f.fir_type ILIKE '%Heinous%' THEN 2 ELSE 0 END)
            , 2)) AS repeat_offender_score
        FROM fir_details f
        WHERE f.accused_count > 0
          AND f.village_area_name IS NOT NULL
          AND f.crime_head_id IS NOT NULL
        GROUP BY f.district_id, f.village_area_name, f.crime_head_id
        HAVING COUNT(*) >= 3
    """)
    con.execute("""
        UPDATE accused_persons a
        SET signature_id = cs.signature_id
        FROM fir_details f
        JOIN criminal_signatures cs
          ON cs.district_id = f.district_id
         AND cs.village_area_name = f.village_area_name
         AND cs.crime_head_id = f.crime_head_id
        WHERE a.fir_id = f.fir_id
    """)

    print("  Step 7/8: Building behavior features...")
    con.execute("""
        CREATE TABLE behavior_features AS
        SELECT
            f.fir_id,
            EXTRACT(DOW FROM MAKE_DATE(f.fir_year, f.fir_month, LEAST(f.fir_day, 28))) AS day_of_week,
            CASE WHEN EXTRACT(DOW FROM MAKE_DATE(f.fir_year, f.fir_month, LEAST(f.fir_day, 28))) IN (0, 6)
                 THEN 1 ELSE 0 END AS is_weekend,
            CASE WHEN f.fir_type ILIKE '%Heinous%' THEN 1 ELSE 0 END AS is_heinous,
            CASE WHEN f.latitude IS NOT NULL AND f.longitude IS NOT NULL THEN 1 ELSE 0 END AS has_geo,
            (f.male_victims + f.female_victims + f.boy_victims + f.girl_victims + f.age_0_victims) AS victim_total,
            CASE WHEN (f.boy_victims + f.girl_victims + f.age_0_victims) > 0 THEN 1 ELSE 0 END AS child_victim,
            CASE WHEN f.female_victims > 0 OR f.girl_victims > 0 THEN 1 ELSE 0 END AS female_victim,
            f.accused_count,
            CASE WHEN f.accused_count > 0 THEN ROUND(f.arrested_count * 1.0 / f.accused_count, 3) ELSE 0 END AS arrest_rate,
            CASE WHEN f.accused_count > 0 THEN ROUND(f.conviction_count * 1.0 / f.accused_count, 3) ELSE 0 END AS conviction_rate,
            CASE WHEN f.accused_count > 0 THEN ROUND(f.chargesheeted_count * 1.0 / f.accused_count, 3) ELSE 0 END AS chargesheet_rate,
            f.offence_duration AS offence_duration_days,
            0 AS complaint_mode_code,
            ROUND(
                (CASE WHEN f.fir_type ILIKE '%Heinous%' THEN 40 ELSE 10 END)
                + LEAST(f.accused_count, 10) * 3
                + (CASE WHEN (f.boy_victims + f.girl_victims) > 0 THEN 15 ELSE 0 END)
                + (CASE WHEN f.conviction_count > 0 THEN 10 ELSE 0 END)
            , 2) AS crime_severity_score,
            ROUND(
                (CASE WHEN f.fir_month IN (10, 11, 12, 1) THEN 15 ELSE 5 END)
                + (CASE WHEN f.offence_duration <= 1 THEN 10 WHEN f.offence_duration <= 7 THEN 5 ELSE 0 END)
            , 2) AS temporal_risk_score
        FROM fir_details f
        WHERE f.fir_year BETWEEN 1900 AND 2100
          AND f.fir_month BETWEEN 1 AND 12
    """)

    con.execute("""
        CREATE TABLE criminal_profiles AS
        WITH agg AS (
            SELECT
                cs.signature_id,
                d.name AS district_name,
                cs.village_area_name,
                ch.name AS primary_crime_head,
                cg.name AS primary_crime_group,
                cs.fir_count AS total_firs,
                cs.total_accused,
                ROUND(cs.total_accused * 1.0 / cs.fir_count, 2) AS avg_accused_per_fir,
                ROUND(AVG(CASE WHEN f.accused_count > 0 THEN f.arrested_count * 1.0 / f.accused_count ELSE 0 END), 3) AS arrest_rate,
                ROUND(AVG(CASE WHEN f.accused_count > 0 THEN f.conviction_count * 1.0 / f.accused_count ELSE 0 END), 3) AS conviction_rate,
                ROUND(AVG(CASE WHEN f.accused_count > 0 THEN f.chargesheeted_count * 1.0 / f.accused_count ELSE 0 END), 3) AS chargesheet_rate,
                ROUND(AVG(CASE WHEN f.fir_type ILIKE '%Heinous%' THEN 1.0 ELSE 0 END), 3) AS heinous_ratio,
                (cs.last_year - cs.first_year + 1) AS active_span_years,
                cs.repeat_offender_score
            FROM criminal_signatures cs
            JOIN districts d ON d.district_id = cs.district_id
            JOIN crime_heads ch ON ch.head_id = cs.crime_head_id
            LEFT JOIN crime_groups cg ON cg.group_id = ch.group_id
            JOIN fir_details f
              ON f.district_id = cs.district_id
             AND f.village_area_name = cs.village_area_name
             AND f.crime_head_id = cs.crime_head_id
            GROUP BY cs.signature_id, d.name, cs.village_area_name, ch.name, cg.name,
                     cs.fir_count, cs.total_accused, cs.first_year, cs.last_year, cs.repeat_offender_score
        ),
        peak AS (
            SELECT cs.signature_id, f.fir_month,
                   ROW_NUMBER() OVER (PARTITION BY cs.signature_id ORDER BY COUNT(*) DESC) AS rn
            FROM criminal_signatures cs
            JOIN fir_details f
              ON f.district_id = cs.district_id
             AND f.village_area_name = cs.village_area_name
             AND f.crime_head_id = cs.crime_head_id
            GROUP BY cs.signature_id, f.fir_month
        )
        SELECT
            a.signature_id AS profile_id,
            a.signature_id,
            a.district_name,
            a.village_area_name,
            a.primary_crime_head,
            a.primary_crime_group,
            a.total_firs,
            a.total_accused,
            a.avg_accused_per_fir,
            a.arrest_rate,
            a.conviction_rate,
            a.chargesheet_rate,
            a.heinous_ratio,
            p.fir_month AS peak_month,
            a.active_span_years,
            a.repeat_offender_score,
            CASE
                WHEN a.repeat_offender_score >= 75 THEN 'critical'
                WHEN a.repeat_offender_score >= 50 THEN 'high'
                WHEN a.repeat_offender_score >= 25 THEN 'medium'
                ELSE 'low'
            END AS risk_level,
            CONCAT_WS(',',
                CASE WHEN a.heinous_ratio >= 0.5 THEN 'violent_pattern' END,
                CASE WHEN a.conviction_rate >= 0.4 THEN 'high_conviction' END,
                CASE WHEN a.avg_accused_per_fir >= 3 THEN 'gang_activity' END,
                CASE WHEN a.total_firs >= 20 THEN 'serial_pattern' END,
                CASE WHEN a.arrest_rate < 0.2 THEN 'low_arrest_rate' END,
                CASE WHEN a.active_span_years >= 5 THEN 'long_term_activity' END
            ) AS behavioral_tags
        FROM agg a
        LEFT JOIN peak p ON p.signature_id = a.signature_id AND p.rn = 1
    """)

    print("  Step 8/8: Building signature network links (sampled)...")
    con.execute("""
        CREATE TABLE signature_network_links AS
        WITH ranked_sigs AS (
            SELECT signature_id
            FROM criminal_signatures
            WHERE fir_count BETWEEN 3 AND 50
            ORDER BY repeat_offender_score DESC
            LIMIT 5000
        ),
        sig_accused AS (
            SELECT a.signature_id, a.accused_id,
                   ROW_NUMBER() OVER (PARTITION BY a.signature_id ORDER BY f.fir_year, f.fir_month, a.accused_id) AS rn
            FROM accused_persons a
            JOIN fir_details f ON f.fir_id = a.fir_id
            WHERE a.signature_id IN (SELECT signature_id FROM ranked_sigs)
        ),
        pairs AS (
            SELECT s1.signature_id, s1.accused_id AS accused_id_a, s2.accused_id AS accused_id_b
            FROM sig_accused s1
            JOIN sig_accused s2
              ON s1.signature_id = s2.signature_id
             AND s2.rn = s1.rn + 1
            WHERE s1.rn <= 30
        )
        SELECT ROW_NUMBER() OVER () AS link_id, signature_id, accused_id_a, accused_id_b, 0.5 AS link_weight
        FROM pairs
        LIMIT 50000
    """)

    stats = {}
    for table in [
        "districts", "police_units", "crime_groups", "crime_heads",
        "investigating_officers", "fir_details", "accused_persons",
        "co_accused_links", "criminal_signatures", "criminal_profiles",
        "behavior_features", "signature_network_links",
    ]:
        stats[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    stats["critical_profiles"] = con.execute(
        "SELECT COUNT(*) FROM criminal_profiles WHERE risk_level = 'critical'"
    ).fetchone()[0]

    con.close()
    return stats
