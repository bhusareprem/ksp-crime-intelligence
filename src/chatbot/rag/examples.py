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
        """SELECT d.name AS district, ch.name AS crime_type, COUNT(*) AS count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE d.name ILIKE '%Bengaluru%' AND ch.name ILIKE '%theft%' AND f.fir_year = 2024
GROUP BY d.name, ch.name ORDER BY count DESC""",
        ("theft", "bengaluru", "fir", "count", "2024", "real"),
    ),
    QueryExample(
        "Murder FIRs by district in 2023",
        """SELECT d.name AS district, COUNT(*) AS murder_firs
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE ch.name ILIKE '%murder%' AND f.fir_year = 2023
GROUP BY d.name ORDER BY murder_firs DESC LIMIT 10""",
        ("murder", "district", "2023", "fir"),
    ),
    QueryExample(
        "Crime breakdown in Gadag district",
        """SELECT ch.name AS crime_type, COUNT(*) AS fir_count,
       SUM(f.accused_count) AS total_accused, SUM(f.arrested_count) AS total_arrested
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE d.name ILIKE '%Gadag%'
GROUP BY ch.name ORDER BY fir_count DESC LIMIT 10""",
        ("gadag", "district", "crime", "overview", "breakdown"),
    ),
    QueryExample(
        "Top repeat offender profiles in Bagalkot",
        """SELECT village_area_name, primary_crime_head, total_firs,
       repeat_offender_score, risk_level
FROM criminal_profiles
WHERE district_name ILIKE '%Bagalkot%'
ORDER BY repeat_offender_score DESC, total_firs DESC LIMIT 10""",
        ("repeat", "offender", "profile", "bagalkot", "risk"),
    ),
    QueryExample(
        "How many POCSO cases in each district?",
        """SELECT d.name AS district, COUNT(*) AS pocso_cases
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE ch.name ILIKE '%POCSO%'
GROUP BY d.name ORDER BY pocso_cases DESC""",
        ("pocso", "district", "count", "each district", "child"),
    ),
    QueryExample(
        "POCSO case details for each FIR",
        """SELECT f.fir_id, d.name AS district, f.fir_year, f.fir_month, f.fir_stage,
       f.village_area_name, f.place_of_offence, f.accused_count, f.arrested_count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE ch.name ILIKE '%POCSO%'
ORDER BY d.name, f.fir_year DESC""",
        ("pocso", "details", "fir", "each case", "individual"),
    ),
    QueryExample(
        "Arrest rate for robberies 2024",
        """SELECT d.name, COUNT(*) AS fir_count,
       SUM(f.arrested_count) AS arrests,
       ROUND(SUM(f.arrested_count)*100.0/COUNT(*), 1) AS arrest_pct
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE ch.name ILIKE '%robbery%' AND f.fir_year = 2024
GROUP BY d.name ORDER BY fir_count DESC LIMIT 10""",
        ("robbery", "arrest", "2024", "rate"),
    ),
    QueryExample(
        "Accused count by district 2022",
        """SELECT d.name, SUM(f.accused_count) AS total_accused, COUNT(*) AS fir_count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
WHERE f.fir_year = 2022
GROUP BY d.name ORDER BY total_accused DESC LIMIT 10""",
        ("accused", "district", "2022", "count"),
    ),
    QueryExample(
        "Cyber crime FIRs in Dakshina Kannada 2023",
        """SELECT ch.name, COUNT(*) AS count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE d.name ILIKE '%Dakshina Kannada%' AND ch.name ILIKE '%cyber%' AND f.fir_year = 2023
GROUP BY ch.name ORDER BY count DESC""",
        ("cyber", "fir", "2023", "district"),
    ),
    QueryExample(
        "Top crime types statewide 2024",
        """SELECT ch.name AS crime_type, COUNT(*) AS count
FROM fir_details f
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE f.fir_year = 2024
GROUP BY ch.name ORDER BY count DESC LIMIT 10""",
        ("top", "crime", "2024", "statewide"),
    ),
    QueryExample(
        "FIR stage distribution in Hassan",
        """SELECT f.fir_stage, COUNT(*) AS count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
WHERE d.name ILIKE '%Hassan%'
GROUP BY f.fir_stage ORDER BY count DESC""",
        ("fir", "stage", "hassan", "investigation"),
    ),
    QueryExample(
        "Co-accused network size by district",
        """SELECT d.name, COUNT(DISTINCT c.link_id) AS co_links
FROM co_accused_links c
JOIN fir_details f ON c.fir_id = f.fir_id
JOIN districts d ON f.district_id = d.district_id
GROUP BY d.name ORDER BY co_links DESC LIMIT 10""",
        ("network", "co-accused", "district"),
    ),
    QueryExample(
        "Recent theft cases Mandya 2024",
        """SELECT f.fir_id, ch.name, f.fir_year, f.village_area_name, f.accused_count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE d.name ILIKE '%Mandya%' AND ch.name ILIKE '%theft%' AND f.fir_year = 2024
ORDER BY f.fir_id DESC LIMIT 20""",
        ("theft", "recent", "mandya", "2024", "cases"),
    ),
    QueryExample(
        "Victim counts by crime head Belagavi",
        """SELECT ch.name, SUM(f.victim_count) AS victims, COUNT(*) AS firs
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
JOIN crime_heads ch ON f.crime_head_id = ch.head_id
WHERE d.name ILIKE '%Belagavi%'
GROUP BY ch.name ORDER BY victims DESC LIMIT 10""",
        ("victim", "belagavi", "crime"),
    ),
    QueryExample(
        "Chargesheeted vs pending in Shivamogga",
        """SELECT f.fir_stage,
       SUM(f.chargesheeted_count) AS chargesheeted,
       COUNT(*) AS total_firs
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
WHERE d.name ILIKE '%Shivamogga%'
GROUP BY f.fir_stage""",
        ("chargesheet", "pending", "shivamogga"),
    ),
    QueryExample(
        "Highest risk behavioral profiles statewide",
        """SELECT district_name, village_area_name, primary_crime_head,
       repeat_offender_score, risk_level, total_firs
FROM criminal_profiles
WHERE risk_level = 'critical'
ORDER BY repeat_offender_score DESC LIMIT 15""",
        ("risk", "profile", "critical", "repeat"),
    ),
    QueryExample(
        "Monthly FIR trend Mysuru 2023",
        """SELECT f.fir_month, COUNT(*) AS fir_count
FROM fir_details f
JOIN districts d ON f.district_id = d.district_id
WHERE d.name ILIKE '%Mysuru%' AND f.fir_year = 2023
GROUP BY f.fir_month ORDER BY f.fir_month""",
        ("trend", "monthly", "mysuru", "2023"),
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
