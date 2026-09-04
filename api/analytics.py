"""Analytics endpoints — KSP FIR Database (CaseMaster / Accused / Unit schema)."""

import sqlite3
from pathlib import Path

import duckdb
import pandas as pd
from fastapi import APIRouter

router = APIRouter(tags=["analytics"])

DATA_DIR: Path = Path(__file__).parent.parent / "data"


def _fir_path() -> Path:
    """Resolve path to the active FIR database."""
    p = DATA_DIR / "ksp_fir.duckdb"
    if p.exists():
        return p
    # Legacy fallback
    for candidate in [DATA_DIR / "unified" / "criminal.db", DATA_DIR / "criminal.db"]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No FIR database found in data/")


# DuckDB refuses a second connection to the same file under a different config,
# and every other module opens with external access disabled. Mismatching here
# made concurrent ML/analytics calls raise into a bare except and silently return
# empty results (the AI Brief showed "0 ML Clusters"). Keep this identical to
# DatabaseManager._DUCKDB_SAFE_CONFIG everywhere.
_DUCKDB_SAFE_CONFIG = {"enable_external_access": False}


def _fir(sql: str) -> list[dict]:
    """Execute against the FIR DuckDB (ksp_fir.duckdb)."""
    conn = duckdb.connect(str(_fir_path()), read_only=True, config=_DUCKDB_SAFE_CONFIG)
    try:
        df = conn.execute(sql).df()
    finally:
        conn.close()
    return df.to_dict(orient="records")


def _ksp(sql: str) -> list[dict]:
    path = DATA_DIR / "unified" / "ksp_crime.db"
    if not path.exists():
        path = DATA_DIR / "ksp_crime.db"
    conn = sqlite3.connect(path)
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df.to_dict(orient="records")


def _cases(sql: str) -> list[dict]:
    path = DATA_DIR / "unified" / "cases.db"
    if not path.exists():
        path = DATA_DIR / "cases.db"
    conn = duckdb.connect(str(path), read_only=True, config=_DUCKDB_SAFE_CONFIG)
    try:
        df = conn.execute(sql).df()
    finally:
        conn.close()
    return df.to_dict(orient="records")


# ── Join shorthand used across queries ────────────────────────────────────────
_FIR_GEO = """
    FROM CaseMaster cm
    JOIN Unit u ON cm.PoliceStationID = u.UnitID
    JOIN District d ON u.DistrictID = d.DistrictID
"""
_FIR_GEO_CSH = _FIR_GEO + "JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/trends")
def crime_trends():
    """Year-wise crime trends from FIR data."""
    try:
        rows = _fir("""
            WITH base AS (
                SELECT EXTRACT(YEAR FROM CrimeRegisteredDate)::INT AS yr,
                       CaseMasterID
                FROM CaseMaster
                WHERE EXTRACT(YEAR FROM CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
            ),
            arr AS (
                SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS yr,
                       COUNT(DISTINCT ar.AccusedMasterID) AS total_arrests
                FROM ArrestSurrender ar
                JOIN CaseMaster cm ON ar.CaseMasterID = cm.CaseMasterID
                WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
                GROUP BY 1
            ),
            vic AS (
                SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS yr,
                       COUNT(*) AS total_victims
                FROM Victim v
                JOIN CaseMaster cm ON v.CaseMasterID = cm.CaseMasterID
                WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
                GROUP BY 1
            ),
            chs AS (
                SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS yr,
                       COUNT(DISTINCT cs.CaseMasterID) AS total_chargesheeted
                FROM ChargesheetDetails cs
                JOIN CaseMaster cm ON cs.CaseMasterID = cm.CaseMasterID
                WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
                GROUP BY 1
            )
            SELECT b.yr AS year, COUNT(*) AS total_firs,
                   COALESCE(v.total_victims, 0) AS total_victims,
                   COALESCE(a.total_arrests, 0) AS total_arrests,
                   COALESCE(c.total_chargesheeted, 0) AS total_chargesheeted
            FROM base b
            LEFT JOIN vic v ON v.yr = b.yr
            LEFT JOIN arr a ON a.yr = b.yr
            LEFT JOIN chs c ON c.yr = b.yr
            GROUP BY b.yr, v.total_victims, a.total_arrests, c.total_chargesheeted
            ORDER BY b.yr
        """)
    except Exception:
        rows = []
    return {"data": rows}


