"""Parse and normalize Karnataka FIR Details CSV."""

from pathlib import Path

import pandas as pd

FIR_CSV_COLUMNS = {
    "District_Name": "district_name",
    "UnitName": "unit_name",
    "FIR_YEAR": "fir_year",
    "FIR_MONTH": "fir_month",
    "Offence_Duration": "offence_duration",
    "FIR_Day": "fir_day",
    "FIR Type": "fir_type",
    "FIR_Stage": "fir_stage",
    "Complaint_Mode": "complaint_mode",
    "CrimeGroup_Name": "crime_group_name",
    "CrimeHead_Name": "crime_head_name",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "ActSection": "act_section",
    "IOName": "io_name",
    "KGID": "kgid",
    "Internal_IO": "internal_io",
    "Place of Offence": "place_of_offence",
    "Distance from PS": "distance_from_ps",
    "Beat_Name": "beat_name",
    "Village_Area_Name": "village_area_name",
    "Male": "male_victims",
    "Female": "female_victims",
    "Boy": "boy_victims",
    "Girl": "girl_victims",
    "Age 0": "age_0_victims",
    "VICTIM COUNT": "victim_count",
    "Accused Count": "accused_count",
    "Arrested Male": "arrested_male",
    "Arrested Female": "arrested_female",
    "Arrested Count\tNo.": "arrested_count",
    "Accused_ChargeSheeted Count": "chargesheeted_count",
    "Conviction Count": "conviction_count",
    "Unit_ID": "unit_id",
}

COMPLAINT_MODE_CODES = {
    "written": 1,
    "oral": 2,
    "electronic": 3,
    "sue-moto by police": 4,
    "court": 5,
    "phone": 6,
}


def normalize_fir_chunk(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns and clean a FIR CSV chunk."""
    df = df.rename(columns=FIR_CSV_COLUMNS)
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    for col in [
        "fir_year", "fir_month", "fir_day", "offence_duration",
        "male_victims", "female_victims", "boy_victims", "girl_victims",
        "age_0_victims", "victim_count", "accused_count",
        "arrested_male", "arrested_female", "arrested_count",
        "chargesheeted_count", "conviction_count", "unit_id", "internal_io",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["accused_count"] = df["accused_count"].clip(lower=0)
    df["arrested_count"] = df["arrested_count"].clip(lower=0)
    df["chargesheeted_count"] = df["chargesheeted_count"].clip(lower=0)
    df["conviction_count"] = df["conviction_count"].clip(lower=0)
    return df


def iter_fir_chunks(csv_path: Path, chunksize: int = 100_000):
    """Yield normalized FIR CSV chunks."""
    for chunk in pd.read_csv(csv_path, chunksize=chunksize, low_memory=False):
        yield normalize_fir_chunk(chunk)


def complaint_mode_code(mode: str | None) -> int:
    if not mode:
        return 0
    key = mode.lower().strip()
    for token, code in COMPLAINT_MODE_CODES.items():
        if token in key:
            return code
    return 0
