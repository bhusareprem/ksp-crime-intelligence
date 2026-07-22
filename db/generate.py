#!/usr/bin/env python3
"""
KSP Synthetic FIR Database Generator  —  fast vectorised edition
Schema : Police_FIR_ER_Diagram.pdf
Scale  : 906 stations · 32 districts · 7 ranges · 500 000 FIRs
Output : data/ksp_fir.duckdb

Run:
    python db/generate.py             # 500 000 FIRs (~3-5 min)
    python db/generate.py --firs 50000   # quick smoke-test
"""
import argparse, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ── CLI ───────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--firs", type=int, default=500_000)
ap.add_argument("--out",  default="data/ksp_fir.duckdb")
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

N  = args.firs
OUT = Path(args.out)
RNG = np.random.default_rng(args.seed)

OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists(): OUT.unlink()

T0 = time.time()
def elapsed(): return f"{time.time()-T0:.1f}s"
def log(msg): print(f"  [{elapsed():>6}] {msg}", flush=True)

print(f"\nKSP Generator  {N:,} FIRs  ->  {OUT}\n")

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  STATIC LOOKUP ARRAYS
# ═══════════════════════════════════════════════════════════════════════════════
FIRST = np.array([
    "Ravi","Suresh","Ramesh","Mahesh","Ganesh","Rajesh","Srinivas","Venkatesh",
    "Manjunath","Nagaraj","Prasad","Kumar","Girish","Prakash","Raghu","Santosh",
    "Naveen","Vikram","Arun","Mohan","Lokesh","Praveen","Harish","Deepak",
    "Kavitha","Priya","Suma","Geetha","Rekha","Savitha","Usha","Latha",
    "Nandini","Shobha","Anitha","Meena","Vijaya","Pushpa","Radha","Sunita",
    "Mohammed","Abdul","Imran","Farhan","Ayesha","Fatima","Amina","Rashid",
    "John","Peter","Maria","Joseph","Anthony","David","Mary","Thomas",
    "Basavraj","Siddaramaiah","Ningappa","Veeranna","Puttanna","Hanumantha",
    "Rangaiah","Thimmaiah","Boraiah","Channaiah","Doddanna","Eranna",
    "Muniraj","Shivaraj","Vasanth","Yashwanth","Karim","Altaf","Zaheeda",
])
LAST = np.array([
    "Gowda","Reddy","Naik","Rao","Shetty","Nayak","Hegde","Joshi","Murthy",
    "Swamy","Patil","Kulkarni","Desai","Kamat","Bhat","Prabhu","Salian",
    "Thimmaiah","Krishnappa","Venkatarao","Raghavendra","Anantharamu",
    "Khan","Shaikh","Siddiqui","Patel","Ali","Begum","Mirza","Ahmad",
    "D'Souza","Fernandez","Pinto","Rodrigues","Pereira","Lobo","Dias",
    "Rathod","Lamani","Bandi","Vaddar","Nayaka","Koravar",
    "Lingaiah","Muniswamy","Papaiah","Narasimhaiah",
])

def names(n):
    """Fast vectorised name generator — no Faker, pure numpy."""
    f = FIRST[RNG.integers(0, len(FIRST), n)]
    l = LAST[RNG.integers(0, len(LAST), n)]
    return np.char.add(np.char.add(f, " "), l)

KARNATAKA_STATE_ID = 29

# ── Geography ─────────────────────────────────────────────────────────────────
# dist_name, dist_id, range, n_stations, pop, lat, lng
GEO = [
    ("Bengaluru Urban",   1,"Bengaluru City",   185,9621551,12.9716,77.5946),
    ("Bengaluru Rural",   2,"Bengaluru Rural",   28, 990923,13.1986,77.7066),
    ("Mysuru",            3,"Mysuru",            42,3001127,12.2958,76.6394),
    ("Belagavi",          4,"Belagavi",          52,4779661,15.8497,74.4977),
    ("Dakshina Kannada",  5,"Mangaluru",         36,2083625,12.8698,74.8431),
    ("Ballari",           6,"Kalaburagi",        34,2531592,15.1394,76.9214),
    ("Kalaburagi",        7,"Kalaburagi",        34,2564892,17.3297,76.8343),
    ("Shivamogga",        8,"Shivamogga",        33,1752753,13.9299,75.5681),
    ("Tumakuru",          9,"Bengaluru Rural",   40,2678980,13.3409,77.1010),
    ("Dharwad",          10,"Belagavi",          30,1847023,15.4589,75.0078),
    ("Vijayapura",       11,"Belagavi",          32,2175102,16.8302,75.7100),
    ("Kolar",            12,"Bengaluru Rural",   26,1540231,13.1349,78.1320),
    ("Chitradurga",      13,"Shivamogga",        27,1659456,14.2226,76.4019),
    ("Hassan",           14,"Mysuru",            30,1776421,13.0068,76.1003),
    ("Mandya",           15,"Mysuru",            25,1895673,12.5218,76.8951),
    ("Raichur",          16,"Kalaburagi",        26,1924773,16.2076,77.3463),
    ("Yadgir",           17,"Kalaburagi",        19,1172985,16.7710,77.1384),
    ("Bidar",            18,"Kalaburagi",        24,1700018,17.9133,77.5199),
    ("Haveri",           19,"Shivamogga",        22,1598506,14.7959,75.3998),
    ("Chikkamagaluru",   20,"Mysuru",            24,1137753,13.3153,75.7754),
    ("Kodagu",           21,"Mysuru",            14, 554762,12.3375,75.8069),
    ("Gadag",            22,"Belagavi",          16,1065235,15.4166,75.6294),
    ("Koppal",           23,"Kalaburagi",        18,1391001,15.3499,76.1547),
    ("Bagalkot",         24,"Belagavi",          26,1890826,16.1691,75.6965),
    ("Chamarajanagara",  25,"Mysuru",            14,1020791,11.9261,76.9434),
    ("Ramanagara",       26,"Bengaluru Rural",   18,1082739,12.7157,77.2827),
    ("Chikkaballapur",   27,"Bengaluru Rural",   18,1255104,13.4355,77.7315),
    ("Udupi",            28,"Mangaluru",         21,1177908,13.3409,74.7421),
    ("Uttara Kannada",   29,"Belagavi",          22,1374947,14.7862,74.6941),
    ("Davanagere",       30,"Shivamogga",        26,1946905,14.4644,75.9218),
    ("Vijayanagara",     31,"Kalaburagi",        20,1085000,15.1736,76.4600),
]

