"""
Unified aligned demo dataset for KSP Crime Intelligence hackathon.

Generates master records (districts, persons, FIRs, court cases, networks)
with consistent IDs and years 2018-2024 across all three databases.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from src.karnataka_data import (
    CRIME_HEADS,
    CRIME_WEIGHTS,
    CRIMINAL_STATUSES,
    FIR_STATUSES,
    KARNATAKA_DISTRICTS,
    STATION_PREFIXES,
)

fake = Faker("en_IN")
Faker.seed(2024)
random.seed(2024)
np.random.seed(2024)

FIR_ID_START = 1_000_001
PERSON_ID_START = 10_001
CASE_ID_START = 500_001

CASTE_CATEGORIES = ["General", "OBC", "SC", "ST"]
EDUCATION_LEVELS = ["Illiterate", "Primary", "Secondary", "Graduate", "Post-Graduate"]
OCCUPATIONS = ["Farmer", "Daily Wage", "Student", "Professional", "Business", "Unemployed", "Driver"]
RISK_LEVELS = ["low", "medium", "high", "critical"]
COURT_DISPOSITIONS = [
    "Convicted", "Acquitted", "Pending Trial", "Withdrawn", "Compounded", "Discharged",
]
CRIME_GROUPS = ["Property Offences", "Violent Crimes", "Economic Offences", "Cyber Crimes", "Special Laws"]

# Map district display name -> e-Courts uppercase label
COURT_DISTRICT = {
    d["name"]: d["name"].upper().replace("BENGALURU URBAN", "BENGALURU")
    .replace("BENGALURU RURAL", "BENGALURU RURAL")
    for d in KARNATAKA_DISTRICTS
}
COURT_DISTRICT["Bengaluru Urban"] = "BENGALURU"
COURT_DISTRICT["Mysuru"] = "MYSURU"
COURT_DISTRICT["Belagavi"] = "BELAGAVI"


@dataclass
class UnifiedConfig:
    n_firs: int = 35_000
    n_persons: int = 3_000
    n_stations: int = 900
    year_start: int = 2018
    year_end: int = 2024
    court_link_ratio: float = 0.55  # share of FIRs with court case


@dataclass
class UnifiedMaster:
    config: UnifiedConfig
    districts: pd.DataFrame = field(default_factory=pd.DataFrame)
    crime_heads: pd.DataFrame = field(default_factory=pd.DataFrame)
    crime_groups: pd.DataFrame = field(default_factory=pd.DataFrame)
    police_stations: pd.DataFrame = field(default_factory=pd.DataFrame)
    police_units: pd.DataFrame = field(default_factory=pd.DataFrame)
    persons: pd.DataFrame = field(default_factory=pd.DataFrame)
    firs: pd.DataFrame = field(default_factory=pd.DataFrame)
    accused: pd.DataFrame = field(default_factory=pd.DataFrame)
    co_accused: pd.DataFrame = field(default_factory=pd.DataFrame)
    signatures: pd.DataFrame = field(default_factory=pd.DataFrame)
    profiles: pd.DataFrame = field(default_factory=pd.DataFrame)
    behavior: pd.DataFrame = field(default_factory=pd.DataFrame)
    court_cases: pd.DataFrame = field(default_factory=pd.DataFrame)
    fir_case_link: pd.DataFrame = field(default_factory=pd.DataFrame)
    ksp_criminals: pd.DataFrame = field(default_factory=pd.DataFrame)
    fir_criminal_link: pd.DataFrame = field(default_factory=pd.DataFrame)
    ncrb_city: pd.DataFrame = field(default_factory=pd.DataFrame)
    ncrb_national: pd.DataFrame = field(default_factory=pd.DataFrame)


def _crime_group_for(name: str) -> str:
    if "Cyber" in name:
        return "Cyber Crimes"
    if name in ("Cheating & Fraud", "Criminal Breach of Trust", "Forgery", "Counterfeiting"):
        return "Economic Offences"
    if name in ("POCSO Act", "NDPS Act", "Dowry Prohibition Act", "SC/ST Atrocities Act", "Domestic Violence"):
        return "Special Laws"
    if name in ("Murder", "Attempt to Murder", "Rape", "Robbery", "Dacoity", "Riots"):
        return "Violent Crimes"
    return "Property Offences"


def generate_unified_master(cfg: UnifiedConfig | None = None) -> UnifiedMaster:
    cfg = cfg or UnifiedConfig()
    master = UnifiedMaster(config=cfg)

    # --- Districts (shared IDs 1..31) ---
    districts = []
    for i, d in enumerate(KARNATAKA_DISTRICTS, start=1):
        districts.append({
            "district_id": i,
            "name": d["name"],
            "name_kn": d.get("name_kn", d["name"]),
            "latitude": d["lat"],
            "longitude": d["lon"],
            "population": d["pop"],
            "zone": d["zone"],
            "court_district_name": COURT_DISTRICT.get(d["name"], d["name"].upper()),
        })
    master.districts = pd.DataFrame(districts)

    # --- Crime heads & groups ---
    groups = {g: i + 1 for i, g in enumerate(CRIME_GROUPS)}
    master.crime_groups = pd.DataFrame([
        {"group_id": gid, "name": gname} for gname, gid in groups.items()
    ])
    heads = []
    for i, ch in enumerate(CRIME_HEADS, start=1):
        gname = _crime_group_for(ch["name"])
        heads.append({
            "crime_head_id": i,
            "head_id": i,
            "name": ch["name"],
            "category": ch["category"],
            "ipc_section": ch["ipc_section"],
            "severity": ch["severity"],
            "group_id": groups[gname],
            "crime_group_name": gname,
        })
    master.crime_heads = pd.DataFrame(heads)

    head_names = master.crime_heads["name"].tolist()
    weights = np.array([CRIME_WEIGHTS.get(n, 1) for n in head_names], dtype=float)
    weights /= weights.sum()
    dist_pops = master.districts["population"].values.astype(float)
    dist_weights = dist_pops / dist_pops.sum()

    # --- Police stations / units ---
    station_counts = np.random.multinomial(cfg.n_stations, dist_weights)
    stations, units = [], []
    sid, uid = 1, 1
    for _, dist in master.districts.iterrows():
        n = station_counts[dist["district_id"] - 1]
        for _ in range(n):
            loc = fake.city()
            prefix = random.choice(STATION_PREFIXES)
            name = f"{loc} {prefix} PS"
            lat = dist["latitude"] + random.uniform(-0.12, 0.12)
            lon = dist["longitude"] + random.uniform(-0.12, 0.12)
            stations.append({
                "station_id": sid,
                "unit_id": uid,
                "name": name,
                "district_id": dist["district_id"],
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "station_code": f"KA-{dist['district_id']:02d}-{sid:04d}",
            })
            units.append({"unit_id": uid, "name": name, "district_id": dist["district_id"]})
            sid += 1
            uid += 1
    master.police_stations = pd.DataFrame(stations)
    master.police_units = pd.DataFrame(units)

    # --- Persons (named criminals / accused) ---
    persons = []
    for pid in range(PERSON_ID_START, PERSON_ID_START + cfg.n_persons):
        dist_id = int(np.random.choice(master.districts["district_id"], p=dist_weights))
        dist_name = master.districts.loc[master.districts["district_id"] == dist_id, "name"].iloc[0]
        age = int(np.clip(np.random.normal(32, 12), 16, 70))
        risk_score = round(float(np.random.beta(2, 5) * 100), 1)
        persons.append({
            "person_id": pid,
            "criminal_id": pid - PERSON_ID_START + 1,
            "name": fake.name(),
            "alias": fake.first_name() if random.random() < 0.35 else None,
            "age": age,
            "gender": random.choice(["Male", "Female", "Other"]),
            "caste_category": np.random.choice(CASTE_CATEGORIES, p=[0.35, 0.35, 0.18, 0.12]),
            "education": np.random.choice(EDUCATION_LEVELS, p=[0.15, 0.25, 0.35, 0.18, 0.07]),
            "occupation": random.choice(OCCUPATIONS),
            "district_id": dist_id,
            "district_name": dist_name,
            "status": random.choice(CRIMINAL_STATUSES),
            "repeat_offender_score": risk_score,
            "risk_level": (
                "critical" if risk_score > 75 else "high" if risk_score > 50
                else "medium" if risk_score > 25 else "low"
            ),
        })
    master.persons = pd.DataFrame(persons)

    # --- Network gangs (co-offenders) ---
    gang_size = 5
    n_gangs = max(80, cfg.n_persons // gang_size)
    person_ids = master.persons["person_id"].tolist()
    gangs = [person_ids[i:i + gang_size] for i in range(0, min(len(person_ids), n_gangs * gang_size), gang_size)]

    # --- FIRs ---
    year_weights = np.array([1, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3])  # 2018-2024 growth
    year_weights /= year_weights.sum()
    years = list(range(cfg.year_start, cfg.year_end + 1))

    firs, accused_rows, co_rows = [], [], []
    fir_id = FIR_ID_START
    accused_id = 1
    co_id = 1

    stations_by_dist = master.police_stations.groupby("district_id")["station_id"].apply(list).to_dict()

    for _ in range(cfg.n_firs):
        dist_id = int(np.random.choice(master.districts["district_id"], p=dist_weights))
        dist_row = master.districts[master.districts["district_id"] == dist_id].iloc[0]
        station_id = random.choice(stations_by_dist[dist_id])
        unit_id = master.police_stations[master.police_stations["station_id"] == station_id]["unit_id"].iloc[0]
        head_idx = int(np.random.choice(len(head_names), p=weights))
        head = master.crime_heads.iloc[head_idx]
        year = int(np.random.choice(years, p=year_weights))
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        village = fake.street_name()
        lat = dist_row["latitude"] + random.uniform(-0.08, 0.08)
        lon = dist_row["longitude"] + random.uniform(-0.08, 0.08)
        n_accused = max(1, int(np.random.poisson(1.3)))
        n_arrested = min(n_accused, int(np.random.binomial(n_accused, 0.65)))
        fir_stage = random.choice(
            ["Pending Trial", "Convicted", "Dis/Acq", "Under Investigation", "Chargesheeted", "False Case"]
        )
        is_cyber = 1 if "Cyber" in head["name"] else 0
        is_econ = 1 if head["crime_group_name"] == "Economic Offences" else 0

        firs.append({
            "fir_id": fir_id,
            "fir_number": f"FIR/{dist_id}/{year}/{fir_id % 100000:05d}",
            "district_id": dist_id,
            "district_name": dist_row["name"],
            "station_id": station_id,
            "unit_id": unit_id,
            "crime_head_id": head["crime_head_id"],
            "crime_group_id": head["group_id"],
            "crime_type": head["name"],
            "crime_group": head["crime_group_name"],
            "year": year,
            "fir_year": year,
            "month": month,
            "fir_month": month,
            "fir_day": day,
            "date_registered": date(year, month, day).isoformat(),
            "fir_stage": fir_stage,
            "status": random.choice(FIR_STATUSES),
            "village_area_name": village,
            "place_of_offence": f"{village}, {dist_row['name']}",
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "accused_count": n_accused,
            "arrested_count": n_arrested,
            "arrested_male": n_arrested if random.random() > 0.2 else 0,
            "arrested_female": n_arrested - (n_arrested if random.random() > 0.2 else 0),
            "victim_count": max(0, int(np.random.poisson(0.8))),
            "male_victims": random.randint(0, 2),
            "female_victims": random.randint(0, 2),
            "is_cyber": is_cyber,
            "is_economic": is_econ,
            "chargesheet_filed": 1 if fir_stage in ("Convicted", "Chargesheeted", "Pending Trial") else 0,
            "chargesheeted_count": 1 if fir_stage in ("Convicted", "Chargesheeted", "Pending Trial") else 0,
            "conviction_count": 1 if fir_stage == "Convicted" else 0,
            "complaint_mode": random.choice(["Written", "Oral", "Online", "Phone", "Zero FIR"]),
            "court_district": dist_row["court_district_name"],
        })

        # Pick accused — bias toward gang members for repeat offenders
        if random.random() < 0.25 and gangs:
            gang = random.choice(gangs)
            accused_pids = random.sample(gang, min(n_accused, len(gang)))
            while len(accused_pids) < n_accused:
                accused_pids.append(random.choice(person_ids))
        else:
            accused_pids = random.sample(person_ids, n_accused)

        fir_accused_ids = []
        for seq, pid in enumerate(accused_pids, start=1):
            was_arrested = 1 if seq <= n_arrested else 0
            was_chargesheeted = 1 if firs[-1]["chargesheet_filed"] else 0
            was_convicted = 1 if fir_stage == "Convicted" and seq == 1 else 0
            accused_rows.append({
                "accused_id": accused_id,
                "fir_id": fir_id,
                "person_id": pid,
                "accused_seq": seq,
                "was_arrested": was_arrested,
                "was_chargesheeted": was_chargesheeted,
                "was_convicted": was_convicted,
            })
            fir_accused_ids.append(accused_id)
            accused_id += 1

        # Co-accused links within same FIR
        for i in range(len(fir_accused_ids)):
            for j in range(i + 1, len(fir_accused_ids)):
                co_rows.append({
                    "link_id": co_id,
                    "fir_id": fir_id,
                    "accused_id_a": fir_accused_ids[i],
                    "accused_id_b": fir_accused_ids[j],
                    "link_weight": round(random.uniform(0.5, 1.0), 2),
                })
                co_id += 1

        fir_id += 1

    master.firs = pd.DataFrame(firs)
    master.accused = pd.DataFrame(accused_rows)
    master.co_accused = pd.DataFrame(co_rows)

    # --- Signatures & behavioral profiles (by person) — vectorized merge ---
    acc_fir = master.accused.merge(master.firs, on="fir_id", how="inner")
    persons_idx = master.persons.set_index("person_id")
    heinous_types = {"Murder", "Rape", "Dacoity", "POCSO Act"}

    sig_rows, prof_rows = [], []
    sig_id = 1
    for pid, g in acc_fir.groupby("person_id"):
        if pid not in persons_idx.index:
            continue
        person = persons_idx.loc[pid]
        primary = g["crime_type"].mode().iloc[0]
        primary_group = g["crime_group"].mode().iloc[0]
        total_firs = g["fir_id"].nunique()
        pa = g.drop_duplicates(subset=["fir_id", "accused_seq"])
        arrest_rate = pa["was_arrested"].mean()
        conv_rate = pa["was_convicted"].mean()
        cs_rate = pa["was_chargesheeted"].mean()
        heinous = g["crime_type"].isin(heinous_types).mean()
        peak_month = int(g["month"].mode().iloc[0])
        span = int(g["year"].max() - g["year"].min()) + 1
        tags = json.dumps({
            "caste": person["caste_category"],
            "education": person["education"],
            "occupation": person["occupation"],
            "age_group": "18-25" if person["age"] < 26 else "26-35" if person["age"] < 36 else "36+",
            "peak_hours": random.choice(["night", "evening", "day"]),
            "mobility": random.choice(["local", "inter_district", "inter_state"]),
        })
        village = g["village_area_name"].mode().iloc[0]
        sig_rows.append({
            "signature_id": sig_id,
            "person_id": pid,
            "district_id": person["district_id"],
            "village_area_name": village,
            "crime_head_id": int(g["crime_head_id"].mode().iloc[0]),
            "fir_count": total_firs,
            "total_accused": total_firs,
            "total_convictions": int(pa["was_convicted"].sum()),
            "first_year": int(g["year"].min()),
            "last_year": int(g["year"].max()),
            "repeat_offender_score": person["repeat_offender_score"],
        })
        prof_rows.append({
            "profile_id": sig_id,
            "signature_id": sig_id,
            "person_id": pid,
            "person_name": person["name"],
            "district_name": person["district_name"],
            "village_area_name": village,
            "primary_crime_head": primary,
            "primary_crime_group": primary_group,
            "total_firs": total_firs,
            "total_accused": total_firs,
            "avg_accused_per_fir": 1.0,
            "arrest_rate": round(arrest_rate, 3),
            "conviction_rate": round(conv_rate, 3),
            "chargesheet_rate": round(cs_rate, 3),
            "heinous_ratio": round(heinous, 3),
            "peak_month": peak_month,
            "active_span_years": span,
            "repeat_offender_score": person["repeat_offender_score"],
            "risk_level": person["risk_level"],
            "behavioral_tags": tags,
            "caste_category": person["caste_category"],
            "education": person["education"],
            "occupation": person["occupation"],
        })
        sig_id += 1

    master.signatures = pd.DataFrame(sig_rows)
    master.profiles = pd.DataFrame(prof_rows)

    # Behavior features — one row per FIR (vectorized)
    pf = master.firs[master.firs["fir_id"].isin(master.accused["fir_id"].unique())].copy()
    pf["day_of_week"] = pd.to_datetime(pf["date_registered"]).dt.dayofweek
    pf["is_weekend"] = (pf["day_of_week"] >= 5).astype(int)
    pf["is_heinous"] = pf["crime_type"].isin(heinous_types).astype(int)
    master.behavior = pd.DataFrame({
        "fir_id": pf["fir_id"],
        "day_of_week": pf["day_of_week"],
        "is_weekend": pf["is_weekend"],
        "is_heinous": pf["is_heinous"],
        "has_geo": 1,
        "victim_total": pf["victim_count"],
        "child_victim": (pf["crime_type"] == "POCSO Act").astype(int),
        "female_victim": pf["female_victims"],
        "accused_count": pf["accused_count"],
        "arrest_rate": pf["arrested_count"] / pf["accused_count"].clip(lower=1),
        "conviction_rate": pf["conviction_count"],
        "chargesheet_rate": pf["chargesheeted_count"],
        "offence_duration_days": np.random.randint(0, 91, size=len(pf)),
        "complaint_mode_code": pf["complaint_mode"].apply(lambda x: hash(x) % 5),
        "crime_severity_score": np.round(np.random.uniform(0.2, 1.0, len(pf)), 2),
        "temporal_risk_score": np.round(np.random.uniform(0.1, 0.9, len(pf)), 2),
    })

    # Update accused with signature_id
    pid_to_sig = dict(zip(master.signatures["person_id"], master.signatures["signature_id"]))
    master.accused["signature_id"] = master.accused["person_id"].map(pid_to_sig)

    # --- Court cases linked to FIRs ---
    case_rows, link_rows = [], []
    case_num = CASE_ID_START
    eligible = master.firs[master.firs["fir_stage"].isin(
        ["Convicted", "Dis/Acq", "Pending Trial", "Chargesheeted", "False Case"]
    )]
    n_cases = int(len(eligible) * cfg.court_link_ratio)
    case_firs = eligible.sample(n=min(n_cases, len(eligible)), random_state=42)

    stage_to_disp = {
        "Convicted": "Convicted",
        "Dis/Acq": "Acquitted",
        "Pending Trial": "Pending Trial",
        "Chargesheeted": "Pending Trial",
        "False Case": "Withdrawn",
    }

    for _, fr in case_firs.iterrows():
        ddl_id = f"KSP-{case_num}"
        disp = stage_to_disp.get(fr["fir_stage"], "Pending Trial")
        filing = date(fr["year"], fr["month"], fr["fir_day"])
        duration = random.randint(180, 900) if disp != "Pending Trial" else random.randint(30, 600)
        decision_date = None
        if disp != "Pending Trial":
            decision_date = (pd.Timestamp(filing) + pd.Timedelta(days=duration)).strftime("%Y-%m-%d")
        case_rows.append({
            "ddl_case_id": ddl_id,
            "linked_fir_id": fr["fir_id"],
            "year": fr["year"],
            "state_code": 29,
            "state_name": "Karnataka",
            "district_name": fr["court_district"],
            "court_name": f"{fr['court_district']} District Court",
            "type_name_s": fr["crime_type"],
            "purpose_name_s": "Trial",
            "disp_name_s": disp,
            "date_of_filing": filing.isoformat(),
            "date_of_decision": decision_date,
            "case_duration_days": duration,
            "female_defendant": random.choice(["Y", "N"]),
        })
        link_rows.append({"fir_id": fr["fir_id"], "ddl_case_id": ddl_id})
        case_num += 1

    master.court_cases = pd.DataFrame(case_rows)
    master.fir_case_link = pd.DataFrame(link_rows)

    # --- ksp_crime criminals (top repeat offenders with names) ---
    top_persons = master.profiles.nlargest(min(1200, len(master.profiles)), "repeat_offender_score")
    ksp_crim = []
    for _, row in top_persons.iterrows():
        p = master.persons[master.persons["person_id"] == row["person_id"]].iloc[0]
        ksp_crim.append({
            "criminal_id": p["criminal_id"],
            "person_id": p["person_id"],
            "name": p["name"],
            "alias": p["alias"],
            "age": p["age"],
            "gender": p["gender"],
            "district_id": p["district_id"],
            "status": p["status"],
        })
    master.ksp_criminals = pd.DataFrame(ksp_crim)

    links = []
    link_id = 1
    for _, acc in master.accused.iterrows():
        p = master.persons[master.persons["person_id"] == acc["person_id"]]
        if p.empty:
            continue
        cid = p.iloc[0]["criminal_id"]
        if cid not in master.ksp_criminals["criminal_id"].values:
            continue
        links.append({
            "link_id": link_id,
            "fir_id": acc["fir_id"],
            "criminal_id": cid,
            "role": "accused",
        })
        link_id += 1
    master.fir_criminal_link = pd.DataFrame(links)

    # --- NCRB aggregates derived from FIR data (aligned years) ---
    ncrb_city_rows, ncrb_nat_rows = [], []
    for year in years:
        yf = master.firs[master.firs["year"] == year]
        total = len(yf)
        pop_lakhs = master.districts["population"].sum() / 100_000
        ncrb_nat_rows.append({
            "year": year,
            "population_lakhs": round(pop_lakhs, 2),
            "total_incidence": total,
            "total_crime_rate": round(total / pop_lakhs, 2),
            "ipc_bns_incidence": int(total * 0.85),
            "sll_incidence": int(total * 0.15),
            "ipc_bns_crime_rate": round(total * 0.85 / pop_lakhs, 2),
            "sll_crime_rate": round(total * 0.15 / pop_lakhs, 2),
        })
        for city in ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi", "Belagavi"]:
            dist_match = {
                "Bengaluru": "Bengaluru Urban",
                "Mysuru": "Mysuru",
                "Mangaluru": "Dakshina Kannada",
                "Hubballi": "Dharwad",
                "Belagavi": "Belagavi",
            }[city]
            did = master.districts[master.districts["name"] == dist_match]["district_id"].iloc[0]
            cf = yf[yf["district_id"] == did]
            for stat_type in ["overall", "cyber", "women", "economic"]:
                if stat_type == "cyber":
                    cnt = len(cf[cf["is_cyber"] == 1])
                elif stat_type == "women":
                    cnt = int(cf["female_victims"].sum())
                elif stat_type == "economic":
                    cnt = len(cf[cf["is_economic"] == 1])
                else:
                    cnt = len(cf)
                pop = master.districts[master.districts["district_id"] == did]["population"].iloc[0]
                ncrb_city_rows.append({
                    "city": city,
                    "state": "Karnataka",
                    "year": year,
                    "total_cases": cnt,
                    "crime_rate": round(cnt / pop * 100_000, 2),
                    "chargesheet_rate": round(random.uniform(65, 92), 1),
                    "stat_type": stat_type,
                })
    master.ncrb_city = pd.DataFrame(ncrb_city_rows)
    master.ncrb_national = pd.DataFrame(ncrb_nat_rows)

    return master


def save_registry(master: UnifiedMaster, path: Path) -> None:
    cfg = master.config
    registry = {
        "version": "unified_demo_v1",
        "years": [cfg.year_start, cfg.year_end],
        "fir_id_range": [FIR_ID_START, FIR_ID_START + cfg.n_firs - 1],
        "person_count": len(master.persons),
        "fir_count": len(master.firs),
        "court_case_count": len(master.court_cases),
        "co_accused_links": len(master.co_accused),
        "districts": master.districts["name"].tolist(),
        "alignment_notes": (
            "Same fir_id in criminal.db and ksp_crime.db; "
            "cases.db linked via linked_fir_id; person names in persons + ksp criminals"
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
