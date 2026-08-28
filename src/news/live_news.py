"""Live crime-news ingestion — Google News RSS → geolocated incidents.

Fetches recent Karnataka crime headlines, extracts the district and crime type,
geolocates each to district coordinates, and returns structured incidents that
the dashboard overlays on the hotspot map and correlates with historical data.
No API key required.
"""

import re
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb

RSS_TEMPLATE = (
    "https://news.google.com/rss/search?"
    "q=Karnataka+(crime+OR+murder+OR+theft+OR+robbery+OR+arrested+OR+police+OR+fraud)"
    "+when:{window}&hl=en-IN&gl=IN&ceid=IN:en"
)
# Ask for the last 24h first so today's stories are actually in the payload, then
# top up from a wider window if the day has been quiet. Google caps the feed at
# roughly 100 items, so a 7d-only query can push today's news out entirely.
RSS_WINDOWS = ("1d", "3d", "7d")
RSS_URL = RSS_TEMPLATE.format(window="7d")   # kept for backwards compatibility

# City / common-spelling aliases → canonical district name (as stored in the DB).
_ALIASES = {
    "bangalore": "Bengaluru Urban", "bengaluru": "Bengaluru Urban", "benglooru": "Bengaluru Urban",
    "mysore": "Mysuru", "mysuru": "Mysuru",
    "mangalore": "Dakshina Kannada", "mangaluru": "Dakshina Kannada", "dakshina kannada": "Dakshina Kannada",
    "hubli": "Dharwad", "hubballi": "Dharwad", "dharwad": "Dharwad",
    "belgaum": "Belagavi", "belagavi": "Belagavi",
    "gulbarga": "Kalaburagi", "kalaburagi": "Kalaburagi",
    "bijapur": "Vijayapura", "vijayapura": "Vijayapura",
    "bellary": "Ballari", "ballari": "Ballari",
    "shimoga": "Shivamogga", "shivamogga": "Shivamogga",
    "tumkur": "Tumakuru", "tumakuru": "Tumakuru",
    "hospet": "Vijayanagara", "vijayanagara": "Vijayanagara",
    "manipal": "Udupi", "udupi": "Udupi",
    "bagalkot": "Bagalkot", "bagalkote": "Bagalkot",
    "chikmagalur": "Chikkamagaluru", "chikkamagaluru": "Chikkamagaluru",
    "gadag": "Gadag", "haveri": "Haveri", "koppal": "Koppal", "raichur": "Raichur",
    "bidar": "Bidar", "yadgir": "Yadgir", "kolar": "Kolar", "hassan": "Hassan",
    "mandya": "Mandya", "davanagere": "Davanagere", "davangere": "Davanagere",
    "chitradurga": "Chitradurga", "kodagu": "Kodagu", "madikeri": "Kodagu",
    "chamarajanagar": "Chamarajanagara", "chamarajanagara": "Chamarajanagara",
    "ramanagara": "Ramanagara", "ramnagar": "Ramanagara",
    "chikkaballapur": "Chikkaballapura", "chikballapur": "Chikkaballapura",
    "uttara kannada": "Uttara Kannada", "karwar": "Uttara Kannada", "sirsi": "Uttara Kannada",
}

# Crime type → (keywords, severity)
_CRIME_RULES = [
    ("Murder",         ["murder", "killed", "stabbed", "shot dead", "homicide", "found dead", "hacked to death", "beaten to death"], "critical"),
    ("Sexual Assault", ["rape", "molest", "sexual assault", "pocso", "gang-rape", "gangrape"], "critical"),
    ("Kidnapping",     ["kidnap", "abduct", "missing", "ransom"], "critical"),
    ("Riot / Communal",["riot", "communal", "mob ", "clash", "stone pelting", "curfew"], "critical"),
    ("Drugs / NDPS",   ["drug", "ganja", "narcotic", "ndps", "peddler", "mdma", "cocaine"], "high"),
    ("Assault",        ["assault", "attack", "beaten", "stab", "acid attack"], "high"),
    ("Robbery",        ["robbery", "robbed", "loot", "dacoity", "snatch", "snatching", "chain"], "high"),
    ("Cyber / Fraud",  ["cyber", "fraud", "scam", "cheat", "phishing", "otp", "online", "ponzi", "extortion", "honeytrap"], "medium"),
    ("Theft / Burglary",["theft", "stolen", "burglary", "burgle", "housebreak", "shoplift"], "medium"),
]

