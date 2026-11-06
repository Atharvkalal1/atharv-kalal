"""Minimal Gemini REST client (stdlib only): disk cache, RPM throttle, backoff, token + cost metadata."""
from __future__ import annotations
import hashlib, json, os, re, time, urllib.request, urllib.error
from pathlib import Path

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# USD per 1M tokens. Both are reported so Task 4 can show either. Override with env vars.
REFERENCE_RATES = (float(os.environ.get("GEMINI_REF_IN_PER_M", 0.15)), float(os.environ.get("GEMINI_REF_OUT_PER_M", 0.60)))
LIST_RATES = (float(os.environ.get("GEMINI_LIST_IN_PER_M", 0.30)), float(os.environ.get("GEMINI_LIST_OUT_PER_M", 2.50)))

_sleep = time.sleep          # indirection so tests can stub them
_now = time.monotonic
_last_call = [0.0]


def has_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def cache_path() -> Path:
    return Path(os.environ.get("GEMINI_CACHE_PATH") or Path(__file__).parent / ".gemini_cache.json")


def _load_cache() -> dict:
    try:
        return json.loads(cache_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(c: dict) -> None:
    try:
        cache_path().write_text(json.dumps(c))
    except OSError:
        pass


def estimate_cost(prompt_tokens: int, output_tokens: int) -> dict:
    """Cost of ONE live request at free-tier ($0) and commercial rates, scaled to 1,000 requests.
    output_tokens includes thinking tokens (billed as output)."""
    per1k = lambda r: round((prompt_tokens * r[0] + output_tokens * r[1]) / 1e6 * 1000, 6)
    return {"free_tier": 0.0, "commercial_reference": per1k(REFERENCE_RATES), "commercial_list_2_5_flash": per1k(LIST_RATES),
            "rates_usd_per_1m_tokens": {"reference_in_out": REFERENCE_RATES, "list_in_out": LIST_RATES}}


def _throttle() -> None:
    gap = float(os.environ.get("GEMINI_MIN_INTERVAL_S", "0") or 0)
    if gap > 0:
        wait = _last_call[0] + gap - _now()
        if wait > 0:
            _sleep(wait)
    _last_call[0] = _now()


def generate_json(prompt: str, system: str | None = None, model: str | None = None, retries: int = 5,
                  use_cache: bool = True, bypass_cache: bool = False):
    """Returns (parsed_json, meta). bypass_cache=True forces a live call and does not touch the cache
    (use it for the 10x determinism test). meta has latency, tokens and est_cost_per_1k_req_usd."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY (free key from Google AI Studio) or use the offline stub.")
    model = model or DEFAULT_MODEL
    ck = hashlib.sha256(json.dumps([model, system, prompt]).encode()).hexdigest()
    if use_cache and not bypass_cache:
        hit = _load_cache().get(ck)
        if hit:
            meta = dict(hit["meta"], mode="live_gemini_cached", cache_hit=True, original_latency_s=hit["meta"]["latency_s"])
            return hit["parsed"], meta
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "seed": 0, "responseMimeType": "application/json"}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    mk = lambda: urllib.request.Request(url, data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    t0 = time.perf_counter()
    for attempt in range(retries):
        _throttle()
        try:
            with urllib.request.urlopen(mk(), timeout=120) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                _sleep(min(60, 2 ** attempt * 2))
                continue
            raise
    latency = time.perf_counter() - t0
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    parsed = json.loads(text)
    u = data.get("usageMetadata", {})
    pt, ot = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    meta = dict(mode="live_gemini", cache_hit=False, model=model, latency_s=round(latency, 3), prompt_tokens=pt,
                output_tokens=ot, est_cost_per_1k_req_usd=estimate_cost(pt, ot))
    if use_cache and not bypass_cache:
        c = _load_cache(); c[ck] = {"parsed": parsed, "meta": meta}; _save_cache(c)
    return parsed, meta