@router.get("/crime-type-trends")
def crime_type_trends():
    """Top crime types trend over years."""
    try:
        rows = _fir(f"""
            SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                   csh.CrimeHeadName AS crime_type, COUNT(*) AS count
            {_FIR_GEO_CSH}
            WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
            GROUP BY 1, 2 ORDER BY 1, 3 DESC
        """)
    except Exception:
        rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        return {"labels": [], "datasets": []}
    top_types = df.groupby("crime_type")["count"].sum().nlargest(8).index.tolist()
    df = df[df["crime_type"].isin(top_types)]
    years = sorted(df["year"].unique().tolist())
    colors = ["#ef4444","#f97316","#eab308","#22c55e","#06b6d4","#3b82f6","#8b5cf6","#ec4899"]
    datasets = []
    for i, ct in enumerate(top_types):
        sub = df[df["crime_type"] == ct].set_index("year")["count"]
        datasets.append({
            "label": ct,
            "data": [int(sub.get(y, 0)) for y in years],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)] + "33",
        })
    return {"labels": years, "datasets": datasets}


@router.get("/hotspots")
def hotspots():
    """District-wise crime hotspot data with lat/lon from new FIR DB."""
    try:
        rows = _fir(f"""
            SELECT d.DistrictName AS district,
                   d.Latitude AS latitude, d.Longitude AS longitude,
                   COUNT(*) AS total_firs,
                   SUM(CASE WHEN cm.CaseStatusID IN (3,4,5,6) THEN 1 ELSE 0 END) AS solved,
                   d.Population AS population
            {_FIR_GEO}
            GROUP BY d.DistrictID, d.DistrictName, d.Latitude, d.Longitude, d.Population
            ORDER BY total_firs DESC
        """)
    except Exception:
        rows = []
    return {"data": rows}


@router.get("/district-breakdown")
def district_breakdown():
    """Top districts by FIR count."""
    try:
        rows = _fir(f"""
            WITH dist_firs AS (
                SELECT d.DistrictName AS district,
                       COUNT(DISTINCT cm.CaseMasterID) AS firs
                {_FIR_GEO}
                GROUP BY d.DistrictName
            ),
            dist_vic AS (
                SELECT d.DistrictName AS district, COUNT(*) AS victims
                {_FIR_GEO}
                JOIN Victim v ON v.CaseMasterID = cm.CaseMasterID
                GROUP BY d.DistrictName
            ),
            dist_arr AS (
                SELECT d.DistrictName AS district,
                       COUNT(DISTINCT ar.AccusedMasterID) AS arrests
                {_FIR_GEO}
                JOIN ArrestSurrender ar ON ar.CaseMasterID = cm.CaseMasterID
                GROUP BY d.DistrictName
            )
            SELECT f.district, f.firs,
                   COALESCE(v.victims, 0) AS victims,
                   COALESCE(a.arrests, 0) AS arrests
            FROM dist_firs f
            LEFT JOIN dist_vic v ON v.district = f.district
            LEFT JOIN dist_arr a ON a.district = f.district
            ORDER BY f.firs DESC LIMIT 20
        """)
    except Exception:
        rows = []
    return {"data": rows}


