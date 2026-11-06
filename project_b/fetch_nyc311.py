"""Download REAL NYC 311 service requests created in calendar 2023 from NYC Open Data (Socrata, dataset erm2-nwe9).
    python -m project_b.fetch_nyc311 --max-rows 200000 [--token YOUR_SOCRATA_APP_TOKEN]
Writes project_b/data/nyc311_2023.jsonl (typed: unique_key int, lat/lon float). When that file exists every project_b script uses it.
NOTE: this sandbox had no access to data.cityofnewyork.us, so this script was written but NOT executed here - run it on your machine."""
import argparse, json, random, urllib.parse, urllib.request
from project_b.common import REAL_FILE, COLUMNS

URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"


def fetch(max_rows, token=None, page=50000, seed=7):
    rows, offset = [], 0
    where = "created_date >= '2023-01-01T00:00:00' AND created_date < '2024-01-01T00:00:00'"
    while len(rows) < max_rows:
        q = {"$select": ",".join(COLUMNS), "$where": where, "$order": "unique_key", "$limit": page, "$offset": offset}
        req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), headers={"X-App-Token": token} if token else {})
        chunk = json.loads(urllib.request.urlopen(req, timeout=120).read())
        if not chunk: break
        rows += chunk; offset += page; print(f"  fetched {len(rows)}")
    return rows[:max_rows]


def clean_types(r):
    o = {c: r.get(c) for c in COLUMNS}                         # absent columns stay None, exactly as in the source
    o["unique_key"] = int(o["unique_key"])
    for c in ("latitude", "longitude"):
        o[c] = float(o[c]) if o[c] not in (None, "") else None
    return o


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--max-rows", type=int, default=200000); ap.add_argument("--token")
    a = ap.parse_args(); rows = [clean_types(r) for r in fetch(a.max_rows, a.token)]
    random.Random(7).shuffle(rows); rows.sort(key=lambda r: r["created_date"])
    REAL_FILE.parent.mkdir(exist_ok=True); REAL_FILE.write_text("\n".join(json.dumps(r) for r in rows))
    print(f"wrote {len(rows)} real rows -> {REAL_FILE}")
