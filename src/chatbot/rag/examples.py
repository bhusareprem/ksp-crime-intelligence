"""Curated SQL examples per database — retrieved by similarity at query time."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryExample:
    question: str
    sql: str
    tags: tuple[str, ...]


KSP_CRIME_EXAMPLES: list[QueryExample] = [
    QueryExample(
        "How many thefts in Bengaluru in 2024?",
        """SELECT d.name AS district, ch.name AS crime_type, COUNT(*) AS count
FROM fir_records f
JOIN police_stations ps ON f.station_id = ps.station_id
JOIN districts d ON ps.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
WHERE d.name LIKE '%Bengaluru%' AND ch.name LIKE '%Theft%' AND f.year = 2024
GROUP BY d.name, ch.name ORDER BY count DESC""",
        ("theft", "bengaluru", "fir", "count", "district"),
    ),
    QueryExample(
        "NCRB cyber crimes in Bengaluru 2024",
        """SELECT city, year, total_cases, crime_rate, chargesheet_rate, stat_type
FROM ncrb_city_stats
WHERE city = 'Bengaluru' AND state = 'Karnataka' AND year = 2024 AND stat_type = 'cyber'""",
        ("ncrb", "cyber", "bengaluru", "national", "rate"),
    ),
    QueryExample(
        "Top 5 districts by murder rate in 2023",
        """SELECT d.name AS district, COUNT(f.fir_id) AS murder_firs, d.population,
       ROUND(COUNT(f.fir_id) * 100000.0 / d.population, 2) AS rate_per_100k
FROM fir_records f
JOIN police_stations ps ON f.station_id = ps.station_id
JOIN districts d ON ps.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
WHERE ch.name LIKE '%Murder%' AND f.year = 2023
GROUP BY d.name, d.population ORDER BY rate_per_100k DESC LIMIT 5""",
        ("murder", "rate", "district", "population", "2023"),
    ),
    QueryExample(
        "Top 10 criminal names in Gadag district",
        """SELECT c.name, COUNT(l.fir_id) AS linked_firs
FROM criminals c
JOIN districts d ON c.district_id = d.district_id
JOIN fir_criminal_link l ON c.criminal_id = l.criminal_id
WHERE d.name LIKE '%Gadag%'
GROUP BY c.name ORDER BY linked_firs DESC LIMIT 10""",
        ("criminal", "name", "gadag", "district", "top"),
    ),
    QueryExample(
        "Who is top criminal in Karnataka?",
        """SELECT c.name, d.name AS district, COUNT(l.fir_id) AS linked_firs
FROM criminals c
JOIN districts d ON c.district_id = d.district_id
JOIN fir_criminal_link l ON c.criminal_id = l.criminal_id
GROUP BY c.criminal_id, c.name, d.name ORDER BY linked_firs DESC LIMIT 10""",
        ("criminal", "name", "top", "karnataka", "who"),
    ),
    QueryExample(
        "National crime rate trend NCRB",
        """SELECT year, total_incidence, total_crime_rate, ipc_bns_crime_rate
FROM ncrb_national_stats ORDER BY year DESC LIMIT 10""",
        ("ncrb", "national", "rate", "trend", "all india"),
    ),
    QueryExample(
        "Compare metro city crime rates 2024",
        """SELECT city, year, total_cases, crime_rate, chargesheet_rate
FROM ncrb_city_stats
WHERE stat_type = 'overall' AND year = 2024
ORDER BY crime_rate DESC""",
        ("ncrb", "metro", "city", "compare", "rate", "2024"),
    ),
    QueryExample(
        "Economic offences in Bengaluru NCRB",
        """SELECT city, year, crime_head, cases
FROM ncrb_economic_headwise
WHERE city = 'Bengaluru' AND year = 2024 ORDER BY cases DESC LIMIT 10""",
        ("ncrb", "economic", "bengaluru", "offence"),
    ),
    QueryExample(
        "Women related crimes national stats",
        """SELECT city, year, total_cases, crime_rate
