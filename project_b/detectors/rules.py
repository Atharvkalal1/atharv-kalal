"""Detector family (a): declarative rules / schema / data-contract checks. Deterministic, $0, explainable.
Everything here is either a schema constant (common.py), an official lookup (ZIP ranges, NYC bbox) or a contract built from
reference data (allow-lists). No statistics, no model."""
from __future__ import annotations
import re
from collections import defaultdict
from project_b.common import REQUIRED, OPTIONAL, ISO, NYC_BBOX, parse_ts, zip_borough

PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CLOSED_BAD = re.compile(r"\b(still|pending|not yet|has not|have not|not been|awaiting|will respond|remains open|not started|being reviewed)\b", re.I)
OPEN_BAD = re.compile(r"\b(resolved|corrected|completed|closed|fixed)\b", re.I)


def build_contract(ref_rows):
    allow = defaultdict(set)
    for r in ref_rows: allow[r.get("complaint_type")].add(r.get("descriptor"))
    return {"allow": dict(allow)}


def _f(row, t, field, msg): return {"row": row, "type": t, "field": field, "msg": msg}


def detect(batch, contract):
    out, seen_key, byloc, nulls = [], {}, defaultdict(list), defaultdict(lambda: [0, 0])
    for i, r in enumerate(batch):
        # a: required columns present
        for c in REQUIRED:
            if c not in r: out.append(_f(i, "a", c, f"required column '{c}' missing (row has {len(r)} columns, contract expects it)"))
        # b: types
        for c, t in {**REQUIRED, **OPTIONAL}.items():
            v = r.get(c)
            if v is None: continue
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) if t is float else (isinstance(v, int) and not isinstance(v, bool)) if t is int else isinstance(v, t)
            if not ok: out.append(_f(i, "b", c, f"'{c}' is {type(v).__name__} ({str(v)[:20]!r}), contract type is {t.__name__}"))
        # c: ISO timestamps
        for c in ("created_date", "closed_date"):
            v = r.get(c)
            if v is not None and not ISO.match(str(v)): out.append(_f(i, "c", c, f"'{c}'={str(v)[:24]!r} is not ISO-8601 (YYYY-MM-DDTHH:MM:SS)"))
        # d: coordinates
        la, lo = r.get("latitude"), r.get("longitude")
        if isinstance(la, (int, float)) and isinstance(lo, (int, float)) and not isinstance(la, bool):
            inb = lambda a, o: NYC_BBOX[0] <= a <= NYC_BBOX[1] and NYC_BBOX[2] <= o <= NYC_BBOX[3]
            if not inb(la, lo) and inb(lo, la): out.append(_f(i, "d", "latitude", f"lat={la}, lon={lo} are outside NYC but swapped they fall inside"))
        # h: ordering
        a, b = parse_ts(r.get("created_date")), parse_ts(r.get("closed_date"))
        if a and b and b < a: out.append(_f(i, "h", "closed_date", f"closed_date {r['closed_date']} is before created_date {r['created_date']}"))
        # i: zip vs borough
        zb = zip_borough(r.get("incident_zip")) if r.get("incident_zip") else None
        bo = str(r.get("borough", "")).upper()
        if zb and bo in ("MANHATTAN", "BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND") and zb != bo:
            out.append(_f(i, "i", "incident_zip", f"zip {r['incident_zip']} belongs to {zb}, row says {bo}"))
        # j: descriptor allow-list
        al = contract["allow"].get(r.get("complaint_type"))
        if al and len(al) >= 2 and r.get("descriptor") not in al:
            out.append(_f(i, "j", "descriptor", f"descriptor {r.get('descriptor')!r} never seen with complaint_type {r.get('complaint_type')!r}"))
        # k: status vs resolution wording
        txt = r.get("resolution_description") or ""
        if r.get("status") == "Closed" and CLOSED_BAD.search(txt): out.append(_f(i, "k", "resolution_description", f"status Closed but text says: {txt[:60]!r}"))
        elif r.get("status") in ("Open", "In Progress", "Assigned", "Pending", "Started") and OPEN_BAD.search(txt):
            out.append(_f(i, "k", "resolution_description", f"status {r['status']} but text says: {txt[:60]!r}"))
        # l: PII
        for fld in ("descriptor", "resolution_description"):
            t = r.get(fld) or ""
            for nm, rx in (("phone", PHONE), ("email", EMAIL), ("ssn", SSN)):
                m = rx.search(str(t))
                if m: out.append(_f(i, "l", fld, f"{nm}-like value {m.group(0)!r} in free text field '{fld}'")); break
        # e: exact duplicate (same unique_key AND identical content)
        k = r.get("unique_key")
        if k in seen_key and batch[seen_key[k]] == r: out.append(_f(i, "e", "unique_key", f"row identical to row {seen_key[k]} (unique_key {k} repeated)"))
        seen_key.setdefault(k, i)
        # f: near duplicate: same place + complaint + normalised descriptor within 10 min, different key
        if isinstance(la, (int, float)) and a:
            byloc[(r.get("agency"), r.get("complaint_type"), (r.get("descriptor") or "").strip().lower(), round(la or 0, 5), round(lo or 0, 5))].append((i, a, k))
        # g: null-rate contract per agency (incident_zip may be null at most 5% of an agency's rows)
        n = nulls[r.get("agency")]; n[1] += 1; n[0] += r.get("incident_zip") is None
    for key, lst in byloc.items():
        for x in range(1, len(lst)):
            for y in range(x):
                if lst[x][2] != lst[y][2] and abs((lst[x][1] - lst[y][1]).total_seconds()) <= 600:
                    out.append(_f(lst[x][0], "f", "created_date", f"same agency/complaint/descriptor/location as row {lst[y][0]} within 10 min, different unique_key")); break
    for ag, (nn, tot) in nulls.items():
        if tot >= 20 and nn / tot > 0.05:
            out.append({"row": None, "type": "g", "field": "incident_zip", "agency": ag, "msg": f"agency {ag}: incident_zip null in {nn}/{tot} rows ({nn/tot:.0%}) > 5% contract"})
    return out
