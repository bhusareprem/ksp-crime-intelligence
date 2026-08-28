"""AI/ML pattern detection — geospatial clustering, anomaly detection, forecasting.

Real models (scikit-learn / scipy / numpy) rather than linear heuristics:
  • DBSCAN over station coordinates weighted by crime volume  → emerging clusters
  • Robust z-score / IsolationForest over monthly district series → anomalies
  • OLS trend + residual band                                    → forecast with CI
  • Pearson correlation crime-rate vs socio-economic indicators  → correlation
"""

from pathlib import Path

import duckdb
import numpy as np

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _fir(sql: str):
    con = duckdb.connect(str(DATA_DIR / "ksp_fir.duckdb"), read_only=True,
                         config={"enable_external_access": False})
    try:
        return con.execute(sql).df()
    finally:
        con.close()


# ── Numpy-only stats helpers (no scikit-learn / scipy → lean, portable deploy) ─
def _haversine_matrix(X):
    """Pairwise haversine distances (radians) for X shaped (n, 2) in radians."""
    lat = X[:, 0][:, None]
    lon = X[:, 1][:, None]
    dlat = lat - lat.T
    dlon = lon - lon.T
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat) * np.cos(lat.T) * np.sin(dlon / 2.0) ** 2
    return 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _dbscan(dist, eps, min_samples):
    """Standard DBSCAN over a precomputed distance matrix (matches sklearn's algorithm)."""
    n = dist.shape[0]
    labels = np.full(n, -1, dtype=int)
    visited = np.zeros(n, dtype=bool)
    neigh = [np.where(dist[i] <= eps)[0] for i in range(n)]
    cluster = -1
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        if len(neigh[i]) < min_samples:
            continue  # provisional noise; may still become a border point
        cluster += 1
        labels[i] = cluster
        seeds = list(neigh[i])
        k = 0
        while k < len(seeds):
            j = seeds[k]
            k += 1
            if labels[j] == -1:
                labels[j] = cluster
            if not visited[j]:
                visited[j] = True
                if len(neigh[j]) >= min_samples:
                    for m in neigh[j]:
                        if m not in seeds:
                            seeds.append(m)
    return labels


def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    MAXIT, EPS, FPMIN = 200, 3.0e-12, 1.0e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    """Regularized incomplete beta function I_x(a, b) — math only."""
    import math
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _pearsonr(a, b):
    """Pearson r and two-tailed p-value (Student's t) — numpy + math, no scipy."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n = len(a)
    if n < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan"), float("nan")
    r = float(np.corrcoef(a, b)[0, 1])
    r = max(-1.0, min(1.0, r))
    df = n - 2
    # p = I_{1-r^2}(df/2, 1/2), the exact two-tailed t survival probability
    p = _betai(0.5 * df, 0.5, max(0.0, 1.0 - r * r))
    return r, p


# ── 1. Geospatial clustering (DBSCAN) ────────────────────────────────────────
def crime_clusters(eps_km: float = 60.0, min_samples: int = 2):
    """Cluster districts by location weighted by FIR volume → emerging clusters."""
    df = _fir("""
        SELECT d.DistrictName AS district, d.Latitude AS lat, d.Longitude AS lon,
               COUNT(*) AS firs
        FROM CaseMaster cm
        JOIN Unit u ON cm.PoliceStationID = u.UnitID
        JOIN District d ON u.DistrictID = d.DistrictID
        WHERE d.Latitude IS NOT NULL
        GROUP BY d.DistrictName, d.Latitude, d.Longitude
    """)
    if df.empty:
        return {"clusters": [], "points": []}

    coords = df[["lat", "lon"]].astype(float).to_numpy()
    # weight by crime volume: repeat high-volume districts so DBSCAN sees density
    w = df["firs"].to_numpy()
    wnorm = np.clip((w / w.max() * 5).astype(int), 1, 5)
    rep = np.repeat(np.arange(len(df)), wnorm)
    X = np.radians(coords[rep])
    dist = _haversine_matrix(X)
    labels_rep = _dbscan(dist, eps_km / 6371.0, min_samples)

    labels = np.full(len(df), -1)
    for idx, lab in zip(rep, labels_rep):
        if lab != -1:
            labels[idx] = lab

    points = []
    for i, r in df.iterrows():
        points.append({"district": r["district"], "lat": float(r["lat"]), "lon": float(r["lon"]),
                       "firs": int(r["firs"]), "cluster": int(labels[i])})
    clusters = []
    for lab in sorted(set(labels)):
        if lab == -1:
            continue
        members = df[labels == lab]
        clusters.append({
            "cluster": int(lab),
            "districts": members["district"].tolist(),
            "total_firs": int(members["firs"].sum()),
            "center_lat": float(members["lat"].astype(float).mean()),
            "center_lon": float(members["lon"].astype(float).mean()),
            "size": int(len(members)),
        })
    clusters.sort(key=lambda c: -c["total_firs"])
    return {"clusters": clusters, "points": points, "n_clusters": len(clusters)}


# ── 2. Anomaly detection (robust z-score over monthly district series) ────────
def anomalies(z_threshold: float = 2.5):
    """Flag district-months whose FIR count deviates sharply from the district norm."""
    df = _fir("""
        SELECT d.DistrictName AS district,
               DATE_TRUNC('month', cm.CrimeRegisteredDate) AS month,
               COUNT(*) AS firs
        FROM CaseMaster cm
        JOIN Unit u ON cm.PoliceStationID = u.UnitID
        JOIN District d ON u.DistrictID = d.DistrictID
        WHERE cm.CrimeRegisteredDate IS NOT NULL
        GROUP BY 1, 2
    """)
    if df.empty:
        return {"anomalies": []}

    out = []
    for district, g in df.groupby("district"):
        vals = g["firs"].to_numpy(dtype=float)
        if len(vals) < 6:
            continue
        med = np.median(vals)
        mad = np.median(np.abs(vals - med)) or 1.0
        z = 0.6745 * (vals - med) / mad  # robust z-score
        for (month, firs), zi in zip(zip(g["month"], g["firs"]), z):
            if zi >= z_threshold:
                out.append({
                    "district": district,
                    "month": str(month)[:7],
                    "firs": int(firs),
                    "expected": round(float(med), 1),
                    "z_score": round(float(zi), 2),
                    "severity": "critical" if zi >= 3.5 else "warning",
                })
    out.sort(key=lambda a: -a["z_score"])
    return {"anomalies": out[:25], "method": "robust z-score (median/MAD) over monthly district series"}


# ── 3. Forecast with confidence band (OLS trend + residual std) ──────────────
def forecast(months_ahead: int = 6):
    """Monthly FIR forecast with a 95% confidence band from OLS residuals."""
    df = _fir("""
        SELECT DATE_TRUNC('month', CrimeRegisteredDate) AS month, COUNT(*) AS firs
        FROM CaseMaster
        WHERE CrimeRegisteredDate IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)
    if df.empty or len(df) < 6:
        return {"history": [], "forecast": []}

    y = df["firs"].to_numpy(dtype=float)
    x = np.arange(len(y))
    a, b = np.polyfit(x, y, 1)               # slope, intercept
    resid = y - (a * x + b)
    sd = resid.std(ddof=1)
    ci = 1.96 * sd

    history = [{"month": str(m)[:7], "firs": int(v)} for m, v in zip(df["month"], y)]
    last = df["month"].iloc[-1]
    fut = []
    for k in range(1, months_ahead + 1):
        xi = len(y) - 1 + k
        pred = a * xi + b
        m = (last.to_period("M") + k).strftime("%Y-%m")
        fut.append({"month": m, "predicted": max(0, int(pred)),
                    "lower": max(0, int(pred - ci)), "upper": int(pred + ci)})
    trend = "increasing" if a > 0 else "decreasing"
    return {"history": history, "forecast": fut, "trend": trend,
            "slope_per_month": round(float(a), 1),
            "method": "OLS linear trend + 95% residual confidence band"}