FROM ncrb_city_stats
WHERE stat_type = 'women' AND state = 'Karnataka' AND year = 2024
ORDER BY total_cases DESC""",
        ("ncrb", "women", "national", "karnataka"),
    ),
    QueryExample(
        "FIR count by crime type in Mysuru 2023",
        """SELECT ch.name AS crime_type, COUNT(*) AS fir_count
FROM fir_records f
JOIN police_stations ps ON f.station_id = ps.station_id
JOIN districts d ON ps.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
WHERE d.name LIKE '%Mysuru%' AND f.year = 2023
GROUP BY ch.name ORDER BY fir_count DESC LIMIT 10""",
        ("fir", "mysuru", "crime type", "2023", "district"),
    ),
    QueryExample(
        "Cyber FIRs in demo database 2024",
        """SELECT d.name, COUNT(*) AS cyber_firs
FROM fir_records f
JOIN police_stations ps ON f.station_id = ps.station_id
JOIN districts d ON ps.district_id = d.district_id
WHERE f.is_cyber = 1 AND f.year = 2024
GROUP BY d.name ORDER BY cyber_firs DESC LIMIT 10""",
        ("cyber", "fir", "2024", "demo"),
    ),
    QueryExample(
        "Chargesheet rate Bengaluru NCRB",
        """SELECT city, year, chargesheet_rate, total_cases
FROM ncrb_city_stats
WHERE city = 'Bengaluru' AND stat_type = 'overall' ORDER BY year DESC LIMIT 5""",
        ("ncrb", "chargesheet", "bengaluru", "rate"),
    ),
    QueryExample(
        "IPC vs BNS cases national",
        """SELECT year, ipc_bns_incidence, ipc_bns_share_pct, total_incidence
FROM ncrb_national_stats ORDER BY year DESC""",
        ("ncrb", "ipc", "bns", "national"),
    ),
    QueryExample(
        "Complaint to FIR conversion stats",
        """SELECT complaint_type, num_complaints, num_firs, num_online_efir
FROM ncrb_complaint_stats WHERE year = 2024 ORDER BY num_firs DESC""",
        ("ncrb", "complaint", "fir", "conversion"),
    ),
    QueryExample(
        "Crime severity breakdown in Ballari",
        """SELECT ch.severity, COUNT(*) AS count
FROM fir_records f
JOIN police_stations ps ON f.station_id = ps.station_id
JOIN districts d ON ps.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.crime_head_id
WHERE d.name LIKE '%Ballari%' AND f.year = 2024
GROUP BY ch.severity ORDER BY count DESC""",
        ("severity", "ballari", "fir", "district"),
    ),
]

CRIMINAL_EXAMPLES: list[QueryExample] = [
    QueryExample(
        "How many thefts in Bengaluru in 2024?",
        """SELECT COUNT(*) AS theft_firs
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE d.DistrictName ILIKE '%Bengaluru Urban%' AND csh.CrimeHeadName ILIKE '%theft%'
  AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2024""",
        ("theft", "bengaluru", "count", "2024", "fir"),
    ),
    QueryExample(
        "Murder FIRs by district in 2023",
        """SELECT d.DistrictName AS district, COUNT(*) AS murder_firs
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE csh.CrimeHeadName ILIKE '%murder%' AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
GROUP BY d.DistrictName ORDER BY murder_firs DESC LIMIT 10""",
        ("murder", "district", "2023", "fir"),
    ),
    QueryExample(
        "Crime breakdown in Gadag district",
        """SELECT csh.CrimeHeadName AS crime_type, COUNT(*) AS fir_count
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE d.DistrictName ILIKE '%Gadag%'
GROUP BY csh.CrimeHeadName ORDER BY fir_count DESC LIMIT 10""",
        ("gadag", "district", "crime", "breakdown", "overview"),
    ),
    QueryExample(
        "Top repeat accused statewide",
        """-- Group by AccusedName: AccusedMasterID is one row per case, so grouping
-- on it gives every person exactly 1 FIR and finds no repeat offenders.
SELECT a.AccusedName AS name, MAX(a.District) AS district,
       COUNT(DISTINCT a.CaseMasterID) AS fir_count
