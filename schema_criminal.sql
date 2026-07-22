-- KSP Criminal Database (real FIR details)
-- Supports criminal network analysis and behavioral profiling

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

CREATE TABLE IF NOT EXISTS investigating_officers (
    io_id           INTEGER PRIMARY KEY,
    kgid            TEXT,
    name            TEXT
);

CREATE TABLE IF NOT EXISTS fir_details (
    fir_id                  INTEGER PRIMARY KEY,
    district_id             INTEGER NOT NULL REFERENCES districts(district_id),
    unit_id                 INTEGER NOT NULL REFERENCES police_units(unit_id),
    crime_group_id          INTEGER REFERENCES crime_groups(group_id),
    crime_head_id           INTEGER REFERENCES crime_heads(head_id),
    io_id                   INTEGER REFERENCES investigating_officers(io_id),
    fir_year                INTEGER NOT NULL,
    fir_month               INTEGER,
    fir_day                 INTEGER,
    offence_duration        INTEGER,
    fir_type                TEXT,
    fir_stage               TEXT,
    complaint_mode          TEXT,
    latitude                REAL,
    longitude               REAL,
    act_section             TEXT,
    place_of_offence        TEXT,
    distance_from_ps        TEXT,
    beat_name               TEXT,
    village_area_name       TEXT,
    male_victims            INTEGER DEFAULT 0,
    female_victims          INTEGER DEFAULT 0,
    boy_victims             INTEGER DEFAULT 0,
    girl_victims            INTEGER DEFAULT 0,
    age_0_victims           INTEGER DEFAULT 0,
    victim_count            INTEGER DEFAULT 0,
    accused_count           INTEGER DEFAULT 0,
    arrested_male           INTEGER DEFAULT 0,
    arrested_female         INTEGER DEFAULT 0,
    arrested_count          INTEGER DEFAULT 0,
    chargesheeted_count     INTEGER DEFAULT 0,
    conviction_count        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accused_persons (
    accused_id      INTEGER PRIMARY KEY,
    fir_id          INTEGER NOT NULL REFERENCES fir_details(fir_id),
    accused_seq     INTEGER NOT NULL,
    signature_id    INTEGER,
    was_arrested    INTEGER DEFAULT 0,
    was_chargesheeted INTEGER DEFAULT 0,
    was_convicted   INTEGER DEFAULT 0,
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
    accused_id_a    INTEGER NOT NULL REFERENCES accused_persons(accused_id),
    accused_id_b    INTEGER NOT NULL REFERENCES accused_persons(accused_id),
    link_weight     REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS signature_network_links (
    link_id         INTEGER PRIMARY KEY,
    signature_id    INTEGER NOT NULL REFERENCES criminal_signatures(signature_id),
    accused_id_a    INTEGER NOT NULL REFERENCES accused_persons(accused_id),
    accused_id_b    INTEGER NOT NULL REFERENCES accused_persons(accused_id),
    link_weight     REAL DEFAULT 0.5
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
CREATE INDEX IF NOT EXISTS idx_fir_crime_head ON fir_details(crime_head_id);
CREATE INDEX IF NOT EXISTS idx_fir_unit ON fir_details(unit_id);
CREATE INDEX IF NOT EXISTS idx_fir_village ON fir_details(village_area_name);
CREATE INDEX IF NOT EXISTS idx_accused_fir ON accused_persons(fir_id);
CREATE INDEX IF NOT EXISTS idx_accused_signature ON accused_persons(signature_id);
CREATE INDEX IF NOT EXISTS idx_co_accused_fir ON co_accused_links(fir_id);
CREATE INDEX IF NOT EXISTS idx_signature_district ON criminal_signatures(district_id);
CREATE INDEX IF NOT EXISTS idx_profile_risk ON criminal_profiles(risk_level);
CREATE INDEX IF NOT EXISTS idx_profile_score ON criminal_profiles(repeat_offender_score);
