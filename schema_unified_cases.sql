-- Unified demo cases database (2018-2024, linked to criminal FIRs)

CREATE TABLE IF NOT EXISTS cases (
    ddl_case_id         VARCHAR PRIMARY KEY,
    linked_fir_id       INTEGER,
    year                INTEGER NOT NULL,
    state_code          INTEGER,
    state_name          VARCHAR,
    district_name       VARCHAR,
    court_name          VARCHAR,
    type_name_s         VARCHAR,
    purpose_name_s      VARCHAR,
    disp_name_s         VARCHAR,
    date_of_filing      DATE,
    date_of_decision    DATE,
    case_duration_days  INTEGER,
    female_defendant    VARCHAR
);

CREATE TABLE IF NOT EXISTS fir_case_link (
    fir_id          INTEGER PRIMARY KEY,
    ddl_case_id     VARCHAR NOT NULL REFERENCES cases(ddl_case_id)
);

CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);
CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district_name);
CREATE INDEX IF NOT EXISTS idx_cases_disp ON cases(disp_name_s);
CREATE INDEX IF NOT EXISTS idx_cases_fir ON cases(linked_fir_id);
