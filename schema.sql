-- KSP Crime Database Schema
-- Compatible with PostgreSQL and SQLite

CREATE TABLE IF NOT EXISTS districts (
    district_id     INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    name_kn         TEXT,
    latitude        REAL,
    longitude       REAL,
    population      INTEGER,
    zone            TEXT
);

CREATE TABLE IF NOT EXISTS police_stations (
    station_id      INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    district_id     INTEGER NOT NULL REFERENCES districts(district_id),
    latitude        REAL,
    longitude       REAL,
    station_code    TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS crime_heads (
    crime_head_id   INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,          -- IPC, BNS, SLL
    ipc_section     TEXT,
    severity        TEXT                    -- low, medium, high, critical
);

CREATE TABLE IF NOT EXISTS fir_records (
    fir_id              INTEGER PRIMARY KEY,
    fir_number          TEXT NOT NULL UNIQUE,
    station_id          INTEGER NOT NULL REFERENCES police_stations(station_id),
    crime_head_id       INTEGER NOT NULL REFERENCES crime_heads(crime_head_id),
    date_registered     DATE NOT NULL,
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    status              TEXT NOT NULL,      -- registered, under_investigation, chargesheeted, closed, pending_trial
    description         TEXT,
    victim_age          INTEGER,
    victim_gender       TEXT,
    accused_count       INTEGER DEFAULT 1,
    latitude            REAL,
    longitude           REAL,
    is_cyber            INTEGER DEFAULT 0,
    is_economic         INTEGER DEFAULT 0,
    chargesheet_filed   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS criminals (
    criminal_id     INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    alias           TEXT,
    age             INTEGER,
    gender          TEXT,
    district_id     INTEGER REFERENCES districts(district_id),
    aadhaar_hash    TEXT,
    status          TEXT,                   -- absconding, arrested, on_bail, convicted, acquitted
    created_at      DATE
);

CREATE TABLE IF NOT EXISTS fir_criminal_link (
    link_id         INTEGER PRIMARY KEY,
    fir_id          INTEGER NOT NULL REFERENCES fir_records(fir_id),
    criminal_id     INTEGER NOT NULL REFERENCES criminals(criminal_id),
    role            TEXT,                   -- accused, witness, victim
    UNIQUE(fir_id, criminal_id)
);

CREATE TABLE IF NOT EXISTS ncrb_crime_stats (
    stat_id         INTEGER PRIMARY KEY,
    crime_head      TEXT NOT NULL,
    category        TEXT,
    year            INTEGER NOT NULL,
    cases           INTEGER,
    crime_rate      REAL,
    ipc_cases       INTEGER,
    bns_cases       INTEGER,
    share_pct       REAL,
    source_table    TEXT
);

CREATE TABLE IF NOT EXISTS ncrb_city_stats (
    stat_id             INTEGER PRIMARY KEY,
    city                TEXT NOT NULL,
    state               TEXT,
    year                INTEGER NOT NULL,
    total_cases         INTEGER,
    ipc_cases           INTEGER,
    bns_cases           INTEGER,
    crime_rate          REAL,
    chargesheet_rate    REAL,
    stat_type           TEXT,               -- overall, sll, total_ipc_sll, women, children, senior, sc, st, economic, cyber
    source_table        TEXT
);

CREATE TABLE IF NOT EXISTS ncrb_complaint_stats (
    stat_id             INTEGER PRIMARY KEY,
    sl_no               TEXT,
    complaint_type      TEXT NOT NULL,
    num_complaints      INTEGER,
    num_firs            INTEGER,
    num_online_efir     INTEGER,
    year                INTEGER DEFAULT 2024,
    source_table        TEXT
);

CREATE TABLE IF NOT EXISTS ncrb_national_stats (
    stat_id                 INTEGER PRIMARY KEY,
    year                    INTEGER NOT NULL,
    population_lakhs        REAL,
    ipc_bns_incidence       INTEGER,
    sll_incidence           INTEGER,
    total_incidence         INTEGER,
    ipc_bns_crime_rate      REAL,
    sll_crime_rate          REAL,
    total_crime_rate        REAL,
    ipc_bns_share_pct       REAL,
    source_table            TEXT
);

CREATE TABLE IF NOT EXISTS ncrb_economic_headwise (
    stat_id         INTEGER PRIMARY KEY,
    city            TEXT NOT NULL,
    state           TEXT,
    year            INTEGER NOT NULL,
    crime_head      TEXT NOT NULL,
    cases           INTEGER,
    source_table    TEXT
);

CREATE INDEX IF NOT EXISTS idx_fir_year ON fir_records(year);
CREATE INDEX IF NOT EXISTS idx_fir_station ON fir_records(station_id);
CREATE INDEX IF NOT EXISTS idx_fir_crime_head ON fir_records(crime_head_id);
CREATE INDEX IF NOT EXISTS idx_fir_date ON fir_records(date_registered);
CREATE INDEX IF NOT EXISTS idx_criminal_district ON criminals(district_id);
CREATE INDEX IF NOT EXISTS idx_fir_criminal_fir ON fir_criminal_link(fir_id);
CREATE INDEX IF NOT EXISTS idx_fir_criminal_criminal ON fir_criminal_link(criminal_id);
