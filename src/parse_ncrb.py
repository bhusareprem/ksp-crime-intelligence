"""Parse NCRB XLSX files into clean Pandas DataFrames."""

from pathlib import Path
import re
import pandas as pd


def _clean_numeric(val):
    if pd.isna(val) or val in ("-", "NA", "N/A", ""):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_crime_head_table(filepath: Path, category: str = "IPC") -> pd.DataFrame:
    """Parse table_1.2 (IPC/BNS) or table_1.3 (SLL) crime head-wise stats."""
    df = pd.read_excel(filepath, header=None)
    rows = []
    for i in range(3, len(df)):
        row = df.iloc[i]
        crime_head = row.iloc[1]
        if pd.isna(crime_head) or str(crime_head).strip() in ("", "nan"):
            continue
        crime_head = str(crime_head).strip()
        if crime_head.startswith("Total"):
            continue

        if category == "IPC":
            for year, cases_col, rate_col in [(2022, 2, 3), (2023, 4, 5), (2024, 6, 7)]:
                cases = _clean_numeric(row.iloc[cases_col]) if cases_col < len(row) else None
                rate = _clean_numeric(row.iloc[rate_col]) if rate_col < len(row) else None
                ipc_cases = _clean_numeric(row.iloc[6]) if year == 2024 and len(row) > 6 else None
                bns_cases = _clean_numeric(row.iloc[7]) if year == 2024 and len(row) > 7 else None
                share = _clean_numeric(row.iloc[10]) if year == 2024 and len(row) > 10 else None
                rows.append({
                    "crime_head": crime_head,
                    "category": category,
                    "year": year,
                    "cases": int(cases) if cases is not None else None,
                    "crime_rate": rate,
                    "ipc_cases": int(ipc_cases) if ipc_cases is not None else None,
                    "bns_cases": int(bns_cases) if bns_cases is not None else None,
                    "share_pct": share,
                    "source_table": filepath.name,
                })
        else:
            for year, cases_col, rate_col in [(2022, 2, 3), (2023, 4, 5), (2024, 6, 7)]:
                cases = _clean_numeric(row.iloc[cases_col]) if cases_col < len(row) else None
                rate = _clean_numeric(row.iloc[rate_col]) if rate_col < len(row) else None
                share = _clean_numeric(row.iloc[8]) if year == 2024 and len(row) > 8 else None
                rows.append({
                    "crime_head": crime_head,
                    "category": category,
                    "year": year,
                    "cases": int(cases) if cases is not None else None,
                    "crime_rate": rate,
                    "ipc_cases": None,
                    "bns_cases": None,
                    "share_pct": share,
                    "source_table": filepath.name,
                })
    return pd.DataFrame(rows)


def parse_city_table(filepath: Path, stat_type: str) -> pd.DataFrame:
    """Parse metropolitan city tables (1B.1, 3B.1, 4B.1, vol2-*)."""
    df = pd.read_excel(filepath, header=None)
    rows = []
    for i in range(3, len(df)):
        row = df.iloc[i]
        sl = row.iloc[0]
        city = row.iloc[1]
        if pd.isna(city) or pd.isna(sl):
            continue
        city = str(city).strip()
        if not city or city.lower() == "nan":
            continue

        state = None
        m = re.search(r"\(([^)]+)\)", city)
        if m:
            state = m.group(1).strip()
            city_clean = city[: m.start()].strip()
        else:
            city_clean = city

        y2022 = _clean_numeric(row.iloc[2]) if len(row) > 2 else None
        y2023 = _clean_numeric(row.iloc[3]) if len(row) > 3 else None

        if stat_type == "overall":
            ipc_2024 = _clean_numeric(row.iloc[4]) if len(row) > 4 else None
            bns_2024 = _clean_numeric(row.iloc[5]) if len(row) > 5 else None
            total_2024 = _clean_numeric(row.iloc[6]) if len(row) > 6 else None
            crime_rate = _clean_numeric(row.iloc[8]) if len(row) > 8 else None
            cs_rate = _clean_numeric(row.iloc[9]) if len(row) > 9 else None
        elif stat_type == "senior":
            ipc_2024 = _clean_numeric(row.iloc[4]) if len(row) > 4 else None
            bns_2024 = _clean_numeric(row.iloc[5]) if len(row) > 5 else None
            total_2024 = _clean_numeric(row.iloc[6]) if len(row) > 6 else None
            crime_rate = None
            cs_rate = _clean_numeric(row.iloc[7]) if len(row) > 7 else None
        else:
            total_2024 = _clean_numeric(row.iloc[4]) if len(row) > 4 else None
            ipc_2024 = bns_2024 = None
            crime_rate = _clean_numeric(row.iloc[6]) if len(row) > 6 else None
            cs_rate = _clean_numeric(row.iloc[7]) if len(row) > 7 else None

        for year, total in [(2022, y2022), (2023, y2023)]:
            if total is not None:
                rows.append({
                    "city": city_clean,
                    "state": state,
                    "year": year,
                    "total_cases": int(total),
                    "ipc_cases": None,
                    "bns_cases": None,
                    "crime_rate": None,
                    "chargesheet_rate": None,
                    "stat_type": stat_type,
                    "source_table": filepath.name,
                })

        if total_2024 is not None:
            rows.append({
                "city": city_clean,
                "state": state,
                "year": 2024,
                "total_cases": int(total_2024),
                "ipc_cases": int(ipc_2024) if ipc_2024 is not None else None,
                "bns_cases": int(bns_2024) if bns_2024 is not None else None,
                "crime_rate": crime_rate,
                "chargesheet_rate": cs_rate,
                "stat_type": stat_type,
                "source_table": filepath.name,
            })
    return pd.DataFrame(rows)