_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL = 60  # 1 minute — fresh headlines without hammering the RSS feed


def _pub_ts(pub: str) -> float:
    """RFC-822 pubDate → epoch seconds. 0.0 when unparseable, so it sorts last."""
    if not pub:
        return 0.0
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _district_coords(data_dir: Path) -> dict:
    path = data_dir / "ksp_fir.duckdb"
    coords = {}
    try:
        con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
        try:
            for name, lat, lon in con.execute(
                "SELECT DistrictName, Latitude, Longitude FROM District"
            ).fetchall():
                if lat is not None and lon is not None:
                    coords[name] = (float(lat), float(lon))
        finally:
            con.close()
    except Exception:
        pass
    return coords


def _match_district(text: str, coords: dict):
    low = text.lower()
    # direct district-name hit first
    for name in coords:
        if name.lower() in low:
            return name
    # then city / alias
    for alias, dist in _ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            if dist in coords:
                return dist
    return None


def _match_crime(text: str):
    low = text.lower()
    for label, keys, sev in _CRIME_RULES:
        for k in keys:
            if k in low:
                return label, sev
    return "General", "low"


def _clean_source(title: str):
    # Google News titles end with " - Source Name"
    if " - " in title:
        head, src = title.rsplit(" - ", 1)
        return head.strip(), src.strip()
    return title.strip(), ""


def fetch_crime_news(data_dir: Path, max_items: int = 40, force: bool = False) -> dict:
    now = time.time()
    if not force and _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"]

    coords = _district_coords(data_dir)
    incidents, feed = [], []
    try:
        items, seen_titles, last_err = [], set(), None
        for window in RSS_WINDOWS:
            try:
                req = urllib.request.Request(RSS_TEMPLATE.format(window=window),
                                             headers={"User-Agent": "Mozilla/5.0"})
                raw = urllib.request.urlopen(req, timeout=15, context=_ctx()).read()
                for it in ET.fromstring(raw).findall(".//item"):
                    t = (it.findtext("title") or "").strip()
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        items.append(it)
            except Exception as e:
                last_err = e
            if len(items) >= max_items:
                break
        if not items and last_err:
            raise last_err
        items = items[:max_items]
        for it in items:
            title_raw = (it.findtext("title") or "").strip()
            if not title_raw:
                continue
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            headline, source = _clean_source(title_raw)
            # Google occasionally emits section stubs ("India News") whose title is
            # just a masthead. They carry no incident and look broken on a wall display.
            if len(headline) < 25 or headline.strip().lower() == (source or "").strip().lower():
                continue
            district = _match_district(title_raw, coords)
            crime, sev = _match_crime(title_raw)
            row = {
                "headline": headline,
                "source": source,
                "url": link,
                "published": pub,
                "published_ts": _pub_ts(pub),
                "district": district,
                "crime_type": crime,
                "severity": sev,
            }
            feed.append(row)
            if district and district in coords:
                lat, lon = coords[district]
                incidents.append({**row, "lat": lat, "lon": lon})

        # Google returns these in relevance order, which buries today's stories
        # under week-old ones. An officer wants newest first.
        feed.sort(key=lambda r: r["published_ts"], reverse=True)
        incidents.sort(key=lambda r: r["published_ts"], reverse=True)
    except Exception as e:
        result = {"incidents": [], "feed": [], "error": str(e), "fetched_at": now}
        return result

    result = {
        "incidents": incidents,
        "feed": feed,
        "total": len(feed),
        "geolocated": len(incidents),
        "fetched_at": now,
    }
    _CACHE["data"], _CACHE["ts"] = result, now
    return result


def correlate_with_hotspots(incidents: list, top_districts: list) -> list:
    """Return callouts where live incidents land in known historical hotspots."""
    top_set = {d for d in top_districts}
    counts = {}
    for inc in incidents:
        d = inc["district"]
        if d in top_set:
            counts[d] = counts.get(d, 0) + 1
    callouts = []
    for d, c in sorted(counts.items(), key=lambda x: -x[1]):
        rank = top_districts.index(d) + 1
        callouts.append({"district": d, "live_count": c, "hotspot_rank": rank})
    return callouts