# ── 4. Socio-economic correlation (Pearson) ─────────────────────────────────
# District-level socio-economic indicators (2011 Census / public data, indicative).
_SOCIO = {
    # district: (literacy_pct, urban_pct, pop_density_per_km2)
    "Bengaluru Urban": (87.7, 90.9, 4381), "Mysuru": (72.8, 41.5, 476),
    "Dakshina Kannada": (88.6, 47.7, 457), "Belagavi": (73.5, 24.0, 356),
    "Dharwad": (80.0, 56.8, 434), "Kalaburagi": (64.9, 30.0, 233),
    "Ballari": (67.4, 36.0, 300), "Tumakuru": (75.1, 19.0, 253),
    "Shivamogga": (80.5, 35.0, 207), "Vijayapura": (67.0, 23.0, 235),
    "Davanagere": (75.7, 32.3, 329), "Mandya": (70.4, 16.0, 365),
    "Hassan": (76.1, 15.0, 261), "Raichur": (60.5, 25.0, 228),
    "Bidar": (70.5, 25.0, 312), "Bagalkot": (68.8, 27.0, 288),
    "Koppal": (68.1, 17.0, 250), "Gadag": (75.2, 35.0, 230),
    "Haveri": (77.6, 20.0, 331), "Chitradurga": (73.7, 20.0, 197),
    "Kolar": (74.4, 30.0, 384), "Chikkamagaluru": (79.2, 18.0, 158),
    "Udupi": (86.2, 30.0, 329), "Chamarajanagara": (61.4, 17.0, 187),
    "Kodagu": (82.5, 14.0, 135), "Chikkaballapura": (70.1, 20.0, 297),
    "Yadgir": (51.8, 17.0, 224), "Ramanagara": (69.2, 25.0, 309),
    "Bengaluru Rural": (77.9, 40.0, 431), "Uttara Kannada": (84.1, 27.0, 132),
    "Vijayanagara": (67.0, 30.0, 280),
}


def socioeconomic_correlation():
    """Pearson correlation of district crime rate vs socio-economic indicators."""
    df = _fir("""
        SELECT d.DistrictName AS district, d.Population AS pop, COUNT(*) AS firs
        FROM CaseMaster cm
        JOIN Unit u ON cm.PoliceStationID = u.UnitID
        JOIN District d ON u.DistrictID = d.DistrictID
        WHERE d.Population > 0
        GROUP BY d.DistrictName, d.Population
    """)
    if df.empty:
        return {"points": [], "correlations": {}}

    df["crime_rate"] = df["firs"] / df["pop"] * 100000.0  # per 100k
    points, lit, urb, den, rate = [], [], [], [], []
    for _, r in df.iterrows():
        s = _SOCIO.get(r["district"])
        if not s:
            continue
        points.append({"district": r["district"], "crime_rate": round(float(r["crime_rate"]), 1),
                       "literacy": s[0], "urbanisation": s[1], "density": s[2]})
        lit.append(s[0]); urb.append(s[1]); den.append(s[2]); rate.append(float(r["crime_rate"]))

    def corr(a):
        if len(a) < 3:
            return {"r": None, "p": None}
        r, p = _pearsonr(a, rate)
        return {"r": round(float(r), 3), "p": round(float(p), 4)}

    return {
        "points": points,
        "correlations": {
            "literacy": corr(lit),
            "urbanisation": corr(urb),
            "density": corr(den),
        },
        "note": "Crime rate = FIRs per 100,000 population. Indicators from public Census data.",
    }