def parse_complaint_table(filepath: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse table_1.1: complaint breakdown + national year-wise incidence."""
    df = pd.read_excel(filepath, header=None)
    complaint_rows = []
    for i in range(3, len(df)):
        row = df.iloc[i]
        sl = row.iloc[0]
        complaint_type = row.iloc[1]
        if pd.isna(complaint_type):
            continue
        complaint_type = str(complaint_type).strip()
        if complaint_type.startswith("Total") or "Crimes under IPC" in complaint_type:
            break
        complaints = _clean_numeric(row.iloc[2])
        firs = _clean_numeric(row.iloc[3])
        online = _clean_numeric(row.iloc[4])
        if complaints is None and firs is None:
            continue
        complaint_rows.append({
            "sl_no": str(sl).strip() if pd.notna(sl) else None,
            "complaint_type": complaint_type,
            "num_complaints": int(complaints) if complaints is not None else None,
            "num_firs": int(firs) if firs is not None else None,
            "num_online_efir": int(online) if online is not None else None,
            "year": 2024,
            "source_table": filepath.name,
        })

    national_rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        year_val = _clean_numeric(row.iloc[1]) if len(row) > 1 else None
        if year_val not in (2022, 2023, 2024):
            continue
        year = int(year_val)
        national_rows.append({
            "year": year,
            "population_lakhs": _clean_numeric(row.iloc[2]),
            "ipc_bns_incidence": int(_clean_numeric(row.iloc[3])) if _clean_numeric(row.iloc[3]) else None,
            "sll_incidence": int(_clean_numeric(row.iloc[4])) if _clean_numeric(row.iloc[4]) else None,
            "total_incidence": int(_clean_numeric(row.iloc[5])) if _clean_numeric(row.iloc[5]) else None,
            "ipc_bns_crime_rate": _clean_numeric(row.iloc[6]),
            "sll_crime_rate": _clean_numeric(row.iloc[7]),
            "total_crime_rate": _clean_numeric(row.iloc[8]),
            "ipc_bns_share_pct": _clean_numeric(row.iloc[9]),
            "source_table": filepath.name,
        })

    return pd.DataFrame(complaint_rows), pd.DataFrame(national_rows)


def parse_economic_headwise(filepath: Path) -> pd.DataFrame:
    """Parse vol2-8b.2 economic crime head-wise for metro cities."""
    df = pd.read_excel(filepath, header=None)
    rows = []
    heads = [
        "Criminal Breach of Trust",
        "Counterfeiting",
        "Forgery, Cheating & Fraud",
    ]
    for i in range(3, len(df)):
        row = df.iloc[i]
        city = row.iloc[1]
        if pd.isna(city):
            continue
        city = str(city).strip()
        state = None
        m = re.search(r"\(([^)]+)\)", city)
        if m:
            state = m.group(1).strip()
            city = city[: m.start()].strip()

        for col_offset, head in enumerate(heads, start=2):
            cases = _clean_numeric(row.iloc[col_offset]) if col_offset < len(row) else None
            if cases is not None:
                rows.append({
                    "city": city,
                    "state": state,
                    "year": 2024,
                    "crime_head": head,
                    "cases": int(cases),
                    "source_table": filepath.name,
                })
    return pd.DataFrame(rows)


TABLE_MAP = {
    "table_1.1.xlsx": ("complaint", {}),
    "table_1.2.xlsx": ("crime_head", {"category": "IPC"}),
    "table_1.3.xlsx": ("crime_head", {"category": "SLL"}),
    "table_1b.1.xlsx": ("city", {"stat_type": "overall"}),
    "table_1b.2.xlsx": ("city", {"stat_type": "sll"}),
    "table_1b.3.xlsx": ("city", {"stat_type": "total_ipc_sll"}),
    "table_3b.1.xlsx": ("city", {"stat_type": "women"}),
    "table_4b.1.xlsx": ("city", {"stat_type": "children"}),
    "vol2-6b.1.xlsx": ("city", {"stat_type": "senior"}),
    "vol2-7b.1.xlsx": ("city", {"stat_type": "sc"}),
    "vol2-7d.1.xlsx": ("city", {"stat_type": "st"}),
    "vol2-8b.1.xlsx": ("city", {"stat_type": "economic"}),
    "vol2-8b.2.xlsx": ("economic_headwise", {}),
    "vol2-9b.1.xlsx": ("city", {"stat_type": "cyber"}),
}


def parse_all_ncrb(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse all NCRB XLSX files in data_dir."""
    crime_stats = []
    city_stats = []
    complaint_stats = None
    national_stats = None
    economic_headwise = []

    parsed_files = []
    skipped_files = []

    all_xlsx = sorted(data_dir.glob("*.xlsx"))
    mapped = set(TABLE_MAP.keys())

    for filename, (table_type, kwargs) in TABLE_MAP.items():
        filepath = data_dir / filename
        if not filepath.exists():
            print(f"  [skip] {filename} not found")
            skipped_files.append(filename)
            continue
        print(f"  Parsing {filename}...")
        parsed_files.append(filename)

        if table_type == "crime_head":
            crime_stats.append(parse_crime_head_table(filepath, **kwargs))
        elif table_type == "city":
            city_stats.append(parse_city_table(filepath, **kwargs))
        elif table_type == "complaint":
            complaints, national = parse_complaint_table(filepath)
            complaint_stats = complaints
            national_stats = national
        elif table_type == "economic_headwise":
            economic_headwise.append(parse_economic_headwise(filepath))

    for f in all_xlsx:
        if f.name not in mapped:
            skipped_files.append(f.name)

    result = {}
    if crime_stats:
        result["ncrb_crime_stats"] = pd.concat(crime_stats, ignore_index=True)
        print(f"  -> {len(result['ncrb_crime_stats'])} crime stat rows")
    if city_stats:
        result["ncrb_city_stats"] = pd.concat(city_stats, ignore_index=True)
        print(f"  -> {len(result['ncrb_city_stats'])} city stat rows")
    if complaint_stats is not None and len(complaint_stats):
        result["ncrb_complaint_stats"] = complaint_stats
        print(f"  -> {len(complaint_stats)} complaint stat rows")
    if national_stats is not None and len(national_stats):
        result["ncrb_national_stats"] = national_stats
        print(f"  -> {len(national_stats)} national stat rows")
    if economic_headwise:
        result["ncrb_economic_headwise"] = pd.concat(economic_headwise, ignore_index=True)
        print(f"  -> {len(result['ncrb_economic_headwise'])} economic headwise rows")

    if "ncrb_city_stats" in result:
        kn = result["ncrb_city_stats"]
        kn_mask = kn["state"].str.contains("Karnataka", case=False, na=False)
        result["karnataka_city_stats"] = kn[kn_mask].copy()
        print(f"  -> {len(result['karnataka_city_stats'])} Karnataka city stat rows")

    print(f"\n  Parsed {len(parsed_files)}/{len(all_xlsx)} XLSX files")
    if skipped_files:
        print(f"  Skipped: {', '.join(skipped_files)}")

    return result
