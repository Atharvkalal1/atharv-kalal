"""Detector family (b): statistical / ML detectors learned from a clean reference batch. $0 per row; no hard-coded schema or lists."""
from __future__ import annotations
import hashlib, math, random
from collections import Counter, defaultdict
from project_b.common import COLUMNS, signature, parse_ts, tokens

_P = (1 << 61) - 1
_RND = random.Random(11)
_SEEDS = [(_RND.randrange(1, _P), _RND.randrange(0, _P)) for _ in range(24)]


def _h(s): return int.from_bytes(hashlib.md5(s.encode()).digest()[:8], "big")


def _minhash(items):
    hs = [_h(x) for x in items]
    return [min((a * h + b) % _P for h in hs) for a, b in _SEEDS]


def _f(row, t, field, msg, **kw): return {"row": row, "type": t, "field": field, "msg": msg, **kw}


def _nb_logodds(ref, toks):
    """log P(closed|text)/P(open|text) with Laplace smoothing."""
    v = len(ref.vocab) + 1; lo = math.log((ref.stat_n["closed"] + 1) / (ref.stat_n["open"] + 1))
    tc, to = sum(ref.stat_tok["closed"].values()) + v, sum(ref.stat_tok["open"].values()) + v
    for t in toks:
        lo += math.log((ref.stat_tok["closed"][t] + 1) / tc) - math.log((ref.stat_tok["open"][t] + 1) / to)
    return lo