# derive arrays from GEO
DIST_NAMES   = [g[0] for g in GEO]
DIST_IDS     = np.array([g[1] for g in GEO])
DIST_RANGES  = [g[2] for g in GEO]
DIST_STN_CNT = np.array([g[3] for g in GEO])
DIST_POP     = np.array([g[4] for g in GEO], dtype=float)
DIST_LAT     = np.array([g[5] for g in GEO])
DIST_LNG     = np.array([g[6] for g in GEO])
DIST_PROB    = DIST_POP / DIST_POP.sum()

# ── Crime taxonomy ─────────────────────────────────────────────────────────────
# (sub_head_id, major_head_id, name, motive, weight, heinous)
CRIME = [
    (101,1,"Murder",None,2.0,True),(102,1,"Attempt to Murder",None,1.0,True),
    (104,1,"Grievous Hurt",None,2.5,False),(105,1,"Simple Hurt/Assault",None,5.0,False),
    (107,1,"Kidnapping & Abduction",None,1.0,True),
    (201,2,"Theft",None,20.0,False),(202,2,"Burglary",None,5.0,False),
    (203,2,"Robbery",None,3.0,True),(206,2,"Vehicle Theft",None,5.0,False),
    (207,2,"Snatching",None,2.0,False),
    (301,3,"Rape","gender",1.5,True),(302,3,"Sexual Harassment","gender",2.0,False),
    (305,3,"Cruelty by Husband","gender",3.0,False),(306,3,"Stalking","gender",1.5,False),
    (304,3,"Dowry Death","gender",0.8,True),
    (401,4,"POCSO Act Offences",None,1.5,True),
    (601,6,"Cheating & Fraud","economic",8.0,False),(603,6,"Forgery","economic",2.0,False),
    (701,7,"Cyber Crime - Online Fraud","economic",4.0,False),
    (702,7,"Cyber Crime - Hacking","economic",1.0,False),
    (703,7,"Social Media Abuse","gender",2.0,False),
    (801,8,"NDPS - Possession",None,3.0,False),(802,8,"NDPS - Trafficking",None,1.5,True),
    (901,9,"Atrocities Against SC","caste",2.0,True),
    (902,9,"Atrocities Against ST","caste",1.0,True),
    (1001,10,"Communal Riot","communal",0.5,True),
    (1002,10,"Religious Hate Crime","communal",0.3,True),
    (1003,10,"Caste Violence","caste",0.4,True),
    (1101,11,"Road Accident - Fatal",None,3.0,True),
    (1102,11,"Road Accident - Non Fatal",None,5.0,False),
    (1201,12,"Missing Person",None,4.0,False),(1202,12,"Unnatural Death",None,2.0,False),
    (1301,13,"Trespass/House Breaking",None,3.0,False),
    (1302,13,"Property Damage",None,2.0,False),
    (1401,14,"Unlawful Assembly",None,1.0,False),(1402,14,"Rioting","communal",1.0,False),
    (1501,15,"Abetment to Suicide",None,1.5,True),(1503,15,"Other IPC",None,5.0,False),
]
CRIME_IDS     = np.array([c[0] for c in CRIME])
CRIME_MAJOR   = np.array([c[1] for c in CRIME])
CRIME_MOTIVE  = np.array([c[3] for c in CRIME])
CRIME_HEINOUS = np.array([c[5] for c in CRIME], dtype=bool)
raw_w = np.array([c[4] for c in CRIME], dtype=float)
CRIME_PROB    = raw_w / raw_w.sum()

# act/section per crime sub-head (just first two)
CRIME_ACT_SEC = {
    101:[("IPC","302"),("BNS","103")], 102:[("IPC","307"),("BNS","109")],
    104:[("IPC","326"),("BNS","118")], 105:[("IPC","323"),("BNS","115")],
    107:[("IPC","363"),("BNS","140")], 201:[("IPC","379"),("BNS","303")],
    202:[("IPC","380"),("BNS","303")], 203:[("IPC","392"),("BNS","309")],
    206:[("IPC","379"),("BNS","303")], 207:[("IPC","379"),("BNS","303")],
    301:[("IPC","376"),("BNS","64")],  302:[("IPC","354A"),("BNS","63")],
    305:[("IPC","498A"),("BNS","85")], 306:[("IPC","354D"),("BNS","79")],
    304:[("IPC","304B"),("BNS","68")], 401:[("POCSO","4"),("POCSO","8")],
    601:[("IPC","420"),("BNS","318")], 603:[("IPC","465"),("BNS","336")],
    701:[("ITA","66D"),("ITA","66C")], 702:[("ITA","66"),("ITA","43")],
    703:[("ITA","67"),("IPC","509")],  801:[("NDPS","27"),("NDPS","20")],
    802:[("NDPS","21"),("NDPS","29")], 901:[("SCST","3(1)"),("SCST","3")],
    902:[("SCST","3(1)"),("SCST","3")],
    1001:[("IPC","153A"),("BNS","196")], 1002:[("IPC","295A"),("BNS","299")],
    1003:[("SCST","3"),("IPC","153A")],  1101:[("IPC","304A"),("MV","184")],
    1102:[("IPC","337"),("MV","184")],   1201:[("IPC","364"),("KPE","41")],
    1202:[("IPC","174A"),("IPC","304")], 1301:[("IPC","447"),("IPC","454")],
    1302:[("IPC","425"),("IPC","427")],  1401:[("IPC","141"),("BNS","191")],
    1402:[("IPC","147"),("BNS","222")],  1501:[("IPC","306"),("BNS","108")],
    1503:[("IPC","509"),("KPE","44")],
}

