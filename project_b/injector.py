"""Task 2: controlled corruption injector for the 12 problem types. One type per call, at a controlled rate, with exact ground truth.

    batch, truth = inject(clean_rows, "h", rate=0.05, seed=1)
truth = {"type", "rate", "level": "row"|"batch", "rows": {indices of affected rows in the returned batch}, "agency": ...}

Design rules (so detectors are not graded on the injector's own fingerprints):
  - no literal marker strings; corruptions are drawn from varied, realistic variants
  - problem types that are batch-level in reality (a, c, g) affect a contiguous tail / one agency, as drift does
"""
from __future__ import annotations
import copy, random
from datetime import timedelta
from project_b.common import ZIP_RANGES, parse_ts

TYPES = {"a": "Renamed or dropped column", "b": "Column type change", "c": "Date format switch partway", "d": "Latitude/longitude swapped",
         "e": "Exact duplicates", "f": "Near-duplicates", "g": "Null spike in one agency", "h": "Closed date earlier than created",
         "i": "ZIP inconsistent with borough", "j": "Complaint Type inconsistent with Descriptor",
         "k": "Resolution Description contradicts Status", "l": "Personal data in free text"}
BATCH_LEVEL = {"a", "c", "g"}
CONTRA_CLOSED = ["Your request is still being reviewed by the agency.", "No inspector has been assigned to this request yet.",
                 "The agency will respond within 14 days.", "This complaint is pending and has not been addressed.",
                 "We have not yet visited the location.", "The case remains open while the investigation continues.",
                 "Work on this issue has not started.", "Request forwarded and awaiting a response from the owner."]
CONTRA_OPEN = ["The condition was corrected and the case was closed.", "The Department inspected and resolved the complaint.",
               "Repairs were completed and no further action is needed.", "This request has been fully resolved."]
PII = ["Caller {n} can be reached at {p}.", "Please call {p} before visiting.", "Contact {e} for access.", "Tenant {n}, phone {p}, wants a callback.",
       "Complainant {n} ({e}) reported this.", "SSN given by caller: {s}."]
NAMES = ["Maria Gonzalez", "John Smith", "Aisha Khan", "Wei Chen", "Robert Johnson", "Priya Patel"]
PHONES = ["212-555-0143", "(718) 555-0199", "646.555.0102", "+1 917 555 0123", "3475550177"]
EMAILS = ["m.gonzalez@gmail.com", "jsmith88@yahoo.com", "aisha.khan@outlook.com", "tenant_5b@icloud.com"]


def _pick(r, n, k):
    return r.sample(range(n), min(k, n))


