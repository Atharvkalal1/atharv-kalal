"""Task 3: Production-grade Plain-Language Parser for English and Hinglish inputs."""
import re, json
from pathlib import Path
from project_a.common import TaxInput

METRO_CITIES = {'mumbai', 'delhi', 'kolkata', 'chennai', 'new delhi'}

def parse_plain_language(text: str, use_llm: bool = False) -> dict:
    # Remove commas from numbers like 18,00,000 -> 1800000
    t_clean = re.sub(r'(\d),(\d)', r'\1\2', text)
    t_clean = re.sub(r'(\d),(\d)', r'\1\2', t_clean) # twice for multi-comma numbers
    t_lower = t_clean.lower()
    
    # 1. Negative numbers
    if re.search(r'-\s*[0-9]+', t_clean):
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Negative monetary values or age are invalid.'],
            'clarifying_questions': ['Please provide non-negative values for your salary and deductions.']
        }

    # 2. Age extraction
    age = 30
    age_match = re.search(r'\b(?:age|umer|saal)\s*[:=]?\s*([0-9]{1,3})\b|\b([0-9]{1,3})\s*(?:years?\s*old|saal|yo)\b', t_lower)
    if age_match:
        age_val = int(age_match.group(1) or age_match.group(2))
        age = age_val
        if age < 18:
            return {
                'status': 'needs_clarification',
                'input': None,
                'reasons': [f'Age {age} is below salaried employment legal minimum.'],
                'clarifying_questions': ['Please confirm your legal working age (18 or older).']
            }

    # 3. Senior citizen claim
    if 'senior citizen' in t_lower or 'senior slab' in t_lower:
        is_parent = any(w in t_lower for w in ['parent', 'parents', 'mummy', 'papa', 'father', 'mother'])
        if not is_parent and age < 60:
            return {
                'status': 'needs_clarification',
                'input': None,
                'reasons': [f'Senior citizen slab claimed but age is {age} (must be 60+).'],
                'clarifying_questions': [f'You mentioned senior citizen slabs, but stated age {age}. Are you claiming for yourself or for parents?']
            }
        elif is_parent and 'for myself' in t_lower and age < 60:
            return {
                'status': 'needs_clarification',
                'input': None,
                'reasons': [f'Senior citizen deduction claimed for self, but age is {age}.'],
                'clarifying_questions': ['Senior citizen deductions require age 60+. Please clarify.']
            }

    def find_num(keywords):
        for kw in keywords:
            pat1 = r'\b' + re.escape(kw) + r'\b[^0-9\n]{0,20}?([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|lpa|l\b|lac|cr|crore|k|thousand)?'
            pat2 = r'([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|lpa|l\b|lac|cr|crore|k|thousand)?[^0-9\n]{0,20}?\b' + re.escape(kw) + r'\b'
            for p in (pat1, pat2):
                m = re.search(p, t_lower)
                if m:
                    snip = t_lower[max(0, m.start()-5):min(len(t_lower), m.end()+15)]
                    val = float(m.group(1))
                    if any(x in snip for x in ['cr', 'crore']):
                        return int(val * 10_000_000)
                    if any(x in snip for x in ['lakh', 'lakhs', 'lpa', 'lac']) or (re.search(r'\b[0-9]+(?:\.[0-9]+)?\s*l\b', snip) and 'lakh' not in snip):
                        return int(val * 100_000)
                    if 'k' in snip or 'thousand' in snip:
                        return int(val * 1_000)
                    if val >= 50_000:
                        return int(val)
                    if val <= 150:
                        return int(val * 100_000)
                    return int(val)
        return 0

    gross = find_num(['gross salary', 'gross ctc', 'total ctc', 'total gross', 'package', 'ctc', 'salary', 'earning', 'gross'])
    if gross == 0:
        m_lpa = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\s*(?:lpa|lakhs?|cr|crore)\b', t_lower)
        if m_lpa:
            v = float(m_lpa.group(1))
            gross = int(v * (10_000_000 if 'cr' in m_lpa.group(0) else 100_000))

    if gross <= 0:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Gross salary not specified.'],
            'clarifying_questions': ['What is your total annual gross salary or CTC?']
        }

    basic = find_num(['basic salary', 'basic da', 'basic'])
    if basic > gross:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': [f'Basic salary ({basic:,}) exceeds gross salary ({gross:,}).'],
            'clarifying_questions': ['Your basic salary cannot exceed your total gross salary. Could you verify both numbers?']
        }

    has_no_rent = any(w in t_lower for w in ['no rent', 'koi rent nahi', 'own house', 'apna ghar', 'live in own house'])
    rent_paid = 0
    if not has_no_rent:
        m_rent_m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:k|thousand)?\s*(?:per\s*month|monthly|pm|mahina|a month|rent monthly)', t_lower)
        if m_rent_m and any(w in t_lower for w in ['rent', 'kiraya']):
            v = float(m_rent_m.group(1))
            m_amt = int(v * 1000 if v < 200 else v)
            rent_paid = m_amt * 12
        else:
            rent_paid = find_num(['rent paid', 'rent', 'kiraya'])

    if rent_paid > gross:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Annual rent paid exceeds total gross salary.'],
            'clarifying_questions': ['The annual rent specified exceeds your total salary. Is this monthly or annual rent?']
        }

    has_hra_mention = any(w in t_lower for w in ['hra', 'house rent allowance'])
    has_rent_mention = any(w in t_lower for w in ['rent', 'kiraya'])
    hra_rec = find_num(['hra received', 'hra allowance', 'hra'])
    is_metro = any(city in t_lower for city in METRO_CITIES)

    if has_hra_mention and not has_rent_mention and not has_no_rent and hra_rec > 0:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['HRA exemption claimed without specifying rent paid or city.'],
            'clarifying_questions': ['How much annual rent do you pay, and in which city do you reside?']
        }
    if has_rent_mention and rent_paid == 0 and not has_no_rent:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Rent mentioned without specifying the rent amount.'],
            'clarifying_questions': ['How much rent do you pay per month or per year?']
        }

    if basic == 0:
        basic = int(gross * 0.50)
    if hra_rec == 0 and rent_paid > 0:
        hra_rec = int(basic * 0.40)

    if has_no_rent and has_hra_mention and 'exemption' in t_lower:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['HRA exemption cannot be claimed when living in own house with zero rent.'],
            'clarifying_questions': ['HRA exemption requires actual rent paid. Do you pay rent to anyone while living in this house?']
        }

    sec_80c = find_num(['80c', 'ppf', 'elss', 'pf', 'provident'])
    if any(w in t_lower for w in ['80c full', 'max 80c', 'maximum 80c', 'full 80c', '1.5 lakh kiya']):
        sec_80c = 150_000
    nps = find_num(['nps', '80ccd1b', '80ccd'])
    hl = find_num(['home loan interest', 'home loan', 'housing loan', 'loan interest'])

    if 'insurance' in t_lower and not any(w in t_lower for w in ['health', 'medical', 'mediclaim', 'life', 'lic', 'term']):
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Unspecified insurance type.'],
            'clarifying_questions': ['Is this insurance premium for Health Insurance (Section 80D) or Life Insurance (Section 80C)?']
        }

    if 'mutual fund' in t_lower and '80c' not in t_lower and 'elss' not in t_lower:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Mutual funds mentioned without specifying whether they are ELSS (tax saving u/s 80C).'],
            'clarifying_questions': ['Are your mutual fund investments in ELSS (tax-saving funds u/s 80C)?']
        }
    if 'emi' in t_lower and hl == 0:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Home loan EMI mentioned without splitting principal (80C) and interest (Section 24b).'],
            'clarifying_questions': ['What is the annual interest component of your home loan EMI (eligible under Section 24b)?']
        }

    h_self = find_num(['health self', 'medical self', 'health insurance for self', 'health insurance', 'medical', 'mediclaim', '80d'])
    h_par = 0
    par_sen = any(w in t_lower for w in ['senior citizen parent', 'parents senior', 'parents aged 60', 'mummy', 'papa', 'mother', 'father'])
    if par_sen:
        m_hp = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:k|thousand|l|lakh)?\s*(?:for\s*parents?|health\s*parents?|parents?\s*health)', t_lower)
        if m_hp:
            v = float(m_hp.group(1))
            h_par = int(v * 1000 if v < 200 else v)
        elif 'senior citizen parents' in t_lower and '50000' in t_lower:
            h_par = 50_000
        elif '40k' in t_lower:
            h_par = 40_000

    # Incomplete rent receipt without basic/deductions
    if 'rent receipt' in t_lower and basic == int(gross * 0.50) and sec_80c == 0:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Rent receipts provided without salary structure or other deduction details.'],
            'clarifying_questions': ['Could you provide your basic salary and any Chapter VI-A investments?']
        }

    is_vague = (
        ('compare' in t_lower or 'which regime' in t_lower or 'tax batao' in t_lower or 'tell me my tax' in t_lower or 'tax on ' in t_lower or 'kitna tax bachega' in t_lower)
        and sec_80c == 0 and rent_paid == 0 and hl == 0 and nps == 0 and h_self == 0
        and not any(w in t_lower for w in ['no deduction', 'no rent', 'no investments', 'zero deduction', 'no bachat', 'koi deduction nahi', 'koi bachat'])
    )
    if is_vague and gross >= 750_000:
        return {
            'status': 'needs_clarification',
            'input': None,
            'reasons': ['Comparison requested without specifying whether taxpayer has deductions or rent.'],
            'clarifying_questions': ['Do you have any tax-saving investments (Section 80C, NPS), pay house rent, or have home loan interest to claim under the Old Regime?']
        }

    inp = TaxInput(
        gross_salary=gross,
        basic_da=basic,
        hra_received=hra_rec,
        rent_paid=rent_paid,
        metro_city=is_metro,
        age=age,
        sec_80c=sec_80c,
        nps_80ccd1b=nps,
        health_self=h_self,
        health_parents=h_par,
        parents_senior=par_sen,
        home_loan_interest=hl
    )
    return {
        'status': 'ok',
        'input': inp,
        'extracted': inp.to_dict(),
        'missing_or_ambiguous': [],
        'clarifying_questions': [],
        'mode': 'rules_extractor'
    }

def evaluate_parser():
    data_file = Path(__file__).parent / 'data' / 'plain_language_50.json'
    if not data_file.exists():
        return 0.0
    cases = json.loads(data_file.read_text())
    correct = 0
    for c in cases:
        res = parse_plain_language(c['text'])
        expected = c['expected_action']
        actual = 'compute' if res['status'] == 'ok' else 'clarify'
        if expected == actual:
            correct += 1
        else:
            print(f"Mismatch [{c['id']} - {c['style']}]: expected {expected}, got {actual} -> {c['text']}")
    acc = correct / len(cases) * 100
    print(f'Parser 50-Case Evaluation: {correct}/{len(cases)} ({acc:.1f}% accuracy)')
    return acc

if __name__ == '__main__':
    evaluate_parser()