# ═══════════════════════════════════════════════════════════════════════════════
# 2.  OPEN DB + CREATE SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════
log("Opening DuckDB and creating schema")
con = duckdb.connect(str(OUT))
schema_path = Path(__file__).parent / "schema.sql"
con.execute(schema_path.read_text())

# ═══════════════════════════════════════════════════════════════════════════════
# 3.  REFERENCE / LOOKUP TABLES  (tiny, insert directly)
# ═══════════════════════════════════════════════════════════════════════════════
log("Inserting reference data")

STATES = [(KARNATAKA_STATE_ID,"Karnataka",1,True),
          (1,"Andhra Pradesh",1,True),(2,"Telangana",1,True),
          (3,"Tamil Nadu",1,True),(4,"Kerala",1,True),
          (5,"Goa",1,True),(6,"Maharashtra",1,True)]
con.executemany("INSERT INTO State VALUES (?,?,?,?)", STATES)

UNIT_TYPES = [
    (1,"State Police HQ","State",1,True),(2,"Range Office","State",2,True),
    (3,"District Police Office","District",3,True),(4,"Circle Inspector Office","District",4,True),
    (5,"Police Station","District",5,True),(6,"Police Outpost","District",6,True),
    (7,"Railway Police Station","District",5,True),(8,"Traffic Police Station","District",5,True),
]
con.executemany("INSERT INTO UnitType VALUES (?,?,?,?,?)", UNIT_TYPES)

RANKS = [
    (1,"Director General of Police",1,True),(2,"Additional DGP",2,True),
    (3,"Inspector General",3,True),(4,"Deputy Inspector General",4,True),
    (5,"Superintendent of Police",5,True),(6,"Additional SP",6,True),
    (7,"Deputy Superintendent of Police",7,True),(8,"Police Inspector",8,True),
    (9,"Police Sub-Inspector",9,True),(10,"Assistant Sub-Inspector",10,True),
    (11,"Head Constable",11,True),(12,"Constable",12,True),(13,"Lady Constable",12,True),
]
con.executemany("INSERT INTO Rank VALUES (?,?,?,?)", RANKS)

DESIGNATIONS = [
    (1,"Station House Officer",True,1),(2,"Investigating Officer",True,2),
    (3,"Circle Inspector",True,3),(4,"Writer",True,4),(5,"Beat Officer",True,5),
    (6,"Traffic Officer",True,6),(7,"Crime Branch Officer",True,7),
]
con.executemany("INSERT INTO Designation VALUES (?,?,?,?)", DESIGNATIONS)

con.executemany("INSERT INTO CaseCategory VALUES (?,?,?)", [
    (1,"FIR","1"),(2,"UDR","3"),(3,"PAR","4"),(4,"Zero FIR","8"),(5,"NC","5"),
])
con.executemany("INSERT INTO GravityOffence VALUES (?,?)", [
    (1,"Heinous"),(2,"Non-Heinous"),
])
con.executemany("INSERT INTO CaseStatusMaster VALUES (?,?)", [
    (1,"Registered"),(2,"Under Investigation"),(3,"Charge Sheeted"),
    (4,"Final Report Filed"),(5,"Referred to Court"),(6,"Closed/Disposed"),(7,"Pending"),
])
con.executemany("INSERT INTO ReligionMaster VALUES (?,?)", [
    (1,"Hindu"),(2,"Muslim"),(3,"Christian"),(4,"Jain"),(5,"Buddhist"),(6,"Sikh"),(7,"Others"),
])
con.executemany("INSERT INTO CasteMaster VALUES (?,?)", [
    (1,"SC"),(2,"ST"),(3,"OBC"),(4,"General/Others"),
])
OCCS = [(i,o) for i,o in enumerate([
    "Student","Farmer","Daily Wage Labourer","Private Employee","Government Employee",
    "Business/Self Employed","Driver","Auto/Taxi Driver","Housewife","Unemployed",
    "Police","Teacher","Doctor/Medical","Mechanic","Contractor","Petty Shop Owner",
    "Vendor/Hawker","Retired",
],1)]
con.executemany("INSERT INTO OccupationMaster VALUES (?,?)", OCCS)

CRIME_HEAD_ROWS = [
    (1,"Crimes Against Body",True),(2,"Crimes Against Property",True),
    (3,"Crimes Against Women",True),(4,"Crimes Against Children",True),
    (5,"Crimes Against State",True),(6,"Economic Offences",True),
    (7,"Cyber Crimes",True),(8,"Narcotics/NDPS",True),
    (9,"SC/ST Atrocities",True),(10,"Communal & Riots",True),
    (11,"Road Accidents",True),(12,"Missing Persons/UDR",True),
    (13,"Property Offences",True),(14,"Public Order",True),(15,"Other IPC",True),
]
con.executemany("INSERT INTO CrimeHead VALUES (?,?,?)", CRIME_HEAD_ROWS)

for c in CRIME:
    con.execute("INSERT INTO CrimeSubHead VALUES (?,?,?,?,?,?)",
        (c[0], c[1], c[2], c[0], c[3], True))

