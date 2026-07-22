-- Unified demo criminal database (extends base schema)
-- Aligned with ksp_crime.db and cases.db (2018-2024)

CREATE TABLE IF NOT EXISTS districts (
    district_id     INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS police_units (
    unit_id         INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    district_id     INTEGER NOT NULL REFERENCES districts(district_id)
);

CREATE TABLE IF NOT EXISTS crime_groups (
    group_id        INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS crime_heads (
    head_id         INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    group_id        INTEGER REFERENCES crime_groups(group_id)
);

CREATE TABLE IF NOT EXISTS persons (
    person_id               INTEGER PRIMARY KEY,
    name                    TEXT NOT NULL,
    alias                   TEXT,
    age                     INTEGER,
    gender                  TEXT,
    caste_category          TEXT,
    education               TEXT,
    occupation              TEXT,
    district_id             INTEGER REFERENCES districts(district_id),
    district_name           TEXT,
    status                  TEXT,
    repeat_offender_score   REAL,
    risk_level              TEXT
);

CREATE TABLE IF NOT EXISTS fir_details (
    fir_id                  INTEGER PRIMARY KEY,
    district_id             INTEGER NOT NULL REFERENCES districts(district_id),
    unit_id                 INTEGER NOT NULL REFERENCES police_units(unit_id),
    crime_group_id          INTEGER REFERENCES crime_groups(group_id),
    crime_head_id           INTEGER REFERENCES crime_heads(head_id),
    io_id                   INTEGER,
    fir_year                INTEGER NOT NULL,
    fir_month               INTEGER,
    fir_day                 INTEGER,
    offence_duration        INTEGER,
    fir_type                TEXT,
    fir_stage               TEXT,
    complaint_mode          TEXT,
    latitude                REAL,
    longitude               REAL,
    place_of_offence        TEXT,
    distance_from_ps        TEXT,
    beat_name               TEXT,
    village_area_name       TEXT,
    male_victims            INTEGER DEFAULT 0,
    female_victims          INTEGER DEFAULT 0,
    victim_count            INTEGER DEFAULT 0,
    accused_count           INTEGER DEFAULT 0,
    arrested_male           INTEGER DEFAULT 0,
    arrested_female         INTEGER DEFAULT 0,
    arrested_count          INTEGER DEFAULT 0,
    chargesheeted_count     INTEGER DEFAULT 0,
    conviction_count        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accused_persons (
    accused_id          INTEGER PRIMARY KEY,
    fir_id              INTEGER NOT NULL REFERENCES fir_details(fir_id),
    person_id           INTEGER REFERENCES persons(person_id),
    accused_seq         INTEGER NOT NULL,
    signature_id        INTEGER,
    was_arrested        INTEGER DEFAULT 0,
    was_chargesheeted   INTEGER DEFAULT 0,
    was_convicted       INTEGER DEFAULT 0,
    UNIQUE(fir_id, accused_seq)
);

CREATE TABLE IF NOT EXISTS criminal_signatures (
    signature_id        INTEGER PRIMARY KEY,
    district_id         INTEGER NOT NULL REFERENCES districts(district_id),
    village_area_name   TEXT NOT NULL,
    crime_head_id       INTEGER NOT NULL REFERENCES crime_heads(head_id),
    fir_count           INTEGER DEFAULT 0,
    total_accused       INTEGER DEFAULT 0,
    total_convictions   INTEGER DEFAULT 0,
    first_year          INTEGER,
    last_year           INTEGER,
    repeat_offender_score REAL
);

CREATE TABLE IF NOT EXISTS co_accused_links (
    link_id         INTEGER PRIMARY KEY,
    fir_id          INTEGER NOT NULL REFERENCES fir_details(fir_id),
    accused_id_a    INTEGER NOT NULL,
    accused_id_b    INTEGER NOT NULL,
    link_weight     REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS behavior_features (
    fir_id                  INTEGER PRIMARY KEY REFERENCES fir_details(fir_id),
    day_of_week             INTEGER,
    is_weekend              INTEGER,
    is_heinous              INTEGER,
    has_geo                 INTEGER,
    victim_total            INTEGER,
    child_victim            INTEGER,
    female_victim           INTEGER,
    accused_count           INTEGER,
    arrest_rate             REAL,
    conviction_rate         REAL,
    chargesheet_rate        REAL,
    offence_duration_days   INTEGER,
    complaint_mode_code     INTEGER,
    crime_severity_score    REAL,
    temporal_risk_score     REAL
);

CREATE TABLE IF NOT EXISTS criminal_profiles (
    profile_id              INTEGER PRIMARY KEY,
    signature_id            INTEGER NOT NULL UNIQUE REFERENCES criminal_signatures(signature_id),
    district_name           TEXT,
    village_area_name       TEXT,
    primary_crime_head      TEXT,
    primary_crime_group     TEXT,
    total_firs              INTEGER,
    total_accused           INTEGER,
    avg_accused_per_fir     REAL,
    arrest_rate             REAL,
    conviction_rate         REAL,
    chargesheet_rate        REAL,
    heinous_ratio           REAL,
    peak_month              INTEGER,
    active_span_years       INTEGER,
    repeat_offender_score   REAL,
    risk_level              TEXT,
    behavioral_tags         TEXT
);

CREATE INDEX IF NOT EXISTS idx_fir_year ON fir_details(fir_year);
CREATE INDEX IF NOT EXISTS idx_fir_district ON fir_details(district_id);
CREATE INDEX IF NOT EXISTS idx_person_district ON persons(district_id);
CREATE INDEX IF NOT EXISTS idx_accused_person ON accused_persons(person_id);
CREATE INDEX IF NOT EXISTS idx_co_accused_fir ON co_accused_links(fir_id);
