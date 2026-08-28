"""Schema documentation and example SQL for NL→SQL prompts."""

KSP_CRIME_SCHEMA = """
Database: ksp_crime (SQLite — NOT DuckDB)
Engine rules: use LIKE not ILIKE; use crime_head_id not ipc_section for joins

Tables & columns:
- districts(district_id, name, population, zone)
- police_stations(station_id, name, district_id)
- crime_heads(crime_head_id, name, category, ipc_section, severity)
- fir_records(fir_id, station_id, crime_head_id, year, month, accused_count)
- criminals(criminal_id, name, alias, age, gender, district_id, status)
- fir_criminal_link(fir_id, criminal_id, role)

CORRECT joins:
  fir_records f → police_stations ps ON f.station_id = ps.station_id
  ps → districts d ON ps.district_id = d.district_id
  f → crime_heads ch ON f.crime_head_id = ch.crime_head_id
  criminals c → districts d ON c.district_id = d.district_id

Example — murder rate by district 2023:
  SELECT d.name, COUNT(f.fir_id) AS murders,
         ROUND(COUNT(f.fir_id)*100000.0/d.population,2) AS rate_per_100k
  FROM fir_records f
  JOIN police_stations ps ON f.station_id=ps.station_id
  JOIN districts d ON ps.district_id=d.district_id
  JOIN crime_heads ch ON f.crime_head_id=ch.crime_head_id
  WHERE ch.name LIKE '%Murder%' AND f.year=2023
  GROUP BY d.name, d.population ORDER BY rate_per_100k DESC LIMIT 5

Example — top criminals by name in Gadag:
  SELECT c.name, COUNT(l.fir_id) AS firs FROM criminals c
  JOIN districts d ON c.district_id=d.district_id
  JOIN fir_criminal_link l ON c.criminal_id=l.criminal_id
  WHERE d.name LIKE '%Gadag%' GROUP BY c.name ORDER BY firs DESC LIMIT 10
"""

CRIMINAL_SCHEMA = """
Database: criminal (DuckDB) — KSP FIR Database  500k FIRs · 906 stations · 31 districts
Engine: DuckDB — use ILIKE, EXTRACT(YEAR FROM date)::INT, CAST(x AS INTEGER)

Core tables:
  CaseMaster(CaseMasterID, CrimeNo, CaseNo, CrimeRegisteredDate DATE,
             PoliceStationID, CaseCategoryID, GravityOffenceID,
             CrimeMajorHeadID, CrimeMinorHeadID, CaseStatusID, CourtID,
             Latitude, Longitude)

  District(DistrictID, DistrictName, Population, Latitude, Longitude)

  Unit(UnitID, UnitName, TypeID, ParentUnit, DistrictID)
    -- TypeID: 2=Range HQ  3=District HQ  5=Station  7=Railway  8=Traffic

  Accused(AccusedMasterID, CaseMasterID, AccusedName, AgeYear,
          GenderID, PersonID, ReligionID, CasteID, OccupationID,
          Nationality, District)
          -- GenderID: 1=Male 2=Female 3=Trans

  Victim(VictimMasterID, CaseMasterID, VictimName, AgeYear, GenderID, VictimPolice)

  ComplainantDetails(ComplainantID, CaseMasterID, ComplainantName,
                     AgeYear, OccupationID, ReligionID, CasteID, GenderID)

  ArrestSurrender(ArrestSurrenderID, CaseMasterID, AccusedMasterID,
                  ArrestSurrenderTypeID, ArrestSurrenderDate,
                  ArrestSurrenderDistrictId, BailGranted, RemandDays)
                  -- TypeID: 1=Arrest 2=Surrender

  ChargesheetDetails(CSID, CaseMasterID, csdate TIMESTAMP,
                     cstype CHAR)  -- A=CS B=FalseCase C=Undetected

  CrimeHead(CrimeHeadID, CrimeGroupName)
    -- major groups: 1=Body 2=Property 3=Women 4=Children 6=Economic
    --               7=Cyber 8=NDPS 9=SC/ST 10=Communal 11=Accident
  CrimeSubHead(CrimeSubHeadID, CrimeHeadID, CrimeHeadName, MotiveType)
    -- MotiveType: 'communal' | 'caste' | 'gender' | 'economic' | NULL

  CrimeGang(GangID, GangName, Specialization, ActiveSince, HomeDistrictID)
  AccusedGangLink(AccusedMasterID, GangID, Role, JoinedYear)
    -- Role: leader | member | financier | mule | lookout

  CaseStatusMaster(CaseStatusID, CaseStatusName)
    -- 1=Registered 2=Investigation 3=ChargeSheet 4=FinalReport 5=Court 6=Closed

  OccupationMaster(OccupationID, OccupationName)
  ReligionMaster(ReligionID, ReligionName)
  CasteMaster(caste_master_id, caste_master_name)

KEY JOINS — always go CaseMaster → Unit → District for geography:
  CaseMaster cm JOIN Unit u ON cm.PoliceStationID = u.UnitID
  Unit u JOIN District d ON u.DistrictID = d.DistrictID
  CaseMaster cm JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
  CrimeSubHead csh JOIN CrimeHead ch ON csh.CrimeHeadID = ch.CrimeHeadID
  Accused a JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
  ArrestSurrender ar JOIN Accused a ON ar.AccusedMasterID = a.AccusedMasterID
  AccusedGangLink agl JOIN CrimeGang g ON agl.GangID = g.GangID

NEVER use fir_details / persons / accused_persons / co_accused_links / crime_heads (those are old schema)

Example — crimes in Bengaluru Urban 2023:
  SELECT csh.CrimeHeadName AS crime_type, COUNT(*) AS fir_count
  FROM CaseMaster cm
  JOIN Unit u ON cm.PoliceStationID = u.UnitID
  JOIN District d ON u.DistrictID = d.DistrictID
  JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
  WHERE d.DistrictName ILIKE '%Bengaluru Urban%'
    AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
  GROUP BY csh.CrimeHeadName ORDER BY fir_count DESC LIMIT 10

Example — murder count by district 2023:
  SELECT d.DistrictName AS district, COUNT(*) AS murder_firs
  FROM CaseMaster cm
  JOIN Unit u ON cm.PoliceStationID = u.UnitID
  JOIN District d ON u.DistrictID = d.DistrictID
  JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
  WHERE csh.CrimeHeadName ILIKE '%murder%'
    AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
  GROUP BY d.DistrictName ORDER BY murder_firs DESC LIMIT 5

Example — accused persons in a case / repeat offenders:
  -- IMPORTANT: Accused has ONE ROW PER CASE and AccusedMasterID is unique per
  -- row, so GROUP BY AccusedMasterID gives every person a count of 1 and finds
  -- no repeat offenders. Always group repeat-offender queries by AccusedName.
  SELECT a.AccusedName, MAX(a.AgeYear) AS age, MAX(a.District) AS district,
         COUNT(DISTINCT a.CaseMasterID) AS fir_count
  FROM Accused a
  WHERE a.AccusedName IS NOT NULL
  GROUP BY a.AccusedName
  ORDER BY fir_count DESC LIMIT 20

Example — cyber crime gang members:
  SELECT g.GangName, g.Specialization, a.AccusedName, agl.Role,
         COUNT(DISTINCT a.CaseMasterID) AS fir_count
  FROM AccusedGangLink agl
  JOIN CrimeGang g ON agl.GangID = g.GangID
  JOIN Accused a ON agl.AccusedMasterID = a.AccusedMasterID
  WHERE g.Specialization ILIKE '%cyber%'
  GROUP BY g.GangID, g.GangName, g.Specialization, a.AccusedName, agl.Role
  ORDER BY fir_count DESC LIMIT 20

Example — communal / hate crime trends:
  SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
         d.DistrictName AS district, csh.CrimeHeadName AS crime_type,
         COUNT(*) AS fir_count
  FROM CaseMaster cm
  JOIN Unit u ON cm.PoliceStationID = u.UnitID
  JOIN District d ON u.DistrictID = d.DistrictID
  JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
  WHERE csh.MotiveType IN ('communal','caste')
     OR csh.CrimeHeadName ILIKE '%communal%'
     OR csh.CrimeHeadName ILIKE '%riot%'
  GROUP BY 1,2,3 ORDER BY fir_count DESC
"""

