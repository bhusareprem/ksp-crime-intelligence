"""Generate synthetic Karnataka FIR records, police stations, and criminals."""

import hashlib
import random
from datetime import date, timedelta

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
Faker.seed(42)
random.seed(42)
np.random.seed(42)

CYBER_CRIMES = {h["name"] for h in CRIME_HEADS if "Cyber" in h["name"]}
ECONOMIC_CRIMES = {"Cheating & Fraud", "Criminal Breach of Trust", "Forgery", "Counterfeiting"}


def generate_districts() -> pd.DataFrame:
    rows = []
    for i, d in enumerate(KARNATAKA_DISTRICTS, start=1):
        rows.append({
            "district_id": i,
            "name": d["name"],
            "name_kn": d["name_kn"],
            "latitude": d["lat"],
            "longitude": d["lon"],
            "population": d["pop"],
            "zone": d["zone"],
        })
    return pd.DataFrame(rows)


def generate_police_stations(districts_df: pd.DataFrame, total_stations: int = 1150) -> pd.DataFrame:
    """Generate police stations weighted by district population."""
    pops = districts_df["population"].values.astype(float)
    weights = pops / pops.sum()
    station_counts = np.random.multinomial(total_stations, weights)

    rows = []
    station_id = 1
    for _, district in districts_df.iterrows():
        count = station_counts[district["district_id"] - 1]
        for j in range(count):
            prefix = random.choice(STATION_PREFIXES)
            locality = fake.city() if random.random() > 0.3 else district["name"].split()[0]
            name = f"{locality} {prefix} PS"
            lat = district["latitude"] + random.uniform(-0.15, 0.15)
            lon = district["longitude"] + random.uniform(-0.15, 0.15)
            code = f"KA-{district['district_id']:02d}-{station_id:04d}"
            rows.append({
                "station_id": station_id,
                "name": name,
                "district_id": district["district_id"],
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "station_code": code,
            })
            station_id += 1
    return pd.DataFrame(rows)


def generate_crime_heads() -> pd.DataFrame:
    rows = []
    for i, ch in enumerate(CRIME_HEADS, start=1):
        rows.append({"crime_head_id": i, **ch})
    return pd.DataFrame(rows)


def _district_weights(districts_df: pd.DataFrame) -> np.ndarray:
    pops = districts_df["population"].values.astype(float)
    # Bengaluru Urban gets extra weight for metro crime concentration
    weights = pops.copy()
    urban_idx = districts_df[districts_df["name"] == "Bengaluru Urban"].index
    if len(urban_idx):
        weights[urban_idx[0]] *= 2.5
    return weights / weights.sum()


def generate_fir_records(
    districts_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    crime_heads_df: pd.DataFrame,
    n_firs: int = 5500,
) -> pd.DataFrame:
    """Generate synthetic FIR records aligned with NCRB crime distribution."""
    crime_names = list(CRIME_WEIGHTS.keys())
    crime_probs = np.array([CRIME_WEIGHTS[c] for c in crime_names])
    crime_probs = crime_probs / crime_probs.sum()

    name_to_id = dict(zip(crime_heads_df["name"], crime_heads_df["crime_head_id"]))
    crime_ids = [name_to_id[c] for c in crime_names]

    station_weights = stations_df.merge(districts_df, on="district_id")
    sw = station_weights["population"].values.astype(float)
    sw = sw / sw.sum()

    year_weights = {2022: 0.28, 2023: 0.34, 2024: 0.38}
    years = list(year_weights.keys())
    yw = np.array([year_weights[y] for y in years])
    yw = yw / yw.sum()

    status_weights = [0.08, 0.35, 0.30, 0.17, 0.10]

    descriptions = {
        "Theft": "Complaint received regarding theft of {item} worth Rs.{amount}.",
        "Murder": "Dead body found at {location}. Prima facie case of murder registered.",
        "Rape": "Victim reported sexual assault incident at {location}. Medical examination conducted.",
        "Cyber Crime - Online Fraud": "Victim lost Rs.{amount} through online fraud/UPI scam.",
        "Cheating & Fraud": "Accused cheated complainant of Rs.{amount} through false promises.",
        "Robbery": "Complainant robbed at {location} by {n} armed persons.",
    }

    rows = []
    fir_counter = {}

    for i in range(1, n_firs + 1):
        station_idx = np.random.choice(len(stations_df), p=sw)
        station = stations_df.iloc[station_idx]
        crime_idx = np.random.choice(len(crime_names), p=crime_probs)
        crime_name = crime_names[crime_idx]
        crime_id = crime_ids[crime_idx]

        year = int(np.random.choice(years, p=yw))
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        reg_date = date(year, month, day)

        dist_key = station["district_id"]
        fir_counter[dist_key] = fir_counter.get(dist_key, 0) + 1
        fir_num = f"FIR/{year}/KA{dist_key:02d}/{fir_counter[dist_key]:05d}"

        status = random.choices(FIR_STATUSES, weights=status_weights)[0]
        chargesheet = 1 if status in ("chargesheeted", "pending_trial", "closed") else 0

        tmpl = descriptions.get(crime_name, "FIR registered for {crime} at {location}.")
        desc = tmpl.format(
            item=random.choice(["mobile phone", "two-wheeler", "gold chain", "laptop", "cash"]),
            amount=random.randint(5000, 500000),
            location=fake.street_name(),
            n=random.randint(1, 4),
            crime=crime_name,
        )

        rows.append({
            "fir_id": i,
            "fir_number": fir_num,
            "station_id": station["station_id"],
            "crime_head_id": crime_id,
            "date_registered": reg_date.isoformat(),
            "year": year,
            "month": month,
            "status": status,
            "description": desc,
            "victim_age": random.randint(18, 75) if random.random() > 0.1 else None,
            "victim_gender": random.choice(["Male", "Female", "Other"]),
            "accused_count": random.randint(1, 5),
            "latitude": station["latitude"] + random.uniform(-0.02, 0.02),
            "longitude": station["longitude"] + random.uniform(-0.02, 0.02),
            "is_cyber": 1 if crime_name in CYBER_CRIMES else 0,
            "is_economic": 1 if crime_name in ECONOMIC_CRIMES else 0,
            "chargesheet_filed": chargesheet,
        })

    return pd.DataFrame(rows)


