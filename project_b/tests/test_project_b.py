import pytest
from project_b.common import load, Reference
from project_b.injector import inject, TYPES
from project_b.detectors import rules, statistical

ROWS, _ = load(); REF = ROWS[:2000]; REFM = Reference(REF); CON = rules.build_contract(REF); BASE = ROWS[2000:3000]


@pytest.mark.parametrize("t", list(TYPES))
def test_injector_controls_rate_and_leaves_input_untouched(t):
    snap = [dict(r) for r in BASE]; b, tr = inject(BASE, t, 0.05, 1)
    assert BASE == snap and tr["rows"] and len(tr["rows"]) >= 40


def test_clean_batch_has_no_typed_alerts_for_structural_checks():
    fs = rules.detect(ROWS[3000:4000], CON)
    assert not [f for f in fs if f["type"] in "abcdeilg"]


@pytest.mark.parametrize("t", list("abcdehijl"))
def test_rules_catch_structural_problems(t):
    b, tr = inject(BASE, t, 0.05, 2); fl = {f["row"] for f in rules.detect(b, CON) if f["type"] == t and f["row"] is not None}
    assert len(fl & tr["rows"]) / len(tr["rows"]) > 0.9


def test_statistics_catch_null_spike_with_right_agency():
    b, tr = inject(BASE, "g", 0.05, 2)
    assert any(f["type"] == "g" and f.get("agency") == tr["agency"] and f["row"] is None for f in statistical.detect(b, REFM))


def test_detectors_do_not_import_injector():  # guards against circular evaluation
    import inspect
    for m in (rules, statistical): assert "injector" not in inspect.getsource(m)