CASES_SCHEMA = """
Database: cases (DuckDB)
District names are UPPERCASE: 'GADAG', 'BENGALURU', 'HASSAN'

Example — convictions in district:
  SELECT district_name, disp_name_s, COUNT(*) FROM cases
  WHERE district_name ILIKE '%GADAG%' AND disp_name_s ILIKE '%convict%'
  GROUP BY district_name, disp_name_s
"""

SCHEMAS = {
    "ksp_crime": KSP_CRIME_SCHEMA,
    "criminal": CRIMINAL_SCHEMA,
    "fir": CRIMINAL_SCHEMA,   # alias — both names point to ksp_fir.duckdb
    "cases": CASES_SCHEMA,
}

DB_DESCRIPTIONS = {
    "ksp_crime": "NCRB national stats + synthetic demo FIRs with named criminals",
    "criminal": "KSP FIR Database — 500k FIRs, 31 districts, 906 stations (2020-2024)",
    "fir": "KSP FIR Database — 500k FIRs, 31 districts, 906 stations (2020-2024)",
    "cases": "Criminal court cases 2010-2018",
}

SQL_EXAMPLES = {
    "ksp_crime": [
        "Murder rate: JOIN fir_records→police_stations→districts, crime_heads ON crime_head_id",
        "Criminal names: criminals JOIN districts JOIN fir_criminal_link",
    ],
    "criminal": [
        "District crimes: CaseMaster JOIN Unit ON PoliceStationID JOIN District ON DistrictID JOIN CrimeSubHead ON CrimeMinorHeadID",
        "Accused: SELECT AccusedName, COUNT(DISTINCT CaseMasterID) FROM Accused GROUP BY AccusedName ORDER BY count DESC (group by NAME, not AccusedMasterID — that is unique per row)",
        "Gangs: AccusedGangLink JOIN CrimeGang JOIN Accused GROUP BY GangName",
    ],
    "fir": [
        "District crimes: CaseMaster JOIN Unit ON PoliceStationID JOIN District ON DistrictID JOIN CrimeSubHead ON CrimeMinorHeadID",
        "Accused repeat: SELECT AccusedName, COUNT(DISTINCT CaseMasterID) FROM Accused GROUP BY AccusedName HAVING count > 1 (NEVER group by AccusedMasterID — it is unique per row, so every count becomes 1)",
    ],
}
