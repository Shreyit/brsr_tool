"""
Pull 5 comparable numeric KPIs out of each report's full_text, anchored on
fixed BRSR phrasing rather than the principle/indicator JSON structure (so
this still works for ICICI_2025-2026, whose section split is unreliable).

KPIs: ghg_intensity, water_intensity, employee_turnover_rate,
gender_pay_gap, safety_incident_rate (LTIFR).

Usage:
    python -m src.kpi.parse_kpis
Writes data/kpis.json: list of
    {company, fy, kpi, value, unit, prior_year_value, note}
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRACTED_DIR = ROOT / "data" / "extracted"
OUT_PATH = ROOT / "data" / "kpis.json"

NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _clean_num(s):
    s = s.strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _first_two_numbers(text, stop_before=None):
    """First two numeric tokens in text, skipping NIL/NA-ish words (-> None)."""
    if stop_before:
        idx = text.find(stop_before)
        if idx != -1:
            text = text[:idx]
    tokens = re.findall(r"NIL|N\.?A\.?|Not Applicable|-?\d[\d,]*\.?\d*", text, re.IGNORECASE)
    vals = []
    for tok in tokens:
        if re.match(r"NIL|N\.?A\.?|Not Applicable", tok, re.IGNORECASE):
            vals.append(None)
        else:
            v = _clean_num(tok)
            if v is not None:
                vals.append(v)
        if len(vals) == 2:
            break
    while len(vals) < 2:
        vals.append(None)
    return vals[0], vals[1]


def _norm(text):
    """Collapse all whitespace runs to single spaces so multi-line anchor
    phrases (PDF text wraps mid-phrase, e.g. "per rupee \\nof turnover")
    still match a plain-space regex."""
    return re.sub(r"\s+", " ", text)


def parse_ghg_intensity(text):
    text = _norm(text)
    m = re.search(r"Total Scope 1 and Scope 2 emission intensity per rupee of turnover", text, re.IGNORECASE)
    if not m:
        return None, None, None
    window = text[m.end():m.end() + 400]
    cur, prior = _first_two_numbers(window, stop_before="adjusted for Purchasing Power Parity")
    unit_m = re.search(r"g\s*CO2e\s*/\s*Rupee", window, re.IGNORECASE)
    unit = unit_m.group(0) if unit_m else "g CO2e/Rupee"
    return cur, prior, unit


def parse_water_intensity(text):
    text = _norm(text)
    m = re.search(r"Water intensity per rupee of turnover", text, re.IGNORECASE)
    if not m:
        return None, None, None
    window = text[m.end():m.end() + 400]
    cur, prior = _first_two_numbers(window, stop_before="adjusted for Purchasing Power Parity")
    return cur, prior, "KL/INR crore"


def parse_turnover_rate(text):
    text = _norm(text)
    m = re.search(r"Turnover rate for permanent employees", text, re.IGNORECASE)
    if not m:
        return None, None, None
    window = text[m.end():m.end() + 600]
    row_m = re.search(r"Permanent\s+[Ee]mployees\S*", window)
    if not row_m:
        return None, None, None
    tail = window[row_m.end():]
    nums = NUM_RE.findall(tail)[:9]
    vals = [_clean_num(n) for n in nums]
    if len(vals) < 3:
        return None, None, None
    return vals[2], (vals[5] if len(vals) > 5 else None), "%"


def parse_gender_pay_gap(text):
    text = _norm(text)
    for m in re.finditer(r"[Rr]emuneration/salary/wages", text):
        window = text[m.end():m.end() + 900]
        row_m = re.search(r"Employees other than (?:BoD|BOD) and KMP\S*", window)
        if not row_m:
            continue
        tail = window[row_m.end():]
        # tail: Number(M), Median(M), Number(F), Median(F) -- possibly with
        # currency/unit words and footnote digits mixed in; grab the 4
        # numeric-looking tokens (ignore lone 1-digit footnote markers glued
        # onto a preceding number, e.g. "694,313 3" -> take 694313 not 3).
        raw_tokens = re.findall(r"[\d,]+\.?\d*|₹\s*[\d.]+\s*(?:[Ll]akh|[Cc]r)", tail)
        nums = []
        for tok in raw_tokens:
            v = _clean_num(tok.replace("₹", ""))
            if v is None:
                continue
            if "lakh" in tok.lower():
                v *= 100000
            elif re.search(r"\bcr\b", tok, re.IGNORECASE):
                v *= 10000000
            nums.append(v)
            if len(nums) == 4:
                break
        if len(nums) < 4:
            continue
        male_median, female_median = nums[1], nums[3]
        if not male_median:
            continue
        gap = (male_median - female_median) / male_median
        return gap, None, "fraction (M-F)/M"
    return None, None, None


def parse_safety_incident_rate(text):
    text = _norm(text)
    m = re.search(r"Lost Time Injury Frequency Rate", text, re.IGNORECASE)
    if not m:
        return None, None, None
    window = text[m.end():m.end() + 400]
    row_m = re.search(r"\bEmployees\b", window)
    if not row_m:
        return None, None, None
    tail = window[row_m.end():]
    cur, prior = _first_two_numbers(tail)
    return cur, prior, "per million person-hours"


KPI_PARSERS = {
    "ghg_intensity": parse_ghg_intensity,
    "water_intensity": parse_water_intensity,
    "employee_turnover_rate": parse_turnover_rate,
    "gender_pay_gap": parse_gender_pay_gap,
    "safety_incident_rate": parse_safety_incident_rate,
}


def parse_report(report_json):
    text = report_json["full_text"]
    records = []
    for kpi, fn in KPI_PARSERS.items():
        cur, prior, unit = fn(text)
        records.append(
            {
                "company": report_json["company"],
                "fy": report_json["fy"],
                "kpi": kpi,
                "value": cur,
                "prior_year_value": prior,
                "unit": unit,
            }
        )
    return records


def main():
    all_records = []
    for path in sorted(EXTRACTED_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        recs = parse_report(data)
        all_records.extend(recs)
        found = sum(1 for r in recs if r["value"] is not None)
        print(f"{data['company']:8s} {data['fy']:10s} {found}/5 KPIs found")

    OUT_PATH.write_text(json.dumps(all_records, indent=2))
    print(f"\nWrote {OUT_PATH.relative_to(ROOT)} ({len(all_records)} records)")


if __name__ == "__main__":
    main()