@router.get("/network")
def criminal_network():
    """Criminal co-accused network — accused in gang or multi-accused FIRs."""
    # Step 1: nodes — gang members + accused from top multi-accused FIRs
    try:
        nodes_raw = _fir("""
            WITH gang_accused AS (
                SELECT DISTINCT agl.AccusedMasterID
                FROM AccusedGangLink agl
            ),
            top_cases AS (
                SELECT CaseMasterID
                FROM Accused
                GROUP BY CaseMasterID
                HAVING COUNT(*) >= 4
                -- CaseMasterID breaks the tie on COUNT(*): without it the 40
                -- seed cases differ run to run and the whole graph changes.
                ORDER BY COUNT(*) DESC, CaseMasterID
                LIMIT 40
            ),
            seed_ids AS (
                SELECT AccusedMasterID FROM gang_accused
                UNION
                SELECT a.AccusedMasterID FROM Accused a JOIN top_cases tc ON a.CaseMasterID = tc.CaseMasterID
            ),
            name_firs AS (
                SELECT AccusedName, COUNT(DISTINCT CaseMasterID) AS n
                FROM Accused WHERE AccusedName IS NOT NULL
                GROUP BY AccusedName
            )
            SELECT a.AccusedMasterID AS id,
                   a.AccusedName     AS name,
                   a.AgeYear         AS age,
                   a.District        AS district,
                   om.OccupationName AS occupation,
                   CASE WHEN ga.AccusedMasterID IS NOT NULL THEN 1 ELSE 0 END AS in_gang,
                   COALESCE(nf.n, 1) AS fir_count
            FROM Accused a
            JOIN seed_ids s ON a.AccusedMasterID = s.AccusedMasterID
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            LEFT JOIN gang_accused ga ON ga.AccusedMasterID = a.AccusedMasterID
            LEFT JOIN name_firs nf ON nf.AccusedName = a.AccusedName
            WHERE a.AccusedName IS NOT NULL
            -- Without an ORDER BY, DuckDB is free to return any 150 of the seed
            -- rows, so the graph redrew with different people on every load and
            -- a demo could not be repeated. Ranking by prior count also puts the
            -- most connected offenders on screen, which is the point of the view.
            ORDER BY fir_count DESC, a.AccusedName, a.AccusedMasterID
            LIMIT 150
        """)
    except Exception:
        return {"nodes": [], "edges": []}

    if not nodes_raw:
        return {"nodes": [], "edges": []}

    top_ids = [r["id"] for r in nodes_raw]
    id_list = ",".join(str(i) for i in top_ids)

    # Step 2: edges — co-accused in same FIR (both must be in our node set)
    try:
        edges_raw = _fir(f"""
            SELECT a1.AccusedMasterID AS src, a2.AccusedMasterID AS tgt, 1 AS weight
            FROM Accused a1
            JOIN Accused a2
              ON a1.CaseMasterID = a2.CaseMasterID
             AND a1.AccusedMasterID < a2.AccusedMasterID
            WHERE a1.AccusedMasterID IN ({id_list})
              AND a2.AccusedMasterID IN ({id_list})
            ORDER BY src, tgt
            LIMIT 500
        """)
    except Exception:
        edges_raw = []

    # Step 3: also add gang co-membership edges (same gang = always connected)
    try:
        gang_edges_raw = _fir(f"""
            SELECT agl1.AccusedMasterID AS src, agl2.AccusedMasterID AS tgt, 2 AS weight
            FROM AccusedGangLink agl1
            JOIN AccusedGangLink agl2
              ON agl1.GangID = agl2.GangID
             AND agl1.AccusedMasterID < agl2.AccusedMasterID
            WHERE agl1.AccusedMasterID IN ({id_list})
              AND agl2.AccusedMasterID IN ({id_list})
            ORDER BY src, tgt
            LIMIT 300
        """)
    except Exception:
        gang_edges_raw = []

    # Accused holds one row per case, so the same person arrives as several ids.
    # Collapse them onto one node per person, otherwise the graph draws the same
    # offender repeatedly and splits their links across the duplicates.
    rep: dict[str, int] = {}
    alias: dict[int, int] = {}
    unique_nodes = []
    for r in nodes_raw:
        key = (r["name"] or "").strip().lower()
        if key in rep:
            alias[r["id"]] = rep[key]
            continue
        rep[key] = r["id"]
        alias[r["id"]] = r["id"]
        unique_nodes.append(r)

    # Merge edges onto the collapsed ids, keep max weight for duplicates
    edge_map: dict[tuple, float] = {}
    for r in edges_raw + gang_edges_raw:
        src, tgt = alias.get(r["src"], r["src"]), alias.get(r["tgt"], r["tgt"])
        if src == tgt:
            continue
        key = (src, tgt) if src < tgt else (tgt, src)
        edge_map[key] = max(edge_map.get(key, 0), float(r["weight"] or 1))

    # Count connections per node for risk scoring
    conn_count: dict = {}
    for (src, tgt) in edge_map:
        conn_count[src] = conn_count.get(src, 0) + 1
        conn_count[tgt] = conn_count.get(tgt, 0) + 1

    nodes = [
        {
            "id": r["id"],
            "label": r["name"] or f"Accused-{r['id']}",
            "risk": "high" if conn_count.get(r["id"], 0) >= 5 else (
                    "medium" if conn_count.get(r["id"], 0) >= 2 else "low"),
            "score": float(conn_count.get(r["id"], 1)),
            "district": r["district"] or "Unknown",
            "firs": int(r["fir_count"]),
            "occupation": r["occupation"] or "",
            "age": int(r["age"] or 0),
            "in_gang": bool(r["in_gang"]),
        }
        for r in unique_nodes
    ]
    edges = [
        {"from": src, "to": tgt, "weight": round(w, 2)}
        for (src, tgt), w in edge_map.items()
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/predictions")
def predictions():
    """Trend-based predictions for next year."""
    try:
        rows = _fir("""
            SELECT EXTRACT(YEAR FROM CrimeRegisteredDate)::INT AS year,
                   COUNT(*) AS count
            FROM CaseMaster
            WHERE EXTRACT(YEAR FROM CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
            GROUP BY 1 ORDER BY 1
        """)
    except Exception:
        rows = []

    if len(rows) < 2:
        return {"predictions": [], "message": "Insufficient data"}

    years = [r["year"] for r in rows]
    counts = [r["count"] for r in rows]
    n = len(counts)
    avg_delta = (counts[-1] - counts[0]) / max(n - 1, 1)
    next_year = years[-1] + 1
    predicted = int(counts[-1] + avg_delta)
    trend = "increasing" if avg_delta > 0 else "decreasing"

    try:
        type_rows = _fir(f"""
            SELECT csh.CrimeHeadName AS crime_type,
                   EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                   COUNT(*) AS count
            {_FIR_GEO_CSH}
            WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT BETWEEN 2020 AND 2024
            GROUP BY 1, 2 ORDER BY 1, 3 DESC
        """)
    except Exception:
        type_rows = []

    df = pd.DataFrame(type_rows)
    crime_preds = []
    if not df.empty:
        top5 = df.groupby("crime_type")["count"].sum().nlargest(5).index.tolist()
        for ct in top5:
            sub = df[df["crime_type"] == ct].sort_values("year")
            if len(sub) < 2:
                continue
            vals = sub["count"].tolist()
            delta = (vals[-1] - vals[0]) / max(len(vals) - 1, 1)
            crime_preds.append({
                "crime_type": ct,
                "predicted_count": int(vals[-1] + delta),
                "trend": "up" if delta > 0 else "down",
                "change_pct": round(delta / max(vals[-1], 1) * 100, 1),
            })

    return {
        "next_year": next_year,
        "predicted_total_firs": predicted,
        "trend": trend,
        "historical": [{"year": r["year"], "count": r["count"]} for r in rows],
        "crime_type_predictions": crime_preds,
    }


@router.get("/behavioral-profile")
def behavioral_profile():
    """Accused demographic profile aggregates."""
    try:
        rows = _fir("""
            SELECT COUNT(*) AS total_accused,
                   ROUND(AVG(a.AgeYear), 1) AS avg_age,
                   ROUND(SUM(CASE WHEN a.GenderID = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS male_pct,
                   ROUND(SUM(CASE WHEN a.GenderID = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS female_pct,
                   ROUND(SUM(CASE WHEN cm.GravityOffenceID = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS heinous_pct,
                   ROUND(SUM(CASE WHEN cm.CaseCategoryID = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS fir_pct
            FROM Accused a
            JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
        """)
        occ_rows = _fir("""
            SELECT om.OccupationName AS occupation, COUNT(*) AS count
            FROM Accused a
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            GROUP BY om.OccupationName ORDER BY count DESC LIMIT 10
        """)
        religion_rows = _fir("""
            SELECT rm.ReligionName AS religion, COUNT(*) AS count
            FROM Accused a
            LEFT JOIN ReligionMaster rm ON a.ReligionID = rm.ReligionID
            GROUP BY rm.ReligionName ORDER BY count DESC
        """)
        # Day-of-week crime pattern — DAYNAME() returns 'Sunday'..'Saturday',
        # which the frontend chart matches by name.
        day_rows = _fir("""
            SELECT DAYNAME(CrimeRegisteredDate) AS day_of_week, COUNT(*) AS count
            FROM CaseMaster
            WHERE CrimeRegisteredDate IS NOT NULL
            GROUP BY DAYNAME(CrimeRegisteredDate)
        """)
    except Exception as e:
        return {"summary": {}, "by_occupation": [], "by_religion": [], "by_day": [], "error": str(e)}

    return {
        "summary": rows[0] if rows else {},
        "by_occupation": occ_rows,
        "by_religion": religion_rows,
        "by_day": day_rows,
    }


@router.get("/alerts")
def crime_alerts():
    """Proactive crime alerts — districts with anomalous spikes vs prior 90-day period."""
    try:
        rows = _fir("""
            WITH max_date AS (
                SELECT MAX(CrimeRegisteredDate) AS md FROM CaseMaster
            ),
            recent AS (
                SELECT d.DistrictName AS district,
                       COALESCE(csh.CrimeHeadName, 'General Crime') AS crime_type,
                       COUNT(*) AS cnt
                FROM CaseMaster cm
                JOIN Unit u ON cm.PoliceStationID = u.UnitID
                JOIN District d ON u.DistrictID = d.DistrictID
                LEFT JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
                CROSS JOIN max_date md
                WHERE cm.CrimeRegisteredDate >= md.md - INTERVAL '90 days'
                GROUP BY d.DistrictName, csh.CrimeHeadName
            ),
            prior AS (
                SELECT d.DistrictName AS district,
                       COALESCE(csh.CrimeHeadName, 'General Crime') AS crime_type,
                       COUNT(*) AS cnt
                FROM CaseMaster cm
                JOIN Unit u ON cm.PoliceStationID = u.UnitID
                JOIN District d ON u.DistrictID = d.DistrictID
                LEFT JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
                CROSS JOIN max_date md
                WHERE cm.CrimeRegisteredDate >= md.md - INTERVAL '180 days'
                  AND cm.CrimeRegisteredDate <  md.md - INTERVAL '90 days'
                GROUP BY d.DistrictName, csh.CrimeHeadName
            )
            SELECT r.district, r.crime_type,
                   r.cnt  AS recent_count,
                   COALESCE(p.cnt, 0) AS prior_count,
                   ROUND(
                       (r.cnt - COALESCE(p.cnt, 1)) * 100.0 / GREATEST(COALESCE(p.cnt, 1), 1),
                   1) AS change_pct
            FROM recent r
            LEFT JOIN prior p ON r.district = p.district AND r.crime_type = p.crime_type
            WHERE r.cnt >= 5
              AND (r.cnt - COALESCE(p.cnt, 1)) * 100.0 / GREATEST(COALESCE(p.cnt, 1), 1) > 20
            ORDER BY change_pct DESC
            LIMIT 20
        """)
    except Exception as e:
        return {"alerts": [], "error": str(e)}

    alerts = []
    for r in rows:
        pct = float(r.get("change_pct") or 0)
        alerts.append({
            "district": r["district"],
            "crime_type": r["crime_type"],
            "recent_count": int(r["recent_count"]),
            "prior_count": int(r["prior_count"]),
            "change_pct": round(pct, 1),
            "severity": "critical" if pct >= 50 else "warning",
            "period": "last 90 days vs prior 90 days",
        })
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/cases-summary")
def cases_summary():
    """Court case disposition summary (from cases.db) + FIR status overview."""
    # FIR status from new DB
    try:
        fir_status = _fir("""
            SELECT csm.CaseStatusName AS status, COUNT(*) AS count
            FROM CaseMaster cm
            JOIN CaseStatusMaster csm ON cm.CaseStatusID = csm.CaseStatusID
            GROUP BY csm.CaseStatusName ORDER BY count DESC
        """)
    except Exception:
        fir_status = []

    # Court outcomes from legacy cases.db if available
    try:
        court_rows = _cases("""
            SELECT disp_name_s AS disposition, COUNT(*) AS count,
                   ROUND(AVG(case_duration_days), 1) AS avg_days
            FROM cases WHERE disp_name_s IS NOT NULL
            GROUP BY disp_name_s ORDER BY count DESC LIMIT 15
        """)
        yearly = _cases("""
            SELECT year, COUNT(*) AS total,
                   SUM(CASE WHEN disp_name_s ILIKE '%convict%' THEN 1 ELSE 0 END) AS convictions,
                   SUM(CASE WHEN disp_name_s ILIKE '%acquit%' THEN 1 ELSE 0 END) AS acquittals
            FROM cases GROUP BY year ORDER BY year
        """)
    except Exception:
        court_rows, yearly = [], []

    return {
        "fir_status": fir_status,
        "dispositions": court_rows,
        "yearly": yearly,
    }