FROM Accused a
WHERE a.AccusedName IS NOT NULL
GROUP BY a.AccusedName
HAVING COUNT(DISTINCT a.CaseMasterID) > 1
ORDER BY fir_count DESC LIMIT 15""",
        ("repeat", "offender", "accused", "top", "name"),
    ),
    QueryExample(
        "Cyber crime gangs and their members",
        """SELECT g.GangName, g.Specialization,
       COUNT(DISTINCT agl.AccusedMasterID) AS members,
       COUNT(DISTINCT a.CaseMasterID) AS linked_firs
FROM CrimeGang g
JOIN AccusedGangLink agl ON agl.GangID = g.GangID
JOIN Accused a ON agl.AccusedMasterID = a.AccusedMasterID
WHERE g.Specialization ILIKE '%cyber%'
GROUP BY g.GangID, g.GangName, g.Specialization
ORDER BY linked_firs DESC LIMIT 10""",
        ("gang", "cyber", "organized", "network", "members"),
    ),
    QueryExample(
        "Cyber crime FIRs by district 2023",
        """SELECT d.DistrictName AS district, COUNT(*) AS cyber_firs
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE csh.CrimeHeadName ILIKE '%cyber%' AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
GROUP BY d.DistrictName ORDER BY cyber_firs DESC LIMIT 10""",
        ("cyber", "district", "2023", "fir"),
    ),
    QueryExample(
        "Monthly FIR trend in Mysuru 2023",
        """SELECT EXTRACT(MONTH FROM cm.CrimeRegisteredDate)::INT AS month, COUNT(*) AS fir_count
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
WHERE d.DistrictName ILIKE '%Mysuru%' AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023
GROUP BY month ORDER BY month""",
        ("trend", "monthly", "mysuru", "2023"),
    ),
    QueryExample(
        "Total FIRs registered in 2024",
        """SELECT COUNT(*) AS fir_count
FROM CaseMaster cm
WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2024""",
        ("total", "count", "fir", "2024", "statewide"),
    ),
    QueryExample(
        "POCSO cases by district",
        """SELECT d.DistrictName AS district, COUNT(*) AS pocso_cases
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE csh.CrimeHeadName ILIKE '%POCSO%'
GROUP BY d.DistrictName ORDER BY pocso_cases DESC""",
        ("pocso", "district", "child", "count"),
    ),
    QueryExample(
        "kannada thefts in Mysuru 2023 (kallathana Mysuru)",
        """SELECT COUNT(*) AS theft_firs
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE d.DistrictName ILIKE '%Mysuru%' AND csh.CrimeHeadName ILIKE '%theft%'
  AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = 2023""",
        ("kannada", "theft", "mysuru", "2023", "kalasu"),
    ),
    QueryExample(
        "kannada murders in Bengaluru (kole Bengaluru)",
        """SELECT COUNT(*) AS murder_firs
FROM CaseMaster cm
JOIN Unit u ON cm.PoliceStationID = u.UnitID
JOIN District d ON u.DistrictID = d.DistrictID
JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
WHERE d.DistrictName ILIKE '%Bengaluru Urban%' AND csh.CrimeHeadName ILIKE '%murder%'""",
        ("kannada", "murder", "bengaluru", "kole"),
    ),
]

CASES_EXAMPLES: list[QueryExample] = [
    QueryExample(
        "Convicted cases in Bengaluru 2017",
        """SELECT district_name, disp_name_s, COUNT(*) AS case_count
FROM cases
WHERE district_name ILIKE '%BENGALURU%' AND year = 2017 AND disp_name_s ILIKE '%convict%'
GROUP BY district_name, disp_name_s ORDER BY case_count DESC""",
        ("convict", "bengaluru", "2017", "court"),
    ),
    QueryExample(
        "Acquittal rate by district 2016",
        """SELECT district_name,
       SUM(CASE WHEN disp_name_s ILIKE '%acquit%' THEN 1 ELSE 0 END) AS acquitted,
       COUNT(*) AS total,
       ROUND(SUM(CASE WHEN disp_name_s ILIKE '%acquit%' THEN 1 ELSE 0 END)*100.0/COUNT(*), 1) AS acquittal_pct
