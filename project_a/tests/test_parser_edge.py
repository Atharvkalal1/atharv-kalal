"""Regression tests for parser edge cases: contradictions, unrealistic values."""
import pytest
from project_a.parser import parse_plain_language


@pytest.mark.parametrize("text", [
    "salary 12 lakh aur 18 lakh",
    "salary 12 lakh and 18 lakh",
])
def test_contradictory_salary_asks_instead_of_guessing(text):
    r = parse_plain_language(text)
    assert r["status"] == "needs_clarification"
    assert any("two different amounts" in x.lower() for x in r["reasons"])


def test_unrealistic_age_is_rejected_before_compute():
    assert parse_plain_language("12 lakh salary age 200")["status"] == "needs_clarification"


def test_absurd_salary_is_rejected():
    assert parse_plain_language("salary 99999999999999999999")["status"] == "needs_clarification"


def test_same_value_repeated_is_not_a_conflict():
    assert parse_plain_language("salary 12 lakh, no rent, no deductions")["status"] == "ok"