def generate_criminals_and_links(
    districts_df: pd.DataFrame,
    fir_df: pd.DataFrame,
    n_criminals: int = 1200,
    link_rate: float = 0.45,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate criminals with network overlap (repeat offenders in multiple FIRs)."""
    criminal_rows = []
    for i in range(1, n_criminals + 1):
        district = districts_df.sample(1).iloc[0]
        gender = random.choice(["Male", "Female"])
        name = fake.name_male() if gender == "Male" else fake.name_female()
        aadhaar = hashlib.sha256(f"crim-{i}".encode()).hexdigest()[:16]
        criminal_rows.append({
            "criminal_id": i,
            "name": name,
            "alias": fake.first_name() if random.random() > 0.6 else None,
            "age": random.randint(18, 60),
            "gender": gender,
            "district_id": district["district_id"],
            "aadhaar_hash": aadhaar,
            "status": random.choice(CRIMINAL_STATUSES),
            "created_at": (date.today() - timedelta(days=random.randint(30, 1000))).isoformat(),
        })
    criminals_df = pd.DataFrame(criminal_rows)

    # Link criminals to FIRs — create network clusters
    link_rows = []
    link_id = 1
    fir_ids = fir_df["fir_id"].tolist()
    linked_firs = random.sample(fir_ids, int(len(fir_ids) * link_rate))

    # 15% of criminals are repeat offenders (appear in 2-5 FIRs)
    repeat_ids = set(random.sample(range(1, n_criminals + 1), int(n_criminals * 0.15)))

    for fir_id in linked_firs:
        n_accused = random.randint(1, 3)
        if random.random() < 0.15 and repeat_ids:
            pool = list(repeat_ids)
        else:
            pool = list(range(1, n_criminals + 1))
        chosen = random.sample(pool, min(n_accused, len(pool)))
        for cid in chosen:
            link_rows.append({
                "link_id": link_id,
                "fir_id": fir_id,
                "criminal_id": cid,
                "role": "accused",
            })
            link_id += 1

    # Add extra links for repeat offenders to build network graph
    for cid in repeat_ids:
        extra_firs = random.sample(linked_firs, min(random.randint(1, 3), len(linked_firs)))
        for fir_id in extra_firs:
            if not any(l["fir_id"] == fir_id and l["criminal_id"] == cid for l in link_rows):
                link_rows.append({
                    "link_id": link_id,
                    "fir_id": fir_id,
                    "criminal_id": cid,
                    "role": "accused",
                })
                link_id += 1

    return criminals_df, pd.DataFrame(link_rows)


def generate_all(n_firs: int = 5500, n_stations: int = 1150, n_criminals: int = 1200) -> dict:
    print(f"  Generating {len(KARNATAKA_DISTRICTS)} districts...")
    districts = generate_districts()
    print(f"  Generating {n_stations} police stations...")
    stations = generate_police_stations(districts, n_stations)
    print(f"  Generating {len(CRIME_HEADS)} crime heads...")
    crime_heads = generate_crime_heads()
    print(f"  Generating {n_firs} FIR records...")
    firs = generate_fir_records(districts, stations, crime_heads, n_firs)
    print(f"  Generating {n_criminals} criminals with network links...")
    criminals, links = generate_criminals_and_links(districts, firs, n_criminals)
    return {
        "districts": districts,
        "police_stations": stations,
        "crime_heads": crime_heads,
        "fir_records": firs,
        "criminals": criminals,
        "fir_criminal_link": links,
    }
