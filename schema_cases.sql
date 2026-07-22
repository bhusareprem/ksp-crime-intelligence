-- Karnataka Judicial Cases Database (DDL e-Courts 2010-2018)
-- Criminal cases identified via judge_case_merge_key (DDL criminal subset)

CREATE TABLE IF NOT EXISTS states (
    year            INTEGER,
    state_code      VARCHAR,
    state_name      VARCHAR,
    pc11_state_name VARCHAR,
    pc11_state_id   VARCHAR
);

CREATE TABLE IF NOT EXISTS districts (
    year            INTEGER,
    state_code      VARCHAR,
    state_name      VARCHAR,
    dist_code       VARCHAR,
    district_name   VARCHAR,
    pc11_state_name VARCHAR,
    pc11_state_id   VARCHAR,
    pc11_district_name VARCHAR,
    pc11_district_id   VARCHAR
);

CREATE TABLE IF NOT EXISTS courts (
    year            INTEGER,
    state_code      VARCHAR,
    state_name      VARCHAR,
    district_name   VARCHAR,
    dist_code       VARCHAR,
    court_no        VARCHAR,
    court_name      VARCHAR
);

CREATE TABLE IF NOT EXISTS case_types (
    year            INTEGER,
    type_name       INTEGER,
    type_name_s     VARCHAR,
    count           INTEGER
);

CREATE TABLE IF NOT EXISTS purposes (
    year            INTEGER,
    purpose_name    INTEGER,
    purpose_name_s  VARCHAR,
    count           INTEGER
);

CREATE TABLE IF NOT EXISTS dispositions (
    year            INTEGER,
    disp_name       INTEGER,
    disp_name_s     VARCHAR,
    count           INTEGER
);

CREATE TABLE IF NOT EXISTS cases (
    ddl_case_id         VARCHAR PRIMARY KEY,
    year                INTEGER NOT NULL,
    state_code          INTEGER,
    dist_code           INTEGER,
    court_no            INTEGER,
    cino                VARCHAR,
    state_name          VARCHAR,
    district_name       VARCHAR,
    court_name          VARCHAR,
    type_name           INTEGER,
    type_name_s         VARCHAR,
    purpose_name        INTEGER,
    purpose_name_s      VARCHAR,
    disp_name           INTEGER,
    disp_name_s         VARCHAR,
    judge_position      VARCHAR,
    female_defendant    VARCHAR,
    female_petitioner   VARCHAR,
    female_adv_def      VARCHAR,
    female_adv_pet      VARCHAR,
    date_of_filing      DATE,
    date_of_decision    DATE,
    date_first_list     DATE,
    date_last_list      DATE,
    date_next_list      DATE,
    case_duration_days  INTEGER,
    ddl_filing_judge_id INTEGER,
    ddl_decision_judge_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);
CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district_name);
CREATE INDEX IF NOT EXISTS idx_cases_type ON cases(type_name_s);
CREATE INDEX IF NOT EXISTS idx_cases_disp ON cases(disp_name_s);
CREATE INDEX IF NOT EXISTS idx_cases_filing ON cases(date_of_filing);