def inject(rows, ptype, rate=0.05, seed=0):
    r = random.Random(seed); b = copy.deepcopy(rows); n = len(b); k = max(1, int(n * rate)); aff, extra = set(), {}
    if ptype == "a":                                   # schema drift: last `rate` fraction of rows lose/rename a column
        col = r.choice(["agency", "incident_zip", "complaint_type"]); drop = r.random() < .5; extra["column"] = col
        for i in range(n - k, n):
            v = b[i].pop(col)
            if not drop: b[i][col + r.choice(["_code", "_name", "2"])] = v
            aff.add(i)
    elif ptype == "b":
        col = r.choice(["unique_key", "latitude", "longitude"]); extra["column"] = col
        for i in _pick(r, n, k):
            if b[i].get(col) is not None: b[i][col] = str(b[i][col]); aff.add(i)
    elif ptype == "c":                                 # date format switch partway: tail rows use legacy US 12-hour format
        for i in range(n - k, n):
            for c in ("created_date", "closed_date"):
                t = parse_ts(b[i].get(c))
                if t: b[i][c] = t.strftime("%m/%d/%Y %I:%M:%S %p")
            aff.add(i)
    elif ptype == "d":
        for i in _pick(r, n, k):
            if b[i]["latitude"] is not None: b[i]["latitude"], b[i]["longitude"] = b[i]["longitude"], b[i]["latitude"]; aff.add(i)
    elif ptype == "e":
        for _ in range(k):
            src = r.randrange(n); pos = r.randrange(n + 1); b.insert(pos, copy.deepcopy(b[src]))
            aff = {j + (j >= pos) for j in aff}; aff.add(pos)
        # rows inserted later may shift earlier inserts; recompute exactly:
        seen, aff = set(), set()
        for i, x in enumerate(b):
            if x["unique_key"] in seen: aff.add(i)
            seen.add(x["unique_key"])
    elif ptype == "f":
        new = []
        for _ in range(k):
            src = copy.deepcopy(b[r.randrange(n)])
            src["unique_key"] = max(x["unique_key"] for x in b[:200]) + r.randint(10_000, 99_999) + len(new)
            t = parse_ts(src["created_date"])
            if t and r.random() < .6: src["created_date"] = (t + timedelta(seconds=r.randint(1, 600))).strftime("%Y-%m-%dT%H:%M:%S.000")
            else:
                d = src["descriptor"]; src["descriptor"] = r.choice([d.lower(), d.upper(), d + " ", d.replace(" ", "  ", 1) if " " in d else d + ".", d[:-1] if len(d) > 4 else d])
            new.append(src)
        for x in new: pos = r.randrange(len(b) + 1); b.insert(pos, x)
        keys = {x["unique_key"] for x in new}; aff = {i for i, x in enumerate(b) if x["unique_key"] in keys}
    elif ptype == "g":
        counts = {}
        for x in b: counts[x["agency"]] = counts.get(x["agency"], 0) + 1
        ag = r.choice([a for a, c in counts.items() if c >= 30]); extra["agency"] = ag; col = "incident_zip"; extra["column"] = col
        for i, x in enumerate(b):
            if x["agency"] == ag and r.random() < max(.5, rate * 8): x[col] = None; aff.add(i)
    elif ptype == "h":
        for i in _pick(r, n, k):
            t = parse_ts(b[i]["created_date"])
            if t: b[i]["closed_date"] = (t - timedelta(seconds=r.randint(30, 20 * 86400))).strftime("%Y-%m-%dT%H:%M:%S.000"); aff.add(i)
    elif ptype == "i":
        for i in _pick(r, n, k):
            other = r.choice([x for x in ZIP_RANGES if x != b[i]["borough"]]); b[i]["incident_zip"] = str(r.randint(*r.choice(ZIP_RANGES[other]))); aff.add(i)
    elif ptype == "j":
        by_ct = {}
        for x in b: by_ct.setdefault(x["complaint_type"], set()).add(x["descriptor"])
        for i in _pick(r, n, k):
            others = [d for ct, ds in by_ct.items() if ct != b[i]["complaint_type"] for d in ds if d not in by_ct[b[i]["complaint_type"]]]
            if others: b[i]["descriptor"] = r.choice(others); aff.add(i)
    elif ptype == "k":
        for i in _pick(r, n, k):
            if r.random() < .6: b[i]["status"], b[i]["resolution_description"] = "Closed", r.choice(CONTRA_CLOSED)
            else: b[i]["status"], b[i]["resolution_description"] = r.choice(["Open", "In Progress", "Assigned"]), r.choice(CONTRA_OPEN)
            aff.add(i)
    elif ptype == "l":
        for i in _pick(r, n, k):
            txt = r.choice(PII).format(n=r.choice(NAMES), p=r.choice(PHONES), e=r.choice(EMAILS), s=f"{r.randint(100,899)}-{r.randint(10,99)}-{r.randint(1000,9999)}")
            f = r.choice(["resolution_description", "descriptor"])
            b[i][f] = ((b[i].get(f) or "") + " " + txt).strip(); aff.add(i)
    else:
        raise ValueError(ptype)
    return b, {"type": ptype, "rate": rate, "level": "batch" if ptype in BATCH_LEVEL else "row", "rows": aff, **extra}
