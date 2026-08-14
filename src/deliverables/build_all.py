"""
Build all 4 deliverables into a single Excel workbook.

Usage:
    python -m src.deliverables.build_all

Output:
    data/output/brsr_deliverables.xlsx  (4 sheets)

Sheets:
    1. Flat_Table       — Deliverable 1: single-company flat table
    2. KPI_Benchmark    — Deliverable 2: cross-company KPI benchmark
    3. Time_Series      — Deliverable 3: per-company KPI time series
    4. Completion_Rate  — Deliverable 4: Essential vs Leadership completion
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXTRACTED_DIR = ROOT / "data" / "extracted"
KPI_PATH = ROOT / "data" / "kpis.json"
OUT_DIR = ROOT / "data" / "output"
OUT_PATH = OUT_DIR / "brsr_deliverables.xlsx"

COMPANY_ORDER = ["AXIS", "HDFC", "ICICI", "KOTAK", "PNB"]
FY_ORDER = ["2023-2024", "2024-2025", "2025-2026"]

PRINCIPLE_NAMES = {
    1: "Ethics & Transparency",
    2: "Product Responsibility",
    3: "Employee Well-being",
    4: "Stakeholder Responsiveness",
    5: "Human Rights",
    6: "Environment Protection",
    7: "Public Policy Advocacy",
    8: "Inclusive Growth",
    9: "Customer Responsibility",
}

KPI_TO_PRINCIPLE = {
    "ghg_intensity": 6,
    "water_intensity": 6,
    "employee_turnover_rate": 3,
    "gender_pay_gap": 5,
    "safety_incident_rate": 6,
}

KPI_LABELS = {
    "ghg_intensity": "GHG Intensity",
    "water_intensity": "Water Intensity",
    "employee_turnover_rate": "Employee Turnover (%)",
    "gender_pay_gap": "Gender Pay Gap",
    "safety_incident_rate": "Safety Incidents (LTIFR)",
}


def load_extracted():
    """Load all extracted JSONs into a dict keyed by (company, fy)."""
    data = {}
    for path in sorted(EXTRACTED_DIR.glob("*.json")):
        with open(path) as f:
            rec = json.load(f)
        key = (rec["company"], rec["fy"])
        data[key] = rec
    return data


def load_kpis():
    """Load kpis.json into a DataFrame."""
    with open(KPI_PATH) as f:
        records = json.load(f)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Deliverable 1: Single-company flat table
# ---------------------------------------------------------------------------
def build_flat_table(extracted, kpi_df):
    """One row per company × FY × principle. Columns: Essential#, Leadership#,
    plus one column per KPI value (only filled for the matching principle)."""
    rows = []
    for company in COMPANY_ORDER:
        for fy in FY_ORDER:
            rec = extracted.get((company, fy))
            if not rec:
                continue
            # Get KPI values for this company-FY
            company_kpis = kpi_df[(kpi_df["company"] == company) & (kpi_df["fy"] == fy)]
            kpi_map = {}
            for _, row in company_kpis.iterrows():
                kpi_map[row["kpi"]] = row["value"]

            for principle in rec.get("principles", []):
                pno = principle["principle_no"]
                row = {
                    "Company": company,
                    "FY": fy,
                    "Principle No": pno,
                    "Principle": f"P{pno} - {PRINCIPLE_NAMES.get(pno, '')}",
                    "Essential Indicators": len(principle.get("essential_indicators", [])),
                    "Leadership Indicators": len(principle.get("leadership_indicators", [])),
                }
                # Add KPI values for matching principles
                for kpi_name, kpi_label in KPI_LABELS.items():
                    if KPI_TO_PRINCIPLE.get(kpi_name) == pno:
                        row[kpi_label] = kpi_map.get(kpi_name)
                rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Deliverable 2: Cross-company KPI benchmark
# ---------------------------------------------------------------------------
def build_benchmark(kpi_df):
    """Rows = KPIs, Columns = companies (latest FY) + summary stats."""
    # Use latest FY available per company
    latest_fy = {}
    for company in COMPANY_ORDER:
        company_data = kpi_df[kpi_df["company"] == company]
        fys = sorted(company_data["fy"].dropna().unique(), reverse=True)
        if fys:
            latest_fy[company] = fys[0]

    rows = []
    for kpi in ["ghg_intensity", "water_intensity", "employee_turnover_rate",
                "gender_pay_gap", "safety_incident_rate"]:
        row = {"KPI": KPI_LABELS.get(kpi, kpi)}
        values = []
        for company in COMPANY_ORDER:
            fy = latest_fy.get(company)
            if fy:
                val = kpi_df[
                    (kpi_df["company"] == company) &
                    (kpi_df["fy"] == fy) &
                    (kpi_df["kpi"] == kpi)
                ]["value"].values
                v = val[0] if len(val) > 0 else None
            else:
                v = None
            row[f"{company} ({latest_fy.get(company, 'N/A')})"] = v
            if v is not None:
                values.append(v)
        row["Min"] = min(values) if values else None
        row["Max"] = max(values) if values else None
        row["Avg"] = round(sum(values) / len(values), 4) if values else None
        row["N"] = len(values)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Deliverable 3: Time-series per company
# ---------------------------------------------------------------------------
def build_timeseries(kpi_df):
    """One table per KPI. Rows = companies, Columns = FYs."""
    sheets = {}
    for kpi in ["ghg_intensity", "water_intensity", "employee_turnover_rate",
                "gender_pay_gap", "safety_incident_rate"]:
        label = KPI_LABELS.get(kpi, kpi)
        pivot = kpi_df[kpi_df["kpi"] == kpi].pivot_table(
            index="company", columns="fy", values="value", aggfunc="first"
        )
        # Reorder
        pivot = pivot.reindex(index=COMPANY_ORDER, columns=FY_ORDER)
        pivot.index.name = "Company"
        pivot.columns.name = None
        sheets[label] = pivot.reset_index()
    return sheets


# ---------------------------------------------------------------------------
# Deliverable 4: Essential vs Leadership completion rate
# ---------------------------------------------------------------------------
def build_completion_rate(extracted):
    """One row per company × FY × principle. Columns: Essential#, Leadership#,
    total expected, completion %."""
    # BRSR Section C has 9 principles. Expected indicator counts vary by
    # company/year but we compute what was actually extracted.
    rows = []
    for company in COMPANY_ORDER:
        for fy in FY_ORDER:
            rec = extracted.get((company, fy))
            if not rec:
                continue
            total_essential = 0
            total_leadership = 0
            for principle in rec.get("principles", []):
                pno = principle["principle_no"]
                n_ess = len(principle.get("essential_indicators", []))
                n_lead = len(principle.get("leadership_indicators", []))
                total_essential += n_ess
                total_leadership += n_lead
                rows.append({
                    "Company": company,
                    "FY": fy,
                    "Principle No": pno,
                    "Principle": f"P{pno} - {PRINCIPLE_NAMES.get(pno, '')}",
                    "Essential Indicators": n_ess,
                    "Leadership Indicators": n_lead,
                    "Total Indicators": n_ess + n_lead,
                })
            # Add a summary row
            n_principles = len(rec.get("principles", []))
            rows.append({
                "Company": company,
                "FY": fy,
                "Principle No": "TOTAL",
                "Principle": "ALL PRINCIPLES",
                "Essential Indicators": total_essential,
                "Leadership Indicators": total_leadership,
                "Total Indicators": total_essential + total_leadership,
            })
    return pd.DataFrame(rows)


def main():
    print("Loading data...")
    extracted = load_extracted()
    kpi_df = load_kpis()
    print(f"  {len(extracted)} extracted reports, {len(kpi_df)} KPI records")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building Deliverable 1: Flat Table...")
    flat = build_flat_table(extracted, kpi_df)

    print("Building Deliverable 2: KPI Benchmark...")
    benchmark = build_benchmark(kpi_df)

    print("Building Deliverable 3: Time Series...")
    ts_sheets = build_timeseries(kpi_df)

    print("Building Deliverable 4: Completion Rate...")
    completion = build_completion_rate(extracted)

    print(f"Writing {OUT_PATH.relative_to(ROOT)}...")
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        flat.to_excel(writer, sheet_name="Flat_Table", index=False)
        benchmark.to_excel(writer, sheet_name="KPI_Benchmark", index=False)
        for label, df in ts_sheets.items():
            # Sheet names max 31 chars, no invalid characters
            sheet = label[:31].replace("/", "-").replace("\\", "-")
            df.to_excel(writer, sheet_name=sheet, index=False)
        completion.to_excel(writer, sheet_name="Completion_Rate", index=False)

    print(f"Done! Wrote {OUT_PATH}")
    print(f"  Sheet: Flat_Table       ({len(flat)} rows)")
    print(f"  Sheet: KPI_Benchmark    ({len(benchmark)} rows)")
    for label, df in ts_sheets.items():
        print(f"  Sheet: {label[:25]:25s} ({len(df)} rows)")
    print(f"  Sheet: Completion_Rate  ({len(completion)} rows)")


if __name__ == "__main__":
    main()