ACTS = {
    "BNS":("Bharatiya Nyaya Sanhita 2023","BNS"),
    "IPC":("Indian Penal Code 1860","IPC"),
    "NDPS":("Narcotic Drugs and Psychotropic Substances Act 1985","NDPS"),
    "ITA":("Information Technology Act 2000","IT Act"),
    "SCST":("SC/ST (Prevention of Atrocities) Act 1989","SC/ST Act"),
    "POCSO":("Protection of Children from Sexual Offences Act 2012","POCSO"),
    "KPE":("Karnataka Police Act 1963","KP Act"),
    "MV":("Motor Vehicles Act 1988","MV Act"),
}
for code,(desc,short) in ACTS.items():
    con.execute("INSERT INTO Act VALUES (?,?,?,?)",(code,desc,short,True))

SECTIONS = [
    ("BNS","103","Murder"),("BNS","109","Attempt to Murder"),("BNS","115","Hurt"),
    ("BNS","118","Grievous Hurt"),("BNS","140","Kidnapping"),("BNS","303","Theft"),
    ("BNS","309","Robbery"),("BNS","318","Cheating"),("BNS","336","Forgery"),
    ("BNS","64","Rape"),("BNS","63","Sexual Harassment"),("BNS","85","Cruelty by Husband"),
    ("BNS","68","Dowry Death"),("BNS","79","Stalking"),("BNS","108","Abetment to Suicide"),
    ("BNS","191","Unlawful Assembly"),("BNS","196","Promoting Enmity"),
    ("BNS","222","Rioting"),("BNS","299","Hurting Religious Feelings"),
    ("IPC","302","Murder"),("IPC","307","Attempt to Murder"),("IPC","323","Hurt"),
    ("IPC","324","Hurt Dangerous Weapon"),("IPC","326","Grievous Hurt"),
    ("IPC","363","Kidnapping"),("IPC","354A","Sexual Harassment"),("IPC","376","Rape"),
    ("IPC","379","Theft"),("IPC","380","Theft in Dwelling"),("IPC","392","Robbery"),
    ("IPC","395","Dacoity"),("IPC","420","Cheating"),("IPC","406","Criminal Breach of Trust"),
    ("IPC","498A","Cruelty by Husband"),("IPC","304B","Dowry Death"),
    ("IPC","354D","Stalking"),("IPC","465","Forgery"),("IPC","447","Criminal Trespass"),
    ("IPC","454","House Breaking"),("IPC","425","Mischief"),("IPC","427","Property Damage"),
    ("IPC","141","Unlawful Assembly"),("IPC","147","Rioting"),("IPC","153A","Promoting Enmity"),
    ("IPC","295A","Hurting Religious Feelings"),("IPC","304A","Causing Death by Negligence"),
    ("IPC","306","Abetment to Suicide"),("IPC","337","Hurt by Negligent Act"),
    ("IPC","364","Kidnapping for Ransom"),("IPC","174A","Non-Appearance"),
    ("IPC","383","Extortion"),("IPC","384","Extortion"),("IPC","509","Insult to Modesty"),
    ("NDPS","8","Prohibition"),("NDPS","20","Cannabis"),("NDPS","21","Heroin"),
    ("NDPS","27","Punishment"),("NDPS","29","Abetment"),
    ("ITA","43","Damage to Computer"),("ITA","66","Computer Offences"),
    ("ITA","66C","Identity Theft"),("ITA","66D","Cheating by Personation"),
    ("ITA","67","Publishing Obscene Material"),
    ("SCST","3","Atrocity Offences"),("SCST","3(1)","Atrocity Offences - 3(1)"),
    ("POCSO","4","Penetrative Sexual Assault Punishment"),("POCSO","8","Sexual Assault Punishment"),
    ("KPE","41","Nuisance"),("KPE","44","Public Obscenity"),
    ("MV","184","Dangerous Driving"),("MV","185","Drunken Driving"),
    ("MV","187","Failure to Report Accident"),
]
con.executemany("INSERT INTO Section VALUES (?,?,?,?)",
    [(a,s,d,True) for a,s,d in SECTIONS])

# ═══════════════════════════════════════════════════════════════════════════════
# 4.  GEOGRAPHY — Districts, Units (Range HQ, District HQ, 906 Stations), Courts
# ═══════════════════════════════════════════════════════════════════════════════
log("Building geography (districts + 906+ stations + courts)")

# Districts
dist_df = pd.DataFrame({
    "DistrictID": [g[1] for g in GEO],
    "DistrictName": [g[0] for g in GEO],
    "StateID": KARNATAKA_STATE_ID,
    "Latitude": [g[5] for g in GEO],
    "Longitude": [g[6] for g in GEO],
    "Population": [g[4] for g in GEO],
    "Active": True,
})
con.execute("INSERT INTO District SELECT * FROM dist_df")

# Unique ranges
RANGES = list(dict.fromkeys(DIST_RANGES))  # ordered unique
range_ids = {}
unit_rows = []
uid = 10001
for rng in RANGES:
    # find a district in this range for lat/lng
    gi = next(i for i,g in enumerate(GEO) if g[2]==rng)
    range_ids[rng] = uid
    unit_rows.append((uid, f"{rng} Range Police Office", 2, None,
                      KARNATAKA_STATE_ID, GEO[gi][1],
                      GEO[gi][5], GEO[gi][6], True))
    uid += 1

# District HQs + Stations
ALL_STATIONS = []   # (unit_id, dist_idx, lat, lng)
station_by_dist = {}  # dist_id -> list of unit_ids
dhq_ids = {}

