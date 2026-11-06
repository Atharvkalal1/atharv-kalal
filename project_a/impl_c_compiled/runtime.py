"""Run a compiled spec. Pure Python, no LLM, no network."""
from __future__ import annotations
import json
from pathlib import Path
from project_a.common import TaxInput, fy_slug, attach_traceability, recommend
from project_a.impl_c_compiled.dsl import run_regime

_DIR = Path(__file__).parent / "compiled"


def load_spec(fy: str, path: Path | None = None) -> dict:
    p = path or _DIR / f"fy{fy_slug(fy)}.json"
    if not p.exists():
        raise ValueError(f"No compiled (reviewed) spec for FY {fy}: {p.name}")
    return json.loads(p.read_text())


def compute(inp: TaxInput, spec: dict | None = None) -> dict:
    inp.validate()
    spec = spec or load_spec(inp.fy)
    d = inp.to_dict()
    res = {r: attach_traceability(dict(regime=r, rounding_288_applied=inp.apply_288_rounding,
                                       **run_regime(spec["regimes"][r], d)), inp.fy) for r in ("old", "new")}
    res["recommendation"] = recommend(res["old"], res["new"])
    return res
