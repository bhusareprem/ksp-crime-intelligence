"""Build cases.db — Karnataka criminal judicial cases from DDL dataset (2010-2018)."""

from pathlib import Path

import duckdb

KARNATAKA_STATE_CODE = 3


def build_cases_db(cases_dir: Path, db_path: Path) -> dict:
    if db_path.exists():
        db_path.unlink()

    cases_sql = str(cases_dir).replace("\\", "/")
    con = duckdb.connect(str(db_path))

    print("  Step 1/4: Loading reference keys...")
    con.execute(f"""
        CREATE TABLE states AS
        SELECT * FROM read_csv('{cases_sql}/cases_state_key.csv', header=true)
    """)
    con.execute(f"""
        CREATE TABLE districts AS
        SELECT * FROM read_csv('{cases_sql}/cases_district_key.csv', header=true)
    """)
    con.execute(f"""
        CREATE TABLE district_lookup AS
        SELECT DISTINCT
            CAST(state_code AS INTEGER) AS state_code,
            CAST(dist_code AS INTEGER) AS dist_code,
            state_name,
            district_name
        FROM read_csv('{cases_sql}/cases_district_key.csv', header=true)
        WHERE state_name = 'Karnataka'
    """)
    con.execute(f"""
        CREATE TABLE courts AS
        SELECT * FROM read_csv('{cases_sql}/cases_court_key.csv', header=true)
    """)
    con.execute(f"""
        CREATE TABLE court_lookup AS
        SELECT
            CAST(state_code AS INTEGER) AS state_code,
            CAST(dist_code AS INTEGER) AS dist_code,
            CAST(court_no AS INTEGER) AS court_no,
            FIRST(court_name) AS court_name
        FROM read_csv('{cases_sql}/cases_court_key.csv', header=true)
        WHERE state_name = 'Karnataka'
        GROUP BY 1, 2, 3
    """)
    con.execute(f"""
        CREATE TABLE case_types AS
        SELECT * FROM read_csv('{cases_sql}/type_name_key.csv', header=true)
    """)
    con.execute(f"""
        CREATE TABLE purposes AS
        SELECT * FROM read_csv('{cases_sql}/purpose_name_key.csv', header=true)
    """)
    con.execute(f"""
        CREATE TABLE dispositions AS
        SELECT * FROM read_csv('{cases_sql}/disp_name_key.csv', header=true)
    """)

    print("  Step 2/4: Loading criminal case IDs (judge merge key)...")
    con.execute(f"""
        CREATE TABLE criminal_case_ids AS
        SELECT DISTINCT
            ddl_case_id,
            ddl_filing_judge_id,
            ddl_decision_judge_id
        FROM read_csv('{cases_sql}/judge_case_merge_key.csv', header=true)
    """)

    print("  Step 3/4: Extracting Karnataka criminal cases (2010-2018)...")
    print("    (This reads ~15GB of CSV — may take 2-5 minutes)")
    con.execute(f"""
        CREATE TABLE cases AS
        SELECT
            c.ddl_case_id,
            CAST(c.year AS INTEGER) AS year,
            CAST(c.state_code AS INTEGER) AS state_code,
            CAST(c.dist_code AS INTEGER) AS dist_code,
            CAST(c.court_no AS INTEGER) AS court_no,
            c.cino,
            d.state_name,
            d.district_name,
            ct.court_name,
            CAST(c.type_name AS INTEGER) AS type_name,
            tn.type_name_s,
            CAST(c.purpose_name AS INTEGER) AS purpose_name,
            pn.purpose_name_s,
            CAST(c.disp_name AS INTEGER) AS disp_name,
            dn.disp_name_s,
            c.judge_position,
            c.female_defendant,
            c.female_petitioner,
            c.female_adv_def,
            c.female_adv_pet,
            TRY_CAST(c.date_of_filing AS DATE) AS date_of_filing,
            TRY_CAST(c.date_of_decision AS DATE) AS date_of_decision,
            TRY_CAST(c.date_first_list AS DATE) AS date_first_list,
            TRY_CAST(c.date_last_list AS DATE) AS date_last_list,
            TRY_CAST(c.date_next_list AS DATE) AS date_next_list,
            DATE_DIFF('day',
                TRY_CAST(c.date_of_filing AS DATE),
                TRY_CAST(c.date_of_decision AS DATE)
            ) AS case_duration_days,
            cr.ddl_filing_judge_id,
            cr.ddl_decision_judge_id
        FROM read_csv('{cases_sql}/cases_20*.csv', header=true, union_by_name=true) c
        INNER JOIN criminal_case_ids cr ON c.ddl_case_id = cr.ddl_case_id
        LEFT JOIN district_lookup d
          ON CAST(c.state_code AS INTEGER) = d.state_code
         AND CAST(c.dist_code AS INTEGER) = d.dist_code
        LEFT JOIN court_lookup ct
          ON CAST(c.state_code AS INTEGER) = ct.state_code
         AND CAST(c.dist_code AS INTEGER) = ct.dist_code
         AND CAST(c.court_no AS INTEGER) = ct.court_no
        LEFT JOIN case_types tn
          ON CAST(c.year AS INTEGER) = CAST(tn.year AS INTEGER)
         AND CAST(c.type_name AS INTEGER) = CAST(tn.type_name AS INTEGER)
        LEFT JOIN purposes pn
          ON CAST(c.year AS INTEGER) = CAST(pn.year AS INTEGER)
         AND CAST(c.purpose_name AS INTEGER) = CAST(pn.purpose_name AS INTEGER)
        LEFT JOIN dispositions dn
          ON CAST(c.year AS INTEGER) = CAST(dn.year AS INTEGER)
         AND CAST(c.disp_name AS INTEGER) = CAST(dn.disp_name AS INTEGER)
        WHERE CAST(c.state_code AS INTEGER) = {KARNATAKA_STATE_CODE}
    """)

    print("  Step 4/4: Cleaning up temp tables...")
    con.execute("DROP TABLE criminal_case_ids")
    con.execute("DROP TABLE district_lookup")
    con.execute("DROP TABLE court_lookup")

    stats = {}
    for table in ["states", "districts", "courts", "case_types", "purposes", "dispositions", "cases"]:
        stats[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    stats["years_covered"] = con.execute(
        "SELECT MIN(year), MAX(year) FROM cases"
    ).fetchone()
    stats["districts_with_cases"] = con.execute(
        "SELECT COUNT(DISTINCT district_name) FROM cases WHERE district_name IS NOT NULL"
    ).fetchone()[0]
    stats["null_district_cases"] = con.execute(
        "SELECT COUNT(*) FROM cases WHERE district_name IS NULL"
    ).fetchone()[0]
    stats["convicted_cases"] = con.execute(
        "SELECT COUNT(*) FROM cases WHERE disp_name_s ILIKE '%convict%'"
    ).fetchone()[0]
    stats["acquitted_cases"] = con.execute(
        "SELECT COUNT(*) FROM cases WHERE disp_name_s ILIKE '%acquit%'"
    ).fetchone()[0]

    con.close()
    return stats