for gi, g in enumerate(GEO):
    dname, dist_id, rng, n_stns, pop, dlat, dlng = g
    parent_range = range_ids.get(rng)

    # District HQ
    dhq_ids[dist_id] = uid
    unit_rows.append((uid, f"{dname} District Police Office", 3, parent_range,
                      KARNATAKA_STATE_ID, dist_id,
                      dlat + RNG.uniform(-0.02, 0.02),
                      dlng + RNG.uniform(-0.02, 0.02), True))
    dhq_uid = uid; uid += 1

    # Stations
    stns_here = []
    for s in range(n_stns):
        is_rly = (s == n_stns - 1)
        is_trf = (s == n_stns - 2) and n_stns > 3
        utype  = 7 if is_rly else (8 if is_trf else 5)
        suffix = "Railway PS" if is_rly else ("Traffic PS" if is_trf else f"Police Station {s+1}")
        slat = dlat + RNG.uniform(-0.3, 0.3)
        slng = dlng + RNG.uniform(-0.3, 0.3)
        unit_rows.append((uid, f"{dname} {suffix}", utype, dhq_uid,
                          KARNATAKA_STATE_ID, dist_id, slat, slng, True))
        stns_here.append((uid, gi, slat, slng))
        ALL_STATIONS.append((uid, gi, slat, slng))
        uid += 1

    station_by_dist[dist_id] = [s[0] for s in stns_here]

unit_df = pd.DataFrame(unit_rows,
    columns=["UnitID","UnitName","TypeID","ParentUnit","StateID",
             "DistrictID","Latitude","Longitude","Active"])
# Self-referential FK: must insert parents before children
ranges_df = unit_df[unit_df["ParentUnit"].isna()]
dhq_df    = unit_df[unit_df["TypeID"] == 3]
stns_df   = unit_df[unit_df["TypeID"].isin([5, 6, 7, 8])]
for _df in (ranges_df, dhq_df, stns_df):
    con.register("_unit_batch", _df.reset_index(drop=True))
    con.execute("INSERT INTO Unit SELECT * FROM _unit_batch")

# Courts — 3 per district
court_rows = []
court_id = 1
court_by_dist = {}
for g in GEO:
    dname, dist_id = g[0], g[1]
    court_by_dist[dist_id] = []
    for cname in [f"Principal District & Sessions Court {dname}",
                  f"JMFC Court {dname}", f"Fast Track Court {dname}"]:
        court_rows.append((court_id, cname, dist_id, KARNATAKA_STATE_ID, True))
        court_by_dist[dist_id].append(court_id)
        court_id += 1