def detect(batch, ref):
    out, n = [], len(batch)
    # a: column presence vs reference column set (batch-level, rows lacking the column are flagged)
    for c in ref.col_set:
        miss = [i for i, r in enumerate(batch) if c not in r]
        if miss and len(miss) / n > 0.005:
            out.append(_f(None, "a", c, f"column '{c}' present in {1 - len(miss)/n:.1%} of rows, reference had ~100%"))
            out += [_f(i, "a", c, f"column '{c}' absent (present in ~100% of reference rows)") for i in miss]
    # b/c: rare format signature per column (type never/rarely seen in reference = b; date column with a new string format = c)
    for c in COLUMNS:
        tot = sum(ref.sig[c].values()); non_null = [(k, v) for k, v in ref.sig[c].most_common() if k != "NULL"]
        dom_type = non_null[0][0].split(":")[0] if non_null else None
        for i, r in enumerate(batch):
            v = r.get(c)
            if v is None: continue
            s = signature(v)
            if ref.sig[c][s] / tot >= 0.002: continue
            if type(v).__name__ != dom_type:
                out.append(_f(i, "b", c, f"'{c}' is {type(v).__name__} ({str(v)[:20]!r}); reference values are {dom_type} ({ref.sig[c][s]/tot:.2%} had this form)"))
            elif c in ("created_date", "closed_date"):
                out.append(_f(i, "c", c, f"'{c}'={str(v)[:24]!r} has a format seen in {ref.sig[c][s]/tot:.2%} of reference rows"))
    # d: robust z-score of coordinates; swapped = far as given, near when swapped
    (mla, sla), (mlo, slo) = ref.lat, ref.lon
    for i, r in enumerate(batch):
        la, lo = r.get("latitude"), r.get("longitude")
        if isinstance(la, (int, float)) and isinstance(lo, (int, float)) and not isinstance(la, bool) and la:
            z = max(abs(la - mla) / sla, abs(lo - mlo) / slo); zs = max(abs(lo - mla) / sla, abs(la - mlo) / slo)
            if z > 8 and zs < 8: out.append(_f(i, "d", "latitude", f"robust z={z:.0f} as given but {zs:.1f} if lat/lon swapped"))
    # e/f: MinHash-LSH over row content (exact vs near duplicates)
    items, sigs = [], []
    for i, r in enumerate(batch):
        its = {f"{k}={v}" for k, v in r.items()}; items.append(its); sigs.append(_minhash(its))
    buckets = defaultdict(list)
    for i, s in enumerate(sigs):
        for b in range(8): buckets[(b, tuple(s[3 * b:3 * b + 3]))].append(i)
    done = set()
    for lst in buckets.values():
        if len(lst) < 2 or len(lst) > 40: continue
        for x in range(len(lst)):
            for y in range(x):
                p = (lst[y], lst[x])
                if p in done: continue
                done.add(p); a, b = items[p[0]], items[p[1]]; j = len(a & b) / len(a | b)
                if j == 1.0: out.append(_f(p[1], "e", "row", f"identical to row {p[0]} (Jaccard 1.00)"))
                elif j >= 0.7: out.append(_f(p[1], "f", "row", f"near-duplicate of row {p[0]} (Jaccard {j:.2f}, differing fields {sorted(x.split('=')[0] for x in a ^ b)[:3]})"))
    # g: per-agency null rate vs reference (one-sided z, only meaningful groups)
    grp = defaultdict(list)
    for i, r in enumerate(batch): grp[r.get("agency")].append(i)
    for ag, idx in grp.items():
        if len(idx) < 20: continue
        for c in COLUMNS:
            k = sum(batch[i].get(c) is None for i in idx); p = k / len(idx); p0 = max(ref.null_rate.get((ag, c), 0.0), 0.01)
            z = (p - p0) / math.sqrt(p0 * (1 - p0) / len(idx))
            if z > 6 and p - p0 > 0.15:
                out.append(_f(None, "g", c, f"agency {ag}: '{c}' null rate {p:.0%} vs reference {p0:.1%} (z={z:.1f})", agency=ag))
                out += [_f(i, "g", c, f"null '{c}' inside spiking agency {ag}", agency=ag) for i in idx if batch[i].get(c) is None]
    # h: closure time in asinh(hours) vs agency distribution (negative durations are far in the left tail)
    for i, r in enumerate(batch):
        a, b = parse_ts(r.get("created_date")), parse_ts(r.get("closed_date"))
        if a and b and r.get("agency") in ref.dur:
            m, s = ref.dur[r["agency"]]; z = (math.asinh((b - a).total_seconds() / 3600) - m) / s
            if z < -4: out.append(_f(i, "h", "closed_date", f"closure time {((b-a).total_seconds()/3600):.1f}h is z={z:.1f} vs {r['agency']} history"))
    # i: P(borough | zip) learned from reference
    for i, r in enumerate(batch):
        c = ref.zip_boro.get(str(r.get("incident_zip")))
        if c and sum(c.values()) >= 3 and r.get("borough") in ("MANHATTAN", "BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND"):
            p = c[r["borough"]] / sum(c.values())
            if p < 0.05: out.append(_f(i, "i", "incident_zip", f"P(borough={r['borough']} | zip={r['incident_zip']}) = {p:.1%} in reference"))
    # j: P(descriptor | complaint_type) learned from reference
    for i, r in enumerate(batch):
        c = ref.cdesc.get(r.get("complaint_type"))
        if c and sum(c.values()) >= 30 and len(c) >= 2:
            p = c[r.get("descriptor")] / sum(c.values())
            if p < 0.005: out.append(_f(i, "j", "descriptor", f"P(descriptor={r.get('descriptor')!r} | {r.get('complaint_type')!r}) = {p:.2%} in reference"))
    # k: naive-Bayes text/status agreement
    for i, r in enumerate(batch):
        tk = tokens(r.get("resolution_description"))
        if len(tk) >= 4:
            lo = _nb_logodds(ref, tk); closed = r.get("status") == "Closed"
            if (closed and lo < -4) or ((not closed) and lo > 4):
                out.append(_f(i, "k", "resolution_description", f"text reads like a {'non-closed' if closed else 'closed'} ticket (NB log-odds {lo:+.1f}) but status is {r.get('status')}"))
    # l: free-text character profile (digit density / '@') vs reference-typical text
    for i, r in enumerate(batch):
        for fld in ("descriptor", "resolution_description"):
            t = str(r.get(fld) or ""); d = sum(ch.isdigit() for ch in t)
            if d >= 7 or "@" in t:
                out.append(_f(i, "l", fld, f"{fld} has {d} digits{' and an @' if '@' in t else ''}; reference free text has ~0")); break
    return out
