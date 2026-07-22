-- ============================================================
-- KSP Crime Intelligence — Full FIR Schema
-- Based on: Police_FIR_ER_Diagram.pdf
-- Target: PostgreSQL 16 (also compatible with DuckDB syntax)
-- Scale: 906 stations · 32 districts · 7 ranges · ~500k FIRs
-- ============================================================

-- ── Lookup / Reference Tables ──────────────────────────────

CREATE TABLE IF NOT EXISTS State (
    StateID       INTEGER PRIMARY KEY,
    StateName     VARCHAR(100) NOT NULL,
    NationalityID INTEGER,
    Active        BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS District (
    DistrictID   INTEGER PRIMARY KEY,
    DistrictName VARCHAR(100) NOT NULL,
    StateID      INTEGER NOT NULL REFERENCES State(StateID),
    Latitude     DECIMAL(9,6),
    Longitude    DECIMAL(9,6),
    Population   INTEGER,
    Active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS UnitType (
    UnitTypeID   INTEGER PRIMARY KEY,
    UnitTypeName VARCHAR(100) NOT NULL,
    CityDistState VARCHAR(20),   -- 'City' | 'District' | 'State'
    Hierarchy    INTEGER,        -- 1=State HQ, 2=Range, 3=District, 4=Circle, 5=Station
    Active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Unit (
    UnitID       INTEGER PRIMARY KEY,
    UnitName     VARCHAR(200) NOT NULL,
    TypeID       INTEGER NOT NULL REFERENCES UnitType(UnitTypeID),
    ParentUnit   INTEGER REFERENCES Unit(UnitID),
    StateID      INTEGER NOT NULL REFERENCES State(StateID),
    DistrictID   INTEGER REFERENCES District(DistrictID),
    Latitude     DECIMAL(9,6),
    Longitude    DECIMAL(9,6),
    Active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Rank (
    RankID    INTEGER PRIMARY KEY,
    RankName  VARCHAR(100) NOT NULL,
    Hierarchy INTEGER,
    Active    BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Designation (
    DesignationID   INTEGER PRIMARY KEY,
    DesignationName VARCHAR(100) NOT NULL,
    Active          BOOLEAN DEFAULT TRUE,
    SortOrder       INTEGER
);

CREATE TABLE IF NOT EXISTS Employee (
    EmployeeID           INTEGER PRIMARY KEY,
    DistrictID           INTEGER REFERENCES District(DistrictID),
    UnitID               INTEGER NOT NULL REFERENCES Unit(UnitID),
    RankID               INTEGER NOT NULL REFERENCES Rank(RankID),
    DesignationID        INTEGER NOT NULL REFERENCES Designation(DesignationID),
    KGID                 VARCHAR(20) UNIQUE,
    FirstName            VARCHAR(100) NOT NULL,
    LastName             VARCHAR(100),
    EmployeeDOB          DATE,
    GenderID             INTEGER,  -- 1=Male 2=Female 3=Trans
    BloodGroupID         INTEGER,
    PhysicallyChallenged BOOLEAN DEFAULT FALSE,
    AppointmentDate      DATE,
    Active               BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS CaseCategory (
    CaseCategoryID INTEGER PRIMARY KEY,
    LookupValue    VARCHAR(50) NOT NULL,  -- FIR, UDR, PAR, Zero FIR, NC
    CategoryCode   CHAR(1)               -- 1=FIR, 3=UDR, 4=PAR, 8=ZeroFIR
);

CREATE TABLE IF NOT EXISTS GravityOffence (
    GravityOffenceID INTEGER PRIMARY KEY,
    LookupValue      VARCHAR(50) NOT NULL  -- Heinous, Non-Heinous
);

CREATE TABLE IF NOT EXISTS CrimeHead (
    CrimeHeadID    INTEGER PRIMARY KEY,
    CrimeGroupName VARCHAR(200) NOT NULL,
    Active         BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS CrimeSubHead (
    CrimeSubHeadID INTEGER PRIMARY KEY,
    CrimeHeadID    INTEGER NOT NULL REFERENCES CrimeHead(CrimeHeadID),
    CrimeHeadName  VARCHAR(200) NOT NULL,
    SeqID          INTEGER,
    MotiveType     VARCHAR(50),  -- communal, caste, gender, economic, other
    Active         BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Act (
    ActCode         VARCHAR(20) PRIMARY KEY,
    ActDescription  VARCHAR(300) NOT NULL,
    ShortName       VARCHAR(50),
    Active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Section (
    ActCode            VARCHAR(20) NOT NULL REFERENCES Act(ActCode),
    SectionCode        VARCHAR(20) NOT NULL,
    SectionDescription VARCHAR(500),
    Active             BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (ActCode, SectionCode)
);

CREATE TABLE IF NOT EXISTS CrimeHeadActSection (
    CrimeHeadID INTEGER NOT NULL REFERENCES CrimeHead(CrimeHeadID),
    ActCode     VARCHAR(20) NOT NULL REFERENCES Act(ActCode),
    SectionCode VARCHAR(20) NOT NULL,
    PRIMARY KEY (CrimeHeadID, ActCode, SectionCode)
);

CREATE TABLE IF NOT EXISTS CaseStatusMaster (
    CaseStatusID   INTEGER PRIMARY KEY,
    CaseStatusName VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS Court (
    CourtID    INTEGER PRIMARY KEY,
    CourtName  VARCHAR(200) NOT NULL,
    DistrictID INTEGER REFERENCES District(DistrictID),
    StateID    INTEGER REFERENCES State(StateID),
    Active     BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ReligionMaster (
    ReligionID   INTEGER PRIMARY KEY,
    ReligionName VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS CasteMaster (
    caste_master_id   INTEGER PRIMARY KEY,
    caste_master_name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS OccupationMaster (
    OccupationID   INTEGER PRIMARY KEY,
    OccupationName VARCHAR(100) NOT NULL
);

-- ── Core FIR Tables ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS CaseMaster (
    CaseMasterID         INTEGER PRIMARY KEY,
    CrimeNo              VARCHAR(30) UNIQUE NOT NULL,
    CaseNo               VARCHAR(20),
    CrimeRegisteredDate  DATE NOT NULL,
    PolicePersonID       INTEGER REFERENCES Employee(EmployeeID),
    PoliceStationID      INTEGER NOT NULL REFERENCES Unit(UnitID),
    CaseCategoryID       INTEGER NOT NULL REFERENCES CaseCategory(CaseCategoryID),
    GravityOffenceID     INTEGER REFERENCES GravityOffence(GravityOffenceID),
    CrimeMajorHeadID     INTEGER REFERENCES CrimeHead(CrimeHeadID),
    CrimeMinorHeadID     INTEGER REFERENCES CrimeSubHead(CrimeSubHeadID),
    CaseStatusID         INTEGER REFERENCES CaseStatusMaster(CaseStatusID),
    CourtID              INTEGER REFERENCES Court(CourtID),
    IncidentFromDate     TIMESTAMP,
    IncidentToDate       TIMESTAMP,
    InfoReceivedPSDate   TIMESTAMP,
    Latitude             DECIMAL(9,6),
    Longitude            DECIMAL(9,6),
    BriefFacts           TEXT
);

CREATE TABLE IF NOT EXISTS ComplainantDetails (
    ComplainantID  INTEGER PRIMARY KEY,
    CaseMasterID   INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    ComplainantName VARCHAR(200),
    AgeYear        INTEGER,
    OccupationID   INTEGER REFERENCES OccupationMaster(OccupationID),
    ReligionID     INTEGER REFERENCES ReligionMaster(ReligionID),
    CasteID        INTEGER REFERENCES CasteMaster(caste_master_id),
    GenderID       INTEGER
);

CREATE TABLE IF NOT EXISTS Victim (
    VictimMasterID INTEGER PRIMARY KEY,
    CaseMasterID   INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    VictimName     VARCHAR(200),
    AgeYear        INTEGER,
    GenderID       INTEGER,
    VictimPolice   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS Accused (
    AccusedMasterID INTEGER PRIMARY KEY,
    CaseMasterID    INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    AccusedName     VARCHAR(200),
    AgeYear         INTEGER,
    GenderID        INTEGER,
    PersonID        VARCHAR(5),   -- A1, A2, A3...
    ReligionID      INTEGER REFERENCES ReligionMaster(ReligionID),
    CasteID         INTEGER REFERENCES CasteMaster(caste_master_id),
    OccupationID    INTEGER REFERENCES OccupationMaster(OccupationID),
    Nationality     VARCHAR(50) DEFAULT 'Indian',
    District        VARCHAR(100)  -- accused home district
);

CREATE TABLE IF NOT EXISTS ArrestSurrender (
    ArrestSurrenderID       INTEGER PRIMARY KEY,
    CaseMasterID            INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    AccusedMasterID         INTEGER NOT NULL REFERENCES Accused(AccusedMasterID),
    ArrestSurrenderTypeID   INTEGER,  -- 1=Arrest, 2=Surrender
    ArrestSurrenderDate     DATE,
    ArrestSurrenderStateId  INTEGER REFERENCES State(StateID),
    ArrestSurrenderDistrictId INTEGER REFERENCES District(DistrictID),
    PoliceStationID         INTEGER REFERENCES Unit(UnitID),
    IOID                    INTEGER REFERENCES Employee(EmployeeID),
    CourtID                 INTEGER REFERENCES Court(CourtID),
    IsAccused               BOOLEAN DEFAULT TRUE,
    IsComplainantAccused    BOOLEAN DEFAULT FALSE,
    BailGranted             BOOLEAN DEFAULT FALSE,
    RemandDays              INTEGER
);

CREATE TABLE IF NOT EXISTS ActSectionAssociation (
    CaseMasterID  INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    ActID         VARCHAR(20) NOT NULL REFERENCES Act(ActCode),
    SectionID     VARCHAR(20) NOT NULL,
    ActOrderID    INTEGER,
    SectionOrderID INTEGER,
    PRIMARY KEY (CaseMasterID, ActID, SectionID)
);

CREATE TABLE IF NOT EXISTS ChargesheetDetails (
    CSID           INTEGER PRIMARY KEY,
    CaseMasterID   INTEGER NOT NULL REFERENCES CaseMaster(CaseMasterID),
    csdate         TIMESTAMP,
    cstype         CHAR(1),  -- A=Chargesheet, B=False Case, C=Undetected
    PolicePersonID INTEGER REFERENCES Employee(EmployeeID)
);

-- ── Gang / Network Extension (new) ─────────────────────────

CREATE TABLE IF NOT EXISTS CrimeGang (
    GangID          INTEGER PRIMARY KEY,
    GangName        VARCHAR(200),
    Specialization  VARCHAR(100),  -- cyber_fraud, burglary, narcotics, etc.
    ActiveSince     INTEGER,       -- year
    HomeDistrictID  INTEGER REFERENCES District(DistrictID),
    Active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS AccusedGangLink (
    AccusedMasterID INTEGER NOT NULL REFERENCES Accused(AccusedMasterID),
    GangID          INTEGER NOT NULL REFERENCES CrimeGang(GangID),
    Role            VARCHAR(50),  -- leader, member, financier, mule
    JoinedYear      INTEGER,
    PRIMARY KEY (AccusedMasterID, GangID)
);

-- ── Indexes for fast chatbot queries ───────────────────────

CREATE INDEX IF NOT EXISTS idx_casemaster_station  ON CaseMaster(PoliceStationID);
CREATE INDEX IF NOT EXISTS idx_casemaster_district ON CaseMaster(PoliceStationID, CrimeRegisteredDate);
CREATE INDEX IF NOT EXISTS idx_casemaster_date     ON CaseMaster(CrimeRegisteredDate);
CREATE INDEX IF NOT EXISTS idx_casemaster_minor    ON CaseMaster(CrimeMinorHeadID);
CREATE INDEX IF NOT EXISTS idx_accused_case        ON Accused(CaseMasterID);
CREATE INDEX IF NOT EXISTS idx_victim_case         ON Victim(CaseMasterID);
CREATE INDEX IF NOT EXISTS idx_arrest_case         ON ArrestSurrender(CaseMasterID);
CREATE INDEX IF NOT EXISTS idx_cs_case             ON ChargesheetDetails(CaseMasterID);
CREATE INDEX IF NOT EXISTS idx_unit_district       ON Unit(DistrictID);
CREATE INDEX IF NOT EXISTS idx_employee_unit       ON Employee(UnitID);