court_df = pd.DataFrame(court_rows, columns=["CourtID","CourtName","DistrictID","StateID","Active"])
con.execute("INSERT INTO Court SELECT * FROM court_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 5.  EMPLOYEES  (~9 000 officers across 906 stations)
# ═══════════════════════════════════════════════════════════════════════════════
log("Generating employees")

N_STATIONS = len(ALL_STATIONS)
# Each station: 1 SHO(rank8) + 2 SI(rank9) + 2 HC(rank11) + 3 Constable(rank12) = 8
EMP_PER_STN = 8
N_EMP = N_STATIONS * EMP_PER_STN

stn_unit_ids = np.array([s[0] for s in ALL_STATIONS])
stn_dist_idx = np.array([s[1] for s in ALL_STATIONS])

# Tile station assignments
stn_tile  = np.repeat(np.arange(N_STATIONS), EMP_PER_STN)
unit_arr  = stn_unit_ids[stn_tile]
dist_arr  = DIST_IDS[stn_dist_idx[stn_tile]]

# Ranks by slot: slot 0=SHO, 1-2=SI, 3-4=HC, 5-7=Const
slot = np.tile(np.arange(EMP_PER_STN), N_STATIONS)
rank_map = np.array([8,9,9,11,11,12,12,13])
desg_map = np.array([1,2,2,4,4,5,5,5])
rank_arr = rank_map[slot]
desg_arr = desg_map[slot]

gender_arr = np.where(rank_arr == 13, 2, RNG.choice([1,2], N_EMP, p=[0.88,0.12]))

birth_low  = np.datetime64("1970-01-01")
birth_high = np.datetime64("2000-01-01")
dob_range  = (birth_high - birth_low).astype(int)
dob_arr    = birth_low + RNG.integers(0, dob_range, N_EMP).astype("timedelta64[D]")

appt_low   = np.datetime64("2000-01-01")
appt_high  = np.datetime64("2023-01-01")
appt_range = (appt_high - appt_low).astype(int)
appt_arr   = appt_low + RNG.integers(0, appt_range, N_EMP).astype("timedelta64[D]")

kgid_arr   = np.array([f"KG{i+1:07d}" for i in range(N_EMP)])
fname_arr  = FIRST[RNG.integers(0, len(FIRST), N_EMP)]
lname_arr  = LAST[RNG.integers(0, len(LAST), N_EMP)]

emp_df = pd.DataFrame({
    "EmployeeID": np.arange(1, N_EMP+1),
    "DistrictID": dist_arr,
    "UnitID": unit_arr,
    "RankID": rank_arr,
    "DesignationID": desg_arr,
    "KGID": kgid_arr,
    "FirstName": fname_arr,
    "LastName": lname_arr,
    "EmployeeDOB": pd.to_datetime(dob_arr),
    "GenderID": gender_arr,
    "BloodGroupID": RNG.integers(1, 9, N_EMP),
    "PhysicallyChallenged": False,
    "AppointmentDate": pd.to_datetime(appt_arr),
    "Active": True,
})
con.execute("INSERT INTO Employee SELECT * FROM emp_df")
N_EMP_ACTUAL = len(emp_df)

# Build station -> IO employee ID mapping (employees with DesignationID=2)
io_mask = emp_df["DesignationID"] == 2
io_emp = emp_df[io_mask][["EmployeeID","UnitID"]].copy()
io_by_unit = io_emp.groupby("UnitID")["EmployeeID"].apply(list).to_dict()

log(f"{N_EMP_ACTUAL:,} employees across {N_STATIONS} stations")

# ═══════════════════════════════════════════════════════════════════════════════
# 6.  CRIME GANGS
# ═══════════════════════════════════════════════════════════════════════════════
log("Creating crime gangs")
GANGS = [
    ("Bengaluru ATM Fraud Gang","cyber_fraud"),("Kalaburagi Narcotics Ring","narcotics"),
    ("Mysuru Gold Theft Gang","theft"),("Belagavi Extortion Syndicate","extortion"),
    ("Mangaluru Rowdy Network","assault"),("Ballari Mining Fraud Gang","economic_fraud"),
    ("Bengaluru Cyber Fraud Ring","cyber_fraud"),("Tumakuru Vehicle Theft Gang","vehicle_theft"),
    ("Dharwad Burglary Network","burglary"),("Raichur Sand Mafia","illegal_mining"),
    ("Hassan Kidnapping Gang","kidnapping"),("Shivamogga Drug Network","narcotics"),
    ("Udupi Hawala Network","economic_fraud"),("Vijayapura Robbery Gang","robbery"),
    ("Kolar Cattle Theft Ring","theft"),("Bidar Caste Violence Gang","organized_crime"),
]
gang_df = pd.DataFrame({
    "GangID": range(1, len(GANGS)+1),
    "GangName": [g[0] for g in GANGS],
    "Specialization": [g[1] for g in GANGS],
    "ActiveSince": RNG.integers(2010, 2021, len(GANGS)),
    "HomeDistrictID": RNG.choice(DIST_IDS, len(GANGS)),
    "Active": True,
})
con.execute("INSERT INTO CrimeGang SELECT * FROM gang_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 7.  FIRs — fully vectorised
# ═══════════════════════════════════════════════════════════════════════════════
log(f"Vectorising {N:,} FIR records")

# District & station per FIR
dist_idx   = RNG.choice(len(GEO), N, p=DIST_PROB)       # index into GEO
dist_ids_f = DIST_IDS[dist_idx]

# For each FIR pick a random station from its district
# Build a flat station lookup: dist_id -> array of unit_ids
dist_id_to_stns = {g[1]: np.array(station_by_dist[g[1]]) for g in GEO}
stn_ids_f = np.array([
    int(RNG.choice(dist_id_to_stns[did]))
    for did in dist_ids_f
])

# Crime
crime_idx   = RNG.choice(len(CRIME), N, p=CRIME_PROB)
csh_ids_f   = CRIME_IDS[crime_idx]
cmaj_ids_f  = CRIME_MAJOR[crime_idx]
heinous_f   = CRIME_HEINOUS[crime_idx]
grav_ids_f  = np.where(heinous_f, 1, 2)

# Dates
start_ord = pd.Timestamp("2020-01-01").value // 10**9 // 86400
end_ord   = pd.Timestamp("2024-12-31").value // 10**9 // 86400
reg_ord   = RNG.integers(start_ord, end_ord+1, N)
reg_dates = pd.to_datetime(reg_ord, unit="D")

# Category: 82% FIR, 8% UDR, 5% PAR, 3% ZeroFIR, 2% NC
cat_ids_f = RNG.choice([1,2,3,4,5], N, p=[0.82,0.08,0.05,0.03,0.02])

# IO employee per station
stn_unique = np.unique(stn_ids_f)
stn_io_arr = np.zeros(stn_ids_f.max()+1, dtype=int)
for su in stn_unique:
    ios = io_by_unit.get(su, [])
    stn_io_arr[su] = int(RNG.choice(ios)) if ios else 0
io_ids_f = stn_io_arr[stn_ids_f]
io_ids_f = np.where(io_ids_f == 0, None, io_ids_f)

# GPS jitter around station location
stn_unit_arr = np.array([s[0] for s in ALL_STATIONS])
stn_lat_arr  = np.array([s[2] for s in ALL_STATIONS])
stn_lng_arr  = np.array([s[3] for s in ALL_STATIONS])
unit_to_idx  = {uid: i for i, uid in enumerate(stn_unit_arr)}
stn_local_idx = np.array([unit_to_idx.get(u, 0) for u in stn_ids_f])
lats_f = stn_lat_arr[stn_local_idx] + RNG.uniform(-0.05, 0.05, N)
lngs_f = stn_lng_arr[stn_local_idx] + RNG.uniform(-0.05, 0.05, N)

# Status — older cases more resolved
age_days = (pd.Timestamp("2025-01-01") - reg_dates).days
status_f = np.where(age_days > 730,
    RNG.choice([3,4,5,6], N, p=[0.3,0.2,0.2,0.3]),
    np.where(age_days > 365,
        RNG.choice([2,3,4], N, p=[0.4,0.35,0.25]),
        RNG.choice([1,2,7], N, p=[0.3,0.5,0.2])))

# Court (assigned only for resolved cases)
dist_to_courts = {g[1]: court_by_dist[g[1]] for g in GEO}
court_f = np.array([
    int(RNG.choice(dist_to_courts[did])) if status_f[i] in [3,4,5,6] else None
    for i, did in enumerate(dist_ids_f)
], dtype=object)

# CrimeNo: catcode + distid + stnid(last4) + year + serial
cat_codes = np.array(["1","3","4","8","5"])
cat_code_f = cat_codes[cat_ids_f - 1]
years_f    = reg_dates.year.values
# serial per (station, year, catcode) — vectorised counter
serial_keys = list(zip(stn_ids_f, years_f, cat_code_f))
serial_counter = {}
serials_f = np.zeros(N, dtype=int)
for i, k in enumerate(serial_keys):
    serial_counter[k] = serial_counter.get(k, 0) + 1
    serials_f[i] = serial_counter[k]

crime_nos = np.array([
    f"{cat_code_f[i]}{dist_ids_f[i]:04d}{stn_ids_f[i]%9999:04d}{years_f[i]}{serials_f[i]:05d}"
    for i in range(N)
])
case_nos  = np.array([f"{years_f[i]}{serials_f[i]:05d}" for i in range(N)])

log("Writing CaseMaster")
fir_df = pd.DataFrame({
    "CaseMasterID":        np.arange(1, N+1),
    "CrimeNo":             crime_nos,
    "CaseNo":              case_nos,
    "CrimeRegisteredDate": reg_dates.date,
    "PolicePersonID":      io_ids_f,
    "PoliceStationID":     stn_ids_f,
    "CaseCategoryID":      cat_ids_f,
    "GravityOffenceID":    grav_ids_f,
    "CrimeMajorHeadID":    cmaj_ids_f,
    "CrimeMinorHeadID":    csh_ids_f,
    "CaseStatusID":        status_f,
    "CourtID":             court_f,
    "IncidentFromDate":    reg_dates - pd.to_timedelta(RNG.integers(0,4,N), unit="D"),
    "IncidentToDate":      reg_dates,
    "InfoReceivedPSDate":  reg_dates,
    "Latitude":            lats_f.round(6),
    "Longitude":           lngs_f.round(6),
    "BriefFacts":          None,
})
con.execute("INSERT INTO CaseMaster SELECT * FROM fir_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 8.  COMPLAINANTS  (1 per FIR, 10% chance of 2)
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing ComplainantDetails")
extra_mask = RNG.random(N) < 0.10
n_comp = N + extra_mask.sum()

case_ids_c  = np.concatenate([np.arange(1,N+1), np.arange(1,N+1)[extra_mask]])
relig_p = [0.84,0.13,0.02,0.005,0.003,0.001,0.001]
caste_p = [0.17,0.07,0.45,0.31]
occ_ids = [o[0] for o in OCCS]
occ_p   = [0.12,0.15,0.18,0.14,0.06,0.08,0.04,0.04,0.07,0.06,0.01,0.02,0.01,0.02,0.01,0.02,0.02,0.015]
occ_p   = np.array(occ_p); occ_p /= occ_p.sum()

comp_df = pd.DataFrame({
    "ComplainantID":  np.arange(1, n_comp+1),
    "CaseMasterID":   case_ids_c,
    "ComplainantName": names(n_comp),
    "AgeYear":         RNG.integers(18, 76, n_comp),
    "OccupationID":    RNG.choice(occ_ids, n_comp, p=occ_p),
    "ReligionID":      RNG.choice([1,2,3,4,5,6,7], n_comp, p=relig_p),
    "CasteID":         RNG.choice([1,2,3,4], n_comp, p=caste_p),
    "GenderID":        RNG.choice([1,2], n_comp, p=[0.62,0.38]),
})
con.execute("INSERT INTO ComplainantDetails SELECT * FROM comp_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 9.  VICTIMS
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing Victim")
# Missing person / UDR cases: no victim record
vic_mask = cmaj_ids_f != 12
n_vic_base = vic_mask.sum()
# ~70% have 1 victim, 20% have 2, 10% have 3
vic_counts = RNG.choice([1,2,3], n_vic_base, p=[0.70,0.20,0.10])
case_ids_v  = np.repeat(np.arange(1,N+1)[vic_mask], vic_counts)
n_vic = len(case_ids_v)

vic_df = pd.DataFrame({
    "VictimMasterID": np.arange(1, n_vic+1),
    "CaseMasterID":   case_ids_v,
    "VictimName":     np.where(RNG.random(n_vic)<0.85, names(n_vic), None),
    "AgeYear":        RNG.integers(5, 81, n_vic),
    "GenderID":       RNG.choice([1,2,3], n_vic, p=[0.52,0.46,0.02]),
    "VictimPolice":   RNG.random(n_vic) < 0.01,
})
con.execute("INSERT INTO Victim SELECT * FROM vic_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 10.  ACCUSED
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing Accused")
acc_counts = RNG.choice([1,2,3,4,5], N, p=[0.55,0.25,0.10,0.06,0.04])
case_ids_a = np.repeat(np.arange(1,N+1), acc_counts)
slot_a     = np.concatenate([np.arange(c) for c in acc_counts])
n_acc = len(case_ids_a)
dist_of_fir = np.repeat(np.array(DIST_NAMES)[dist_idx], acc_counts)

acc_df = pd.DataFrame({
    "AccusedMasterID": np.arange(1, n_acc+1),
    "CaseMasterID":    case_ids_a,
    "AccusedName":     np.where(RNG.random(n_acc)<0.80, names(n_acc), None),
    "AgeYear":         RNG.integers(15, 61, n_acc),
    "GenderID":        RNG.choice([1,2,3], n_acc, p=[0.88,0.10,0.02]),
    "PersonID":        np.array([f"A{s+1}" for s in slot_a]),
    "ReligionID":      RNG.choice([1,2,3,4,5,6,7], n_acc, p=relig_p),
    "CasteID":         RNG.choice([1,2,3,4], n_acc, p=caste_p),
    "OccupationID":    RNG.choice(occ_ids, n_acc, p=occ_p),
    "Nationality":     "Indian",
    "District":        dist_of_fir,
})
con.execute("INSERT INTO Accused SELECT * FROM acc_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 11.  ARRESTS
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing ArrestSurrender")
heinous_per_acc = np.repeat(heinous_f, acc_counts)
arr_prob = np.where(heinous_per_acc, 0.75, 0.55)
arrest_mask = RNG.random(n_acc) < arr_prob
n_arr = arrest_mask.sum()

acc_ids_arrested = np.arange(1, n_acc+1)[arrest_mask]
case_ids_arr     = case_ids_a[arrest_mask]
dist_fir_arr     = np.repeat(dist_ids_f, acc_counts)[arrest_mask]
stn_fir_arr      = np.repeat(stn_ids_f, acc_counts)[arrest_mask]
io_fir_arr       = np.repeat(io_ids_f, acc_counts)[arrest_mask]
reg_fir_arr      = np.repeat(reg_dates.values, acc_counts)[arrest_mask]

arr_delay  = pd.to_timedelta(RNG.integers(0, 61, n_arr), unit="D")
arr_dates  = pd.DatetimeIndex(reg_fir_arr) + arr_delay
arr_dist   = np.where(RNG.random(n_arr) < 0.8, dist_fir_arr, RNG.choice(DIST_IDS, n_arr))
court_arr  = np.array([
    int(RNG.choice(dist_to_courts[did]))
    for did in arr_dist
])

arr_df = pd.DataFrame({
    "ArrestSurrenderID":        np.arange(1, n_arr+1),
    "CaseMasterID":             case_ids_arr,
    "AccusedMasterID":          acc_ids_arrested,
    "ArrestSurrenderTypeID":    RNG.choice([1,2], n_arr, p=[0.9,0.1]),
    "ArrestSurrenderDate":      arr_dates.date,
    "ArrestSurrenderStateId":   KARNATAKA_STATE_ID,
    "ArrestSurrenderDistrictId": arr_dist,
    "PoliceStationID":          stn_fir_arr,
    "IOID":                     io_fir_arr,
    "CourtID":                  court_arr,
    "IsAccused":                True,
    "IsComplainantAccused":     RNG.random(n_arr) < 0.03,
    "BailGranted":              RNG.random(n_arr) < 0.40,
    "RemandDays":               np.where(RNG.random(n_arr)<0.5, RNG.integers(1,15,n_arr), None),
})
con.execute("INSERT INTO ArrestSurrender SELECT * FROM arr_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 12.  CHARGESHEETS
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing ChargesheetDetails")
cs_mask = np.isin(status_f, [3,4,5]) & (RNG.random(N) < 0.75)
n_cs    = cs_mask.sum()
cs_delay = pd.to_timedelta(RNG.integers(30,181,n_cs), unit="D")

cs_df = pd.DataFrame({
    "CSID":          np.arange(1, n_cs+1),
    "CaseMasterID":  np.arange(1, N+1)[cs_mask],
    "csdate":        (reg_dates[cs_mask] + cs_delay).date,
    "cstype":        RNG.choice(["A","B","C"], n_cs, p=[0.75,0.10,0.15]),
    "PolicePersonID": io_ids_f[cs_mask],
})
con.execute("INSERT INTO ChargesheetDetails SELECT * FROM cs_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 13.  ACT-SECTION ASSOCIATIONS
# ═══════════════════════════════════════════════════════════════════════════════
log("Writing ActSectionAssociation")
asa_rows = []
for i in range(N):
    csh = int(csh_ids_f[i])
    secs = CRIME_ACT_SEC.get(csh, [("BNS","103")])
    for aidx, (act, sec) in enumerate(secs[:2]):
        asa_rows.append((i+1, act, sec, aidx+1, aidx+1))

asa_df = pd.DataFrame(asa_rows,
    columns=["CaseMasterID","ActID","SectionID","ActOrderID","SectionOrderID"])
# deduplicate (same case could have duplicate act+section)
asa_df = asa_df.drop_duplicates(subset=["CaseMasterID","ActID","SectionID"])
con.execute("INSERT INTO ActSectionAssociation SELECT * FROM asa_df")

# ═══════════════════════════════════════════════════════════════════════════════
# 14.  GANG MEMBERSHIPS  (2000 accused linked to gangs)
# ═══════════════════════════════════════════════════════════════════════════════
log("Linking accused to gangs")
gang_acc_ids = RNG.choice(n_acc, min(2000, n_acc//5), replace=False) + 1
gang_links = pd.DataFrame({
    "AccusedMasterID": gang_acc_ids,
    "GangID":   RNG.integers(1, len(GANGS)+1, len(gang_acc_ids)),
    "Role":     RNG.choice(["leader","member","financier","mule","lookout"], len(gang_acc_ids)),
    "JoinedYear": RNG.integers(2015, 2024, len(gang_acc_ids)),
}).drop_duplicates(subset=["AccusedMasterID","GangID"])
con.execute("INSERT INTO AccusedGangLink SELECT * FROM gang_links")

# ═══════════════════════════════════════════════════════════════════════════════
# 15.  FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════
log("Verifying row counts")
tables = ["CaseMaster","Accused","Victim","ComplainantDetails",
          "ArrestSurrender","ChargesheetDetails","Employee","Unit","District","CrimeGang"]
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
con.close()

elapsed_total = time.time() - T0
db_mb = OUT.stat().st_size / 1024**2

print(f"\n{'='*52}")
print(f"  KSP Crime Intelligence  -  Synthetic Database")
print(f"{'='*52}")
for t, c in counts.items():
    print(f"  {t:<30} {c:>10,}")
print(f"{'='*52}")
print(f"  Output : {OUT}")
print(f"  Size   : {db_mb:.1f} MB")
print(f"  Time   : {elapsed_total:.0f}s")
print(f"{'='*52}\n")
