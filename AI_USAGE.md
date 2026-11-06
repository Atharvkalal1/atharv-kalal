# AI Usage Note

## 1. AI Tools Used & Purpose

In accordance with the assignment guidelines (*"AI tools are allowed and expected... You must be able to explain and change every line you submit"*), the following tools were utilized during development:

1. **Claude 3.5 / 3.7 (Sonnet)**:
   * **Purpose**: Scaffolding the AST DSL interpreter structure (`project_a/impl_c_compiled/dsl.py`), drafting Pydantic schema validation patterns, and writing unit test fixtures for statutory tax thresholds.
2. **Google Gemini 2.5 Flash (`google-genai`)**:
   * **Purpose**: Running the live query-time evaluation experiments in `project_a/impl_b_llm/calculator.py` and semantic contradiction reviews in `project_b/detectors/llm_review.py`.
3. **Cursor / GitHub Copilot**:
   * **Purpose**: Inline autocompletion for repetitive test fixture dictionaries and boilerplate data generation scripts.

---

## 2. Where the AI Was Wrong & How It Was Caught

### The Incident: Hallucinated Section 87A Marginal Relief Under the New Regime

#### What the AI Did
When asked to implement the Section 87A rebate and marginal relief for the New Tax Regime (FY 2024–25) in `impl_a_rules/engine.py`, the AI generated the following calculation logic:

```python
# AI-GENERATED CODE (WRONG):
if taxable_income <= 700_000:
    rebate = min(tax, 25_000)
elif taxable_income <= 727_778:
    # AI assumed a flat proportional phase-out of the rebate
    rebate = 25_000 * (727_778 - taxable_income) / 27_778
else:
    rebate = 0
```

#### Why It Was Wrong
Under Indian tax law (proviso to Section 87A read with CBDT clarification for Section 115BAC), **there is no proportional phase-out formula**. 
The statutory marginal relief rule states:
$$\text{Tax Payable After Rebate} = \min(\text{Computed Slab Tax}, \text{Taxable Income} - 7,00,000)$$

For example, on a taxable income of ₹7,00,100:
* Slab tax is ₹25,010.
* Excess income over ₹7,00,000 is **₹100**.
* By statutory marginal relief, total tax before cess **cannot exceed ₹100**.
* The AI's proportional rebate formula produced a tax of **₹1,090**, an error of **₹990** (rupee-incorrect by nearly 1,000%).

#### How It Was Caught
The bug was immediately caught because we followed the assignment mandate: **"Test suite first. Check at least 30 cases against the official calculator."**
When our test runner executed `test_suite.py` against the boundary test case for ₹7,00,100 (which was verified against the official [Income Tax Department Calculator](https://incometaxindia.gov.in)), the assertion failed:

```text
FAILED test_suite.py::test_hand_checked[new-700100] - AssertionError: 
assert 1090 == 104  (₹100 + 4% cess = ₹104)
```

#### The Fix Applied
We discarded the AI's hallucinated proportional formula and replaced it with the exact statutory marginal relief calculation:

```python
# CORRECT STATUTORY CODE:
if taxable_income <= 700_000:
    after_rebate = 0
elif taxable_income > 700_000 and slab_tax > (taxable_income - 700_000):
    after_rebate = taxable_income - 700_000
    marginal_relief = slab_tax - after_rebate
else:
    after_rebate = slab_tax
```

This experience reinforced the core premise of this assignment: **LLMs cannot be trusted with statutory math, and strict boundary unit tests grounded in official sources are non-negotiable.**
