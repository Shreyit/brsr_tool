# BRSR ESG KPI Extraction & Analysis — Plan

Reconstructed from repo state (no git history, no persisted task list). Last checked: 2026-08-14.

## Objective

Turn BRSR (Business Responsibility & Sustainability Report) PDF filings for four
Indian banks — AXIS, HDFC, ICICI, KOTAK — across FY2023-24 / FY2024-25 / FY2025-26
into structured data, then produce cross-company and cross-year ESG KPI deliverables.

## Data inventory

- `brsr_reports_pdf/` — 10 source PDFs. AXIS, HDFC, ICICI each have all 3 FYs;
  **KOTAK has only FY2023-2024**.
- `data/extracted/` — 10 JSONs, one per PDF (mirrors the same KOTAK gap), output
  of `src/extraction/extract.py`.
- `data/kpis.json` — 50 records (10 report-years × 5 KPIs), output of
  `src/kpi/parse_kpis.py`.
- `data/output/` — empty. No deliverable exports produced yet.
- `brsr_shreyit.xlsx` — a hand-built 9-row table (Principle | KPI | Value, one
  principle per row, single company/FY). Predates the pipeline (older timestamp
  than `src/`) — looks like a manual reference for the target shape of
  Deliverable 1, not pipeline output.

## Completed

1. **Extraction pipeline** (`src/extraction/extract.py`) — splits each PDF into
   `general_disclosures`, `principles[1..9]` (each with `essential_indicators`
   / `leadership_indicators`), and `assurance_statement`, using validating
   heuristics for section headers so it survives inconsistent formatting across
   banks (its docstring specifically calls out fixing `ICICI_2025-2026`, whose
   section split is unreliable with naive regex).
2. Ran extraction across all 10 available PDFs → `data/extracted/*.json`.
3. **Targeted numeric KPI parser** (`src/kpi/parse_kpis.py`) — pulls 5
   comparable numeric KPIs per report by anchoring on fixed BRSR phrasing
   rather than relying on table column structure: `ghg_intensity`,
   `water_intensity`, `employee_turnover_rate`, `gender_pay_gap`,
   `safety_incident_rate` (LTIFR). Output: `data/kpis.json`.

This matches the "Build targeted numeric KPI parser" item shown as
running/completed in the last visible status, and is most likely 2 of the "3
completed" tasks referenced in the truncated status line.

## Known issues — fix before trusting the numbers

- **`ghg_intensity` is wrong for ~9 of 10 rows.** It returns `value=1.0,
  prior_year_value=2.0` almost everywhere. Root cause: in
  `parse_ghg_intensity` (`src/kpi/parse_kpis.py:63`), the number-search window
  starts right after the anchor phrase *"Total Scope 1 and Scope 2 emission
  intensity per rupee of turnover"* — but the phrase itself contains the
  digits "1" and "2" ("Scope **1**... Scope **2**"), so `_first_two_numbers`
  is capturing those instead of the real intensity figures that follow. Needs
  the anchor moved past "turnover" (or past the first unit token) before
  scanning for numbers. HDFC's two most recent FYs instead return
  `null, null`, suggesting its phrasing diverges enough to miss the anchor
  match entirely for that company.
- **`gender_pay_gap.prior_year_value` is always `null`** — the parser only
  extracts the current year's male/female medians and never captures a prior
  year figure even where the source table has one.
- **KOTAK is missing FY2024-25 and FY2025-26 PDFs.** Any cross-company or
  time-series deliverable is incomplete for KOTAK until those are sourced (or
  KOTAK is explicitly excluded from those views).
- **Two extraction implementations exist.** `scripts/extract_brsr_json.py` is
  an earlier, simpler pass (fixed regex, no validation heuristics, keeps full
  per-page text instead of `full_text`). `src/extraction/extract.py` is the
  one actually used to produce `data/extracted/` — it looks superseded but
  hasn't been removed. Confirm with the user before deleting.

## Deliverables

Only 4 of what the prior session's status line implied was a 9-item list
(`... +5 pending, 3 completed`) were visible when this doc was written:

| # | Deliverable | Status |
|---|---|---|
| 1 | Single-company Section C flat table | Not started. `data/output/` is empty; `brsr_shreyit.xlsx` may be the target shape to match. |
| 2 | Cross-company KPI benchmark table + chart | Not started. |
| 3 | Per-company KPI time series across FY23-24/24-25/25-26 | Not started. Blocked on the KOTAK data gap for full coverage. |
| 4 | Essential vs Leadership completion rate | Not started. Inputs already exist: `principles[].essential_indicators` / `leadership_indicators` counts in `data/extracted/*.json`. |
| 5-9 | **Unknown — not recovered** | The original task list had 5 more pending items not captured in the pasted status. Reconcile with the prior session if you still have it. |

## Open questions for the user

- What were deliverables 5-9?
- Is `scripts/extract_brsr_json.py` safe to delete?
- Are the missing KOTAK FY24-25 / FY25-26 PDFs available anywhere, or should
  KOTAK be dropped from cross-year comparisons?
- Is `brsr_shreyit.xlsx` a reference to match, or an already-completed
  deliverable to extend?

## Suggested next steps

1. Fix the `ghg_intensity` parser bug — highest priority, it's silently wrong
   almost everywhere it returns a value.
2. Fix (or explicitly accept as a known gap) `gender_pay_gap`'s missing
   prior-year figure.
3. Resolve the KOTAK PDF gap one way or the other.
4. Build Deliverable 1, matching `brsr_shreyit.xlsx`'s shape if that's the
   intended target.
5. Build Deliverables 2-4.
6. Recover/reconcile deliverables 5-9 from the original list.
