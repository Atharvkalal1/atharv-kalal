"""Shared constants, loaders and the reference model learned from CLEAN data (no injector knowledge anywhere)."""
from __future__ import annotations
import json, math, re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).parent / "data"
REAL_FILE, SYNTH_FILE = DATA / "nyc311_2023.jsonl", DATA / "synthetic_nyc311_2023.jsonl"
COLUMNS = ["unique_key", "created_date", "closed_date", "agency", "agency_name", "complaint_type", "descriptor",
           "incident_zip", "borough", "status", "resolution_description", "latitude", "longitude"]
REQUIRED = {"unique_key": int, "created_date": str, "agency": str, "complaint_type": str, "descriptor": str,
            "borough": str, "status": str, "latitude": float, "longitude": float}
OPTIONAL = {"closed_date": str, "incident_zip": str, "resolution_description": str, "agency_name": str}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")
NYC_BBOX = (40.49, 40.92, -74.28, -73.68)       # lat_min, lat_max, lon_min, lon_max (generous NYC bounding box)
# Official ZIP ranges per borough (USPS): used as a *declarative* lookup by the rules family
ZIP_RANGES = {"MANHATTAN": [(10001, 10282)], "STATEN ISLAND": [(10301, 10314)], "BRONX": [(10451, 10475)],
              "BROOKLYN": [(11201, 11256)], "QUEENS": [(11004, 11109), (11351, 11697)]}


def load(path=None):
    p = Path(path) if path else (REAL_FILE if REAL_FILE.exists() else SYNTH_FILE)
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows, ("REAL (NYC Open Data)" if p == REAL_FILE else "SYNTHETIC (run fetch_nyc311.py for real data)")


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", ""))
    except ValueError:
        return None


def zip_borough(z):
    try:
        z = int(str(z)[:5])
    except ValueError:
        return None
    return next((b for b, rs in ZIP_RANGES.items() if any(a <= z <= c for a, c in rs)), None)


def tokens(text):
    return re.findall(r"[a-z]{3,}", str(text).lower())


def signature(v):
    """Format signature of a value: 'Aa9' classes with runs collapsed -> catches format drift without knowing the format."""
    if v is None: return "NULL"
    s = re.sub(r"[A-Za-z]+", "A", re.sub(r"\d+", "9", str(v)))
    return f"{type(v).__name__}:{s[:24]}"


class Reference:
    """Statistics learned from a clean reference batch. Used ONLY by the statistical family."""
    def __init__(self, rows):
        n = len(rows); self.n = n
        self.cols = Counter(k for r in rows for k in r)
        self.col_set = {c for c, k in self.cols.items() if k >= 0.9 * n}
        self.sig = {c: Counter(signature(r.get(c)) for r in rows) for c in COLUMNS}
        self.null_rate = {(a, c): 0 for a in set(r.get("agency") for r in rows) for c in COLUMNS}
        by_ag = defaultdict(list)
        for r in rows: by_ag[r.get("agency")].append(r)
        self.agency_n = {a: len(v) for a, v in by_ag.items()}
        for a, v in by_ag.items():
            for c in COLUMNS: self.null_rate[(a, c)] = sum(x.get(c) is None for x in v) / len(v)
        self.zip_boro = defaultdict(Counter); self.cdesc = defaultdict(Counter); self.stat_tok = defaultdict(Counter)
        self.stat_n = Counter(); self.vocab = set(); dur = defaultdict(list)
        lats, lons = [], []
        for r in rows:
            if r.get("incident_zip") and r.get("borough"): self.zip_boro[str(r["incident_zip"])][r["borough"]] += 1
            self.cdesc[r.get("complaint_type")][r.get("descriptor")] += 1
            st = "closed" if r.get("status") == "Closed" else "open"
            self.stat_n[st] += 1
            for t in tokens(r.get("resolution_description")): self.stat_tok[st][t] += 1; self.vocab.add(t)
            a, b = parse_ts(r.get("created_date")), parse_ts(r.get("closed_date"))
            if a and b: dur[r.get("agency")].append(math.asinh((b - a).total_seconds() / 3600))
            if isinstance(r.get("latitude"), (int, float)) and isinstance(r.get("longitude"), (int, float)) and r["latitude"]:
                lats.append(r["latitude"]); lons.append(r["longitude"])
        self.dur = {a: (_med(v), _mad(v)) for a, v in dur.items() if len(v) >= 20}
        self.lat, self.lon = (_med(lats), _mad(lats)), (_med(lons), _mad(lons))
        self.gap_median = None


def _med(v):
    s = sorted(v); return s[len(s) // 2] if s else 0.0


def _mad(v):
    m = _med(v); return max(1e-6, 1.4826 * _med([abs(x - m) for x in v]))