FROM cases WHERE year = 2016
GROUP BY district_name ORDER BY acquittal_pct DESC LIMIT 10""",
        ("acquit", "rate", "district", "2016"),
    ),
    QueryExample(
        "Pending trial cases in Gadag",
        """SELECT type_name_s, disp_name_s, COUNT(*) AS count
FROM cases
WHERE district_name ILIKE '%GADAG%' AND disp_name_s ILIKE '%pending%'
GROUP BY type_name_s, disp_name_s ORDER BY count DESC""",
        ("pending", "trial", "gadag", "court"),
    ),
    QueryExample(
        "Average case duration by district 2015",
        """SELECT district_name,
       ROUND(AVG(case_duration_days), 0) AS avg_days,
       COUNT(*) AS cases
FROM cases WHERE year = 2015 AND case_duration_days IS NOT NULL
GROUP BY district_name ORDER BY avg_days DESC LIMIT 10""",
        ("duration", "district", "2015", "court"),
    ),
    QueryExample(
        "Top case types in Karnataka 2018",
        """SELECT type_name_s, COUNT(*) AS count
FROM cases WHERE year = 2018
GROUP BY type_name_s ORDER BY count DESC LIMIT 10""",
        ("case type", "2018", "karnataka"),
    ),
    QueryExample(
        "Disposed vs pending in Hassan 2014",
        """SELECT disp_name_s, COUNT(*) AS count
FROM cases
WHERE district_name ILIKE '%HASSAN%' AND year = 2014
GROUP BY disp_name_s ORDER BY count DESC""",
        ("disposition", "hassan", "2014"),
    ),
    QueryExample(
        "Female defendant cases Ballari 2017",
        """SELECT type_name_s, COUNT(*) AS count
FROM cases
WHERE district_name ILIKE '%BALLARI%' AND year = 2017 AND female_defendant = 'Y'
GROUP BY type_name_s ORDER BY count DESC LIMIT 10""",
        ("female", "defendant", "ballari", "2017"),
    ),
    QueryExample(
        "Court workload by court name 2016",
        """SELECT court_name, district_name, COUNT(*) AS cases
FROM cases WHERE year = 2016
GROUP BY court_name, district_name ORDER BY cases DESC LIMIT 15""",
        ("court", "workload", "2016"),
    ),
    QueryExample(
        "Conviction count Mysuru district 2013",
        """SELECT COUNT(*) AS convicted_cases
FROM cases
WHERE district_name ILIKE '%MYSURU%' AND year = 2013 AND disp_name_s ILIKE '%convict%'""",
        ("convict", "mysuru", "2013", "count"),
    ),
    QueryExample(
        "Cases filed vs decided 2012",
        """SELECT district_name,
       COUNT(*) AS total,
       SUM(CASE WHEN date_of_decision IS NOT NULL THEN 1 ELSE 0 END) AS decided
FROM cases WHERE year = 2012
GROUP BY district_name ORDER BY total DESC LIMIT 10""",
        ("filing", "decision", "2012", "court"),
    ),
    QueryExample(
        "Bail related dispositions 2018",
        """SELECT disp_name_s, COUNT(*) AS count
FROM cases
WHERE year = 2018 AND disp_name_s ILIKE '%bail%'
GROUP BY disp_name_s ORDER BY count DESC""",
        ("bail", "disposition", "2018"),
    ),
    QueryExample(
        "Longest running cases over 1000 days",
        """SELECT district_name, type_name_s, case_duration_days, disp_name_s
FROM cases
WHERE case_duration_days > 1000
ORDER BY case_duration_days DESC LIMIT 15""",
        ("duration", "long", "pending"),
    ),
]

EXAMPLES_BY_DB: dict[str, list[QueryExample]] = {
    "ksp_crime": KSP_CRIME_EXAMPLES,
    "criminal": CRIMINAL_EXAMPLES,
    "cases": CASES_EXAMPLES,
}
