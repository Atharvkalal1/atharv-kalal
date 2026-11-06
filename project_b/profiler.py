"""Task 1: profile the raw data for pre-existing quality problems (counts + examples). Works on real data when
data/nyc311_2023.jsonl exists, else on the SYNTHETIC stand-in (whose 'findings' are seeded and say nothing about real NYC 311)."""
import json, re
from collections import Counter
from project_b.common import load, parse_ts, zip_borough, NYC_BBOX, COLUMNS, ISO
from project_b.detectors.rules import PHONE, EMAIL, SSN


def profile_raw_data(write=True):
    rows, src = load(); n = len(rows); P, ex = Counter(), {}
    def hit(k, r, **kw): P[k] += 1; ex.setdefault(k, kw or {"unique_key": r.get("unique_key")})
    keys = Counter(r["unique_key"] for r in rows)
    for r in rows:
        a, b = parse_ts(r.get("created_date")), parse_ts(r.get("closed_date"))
        if a and b and b < a: hit("closed_before_created", r, created=r["created_date"], closed=r["closed_date"])
        if r.get("status") == "Closed" and not r.get("closed_date"): hit("status_closed_but_no_closed_date", r)
        if r.get("status") != "Closed" and r.get("closed_date"): hit("not_closed_but_has_closed_date", r, status=r.get("status"))
        if a and a.year != 2023: hit("created_outside_2023", r, created=r["created_date"])
        if b and a and (b - a).days > 365: hit("closure_over_a_year_after_creation", r, created=r["created_date"], closed=r["closed_date"])
        la, lo = r.get("latitude"), r.get("longitude")
        if la is None or lo is None: hit("missing_coordinates", r)
        elif la == 0 or lo == 0: hit("zero_coordinates", r, lat=la, lon=lo)
        elif not (NYC_BBOX[0] <= la <= NYC_BBOX[1] and NYC_BBOX[2] <= lo <= NYC_BBOX[3]): hit("coordinates_outside_nyc_bbox", r, lat=la, lon=lo)
        z = r.get("incident_zip")
        if z is None: hit("missing_zip", r)
        elif not re.fullmatch(r"\d{5}(-\d{4})?", str(z)): hit("malformed_zip", r, zip=z)
        elif r.get("borough") not in (None, "Unspecified") and zip_borough(z) not in (None, str(r["borough"]).upper()): hit("zip_borough_mismatch", r, zip=z, borough=r["borough"])
        if r.get("borough") in (None, "Unspecified"): hit("borough_unspecified_or_null", r)
        if not r.get("resolution_description") and r.get("status") == "Closed": hit("closed_without_resolution_text", r)
        for f in ("descriptor", "resolution_description"):
            t = r.get(f) or ""
            if PHONE.search(t) or EMAIL.search(t) or SSN.search(t): hit(f"pii_like_in_{f}", r, text=t[:60])
        if keys[r["unique_key"]] > 1: hit("duplicate_unique_key", r)
    ws = Counter(r.get("complaint_type") for r in rows if r.get("complaint_type") and (r["complaint_type"] != r["complaint_type"].strip()))
    case_var = Counter(); low = {}
    for r in rows:
        c = r.get("complaint_type")
        if c: low.setdefault(c.lower().strip(), set()).add(c)
    variants = {k: sorted(v) for k, v in low.items() if len(v) > 1}
    nulls = {c: round(100 * sum(r.get(c) is None for r in rows) / n, 2) for c in COLUMNS}
    out = {"data_source": src, "rows": n, "issues": {k: {"count": v, "pct": round(100 * v / n, 3), "example": ex[k]} for k, v in P.most_common()},
           "category_spelling_variants": variants, "null_pct_by_column": nulls}
    print(f"=== PROFILE | {src} | {n:,} rows ===")
    for k, v in out["issues"].items(): print(f"  {k}: {v['count']} ({v['pct']}%) e.g. {v['example']}")
    if write: (__import__('pathlib').Path(__file__).parent / "results" / "profile.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    profile_raw_data()
