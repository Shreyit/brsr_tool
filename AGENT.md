# AGENT.md

Operating notes for an agent (or new contributor) picking up this repo
mid-stream. Read this and `PLAN.md` before touching `src/` or `data/`.

## Environment

- Python venv at `.venv/` — activate with `source .venv/bin/activate`.
- Key packages: `pymupdf` (imported as `fitz`) for PDF text extraction,
  `pandas` / `numpy` for analysis, `matplotlib` for charts, `openpyxl` for
  xlsx I/O.
- No git repo here (`git init` if the user wants version history before
  larger edits).

## Directory map

- `brsr_reports_pdf/` — raw source PDFs. Filename convention is
  `COMPANY_FYSTART-FYEND.pdf` (e.g. `AXIS_2023-2024.pdf`). This is the only
  supported format: if a filename doesn't match, `extract.py`'s
  `parse_filename` silently falls back to the bare stem as company and `None`
  as fy — check for that rather than assuming every file parsed correctly.
- `data/extracted/` — one JSON per PDF, output of `src/extraction/extract.py`.
  Schema: `source_file, company, fy, page_count, general_disclosures,
  principles[], assurance_statement, full_text`. Each `principles[]` entry is
  `{principle_no, title, essential_indicators[], leadership_indicators[]}`,
  each indicator is `{no, question, text}`.
- `data/kpis.json` — output of `src/kpi/parse_kpis.py`. Flat list of
  `{company, fy, kpi, value, prior_year_value, unit}`, 5 KPI rows per report.
- `data/output/` — empty; deliverable exports (tables, charts) should land
  here.
- `scripts/extract_brsr_json.py` — an earlier, standalone extraction script.
  Likely superseded by `src/extraction/extract.py` (see `PLAN.md` known
  issues) — don't build on it without checking with the user first.
- `brsr_shreyit.xlsx` — hand-built reference table (`Principle | KPI | Value`,
  9 rows, one company/FY). Treat as a target-shape reference, not pipeline
  output, unless told otherwise.

## How to run the pipeline

```bash
source .venv/bin/activate
python -m src.extraction.extract          # all PDFs -> data/extracted/*.json
python -m src.extraction.extract <one.pdf> # single file
python -m src.kpi.parse_kpis               # data/extracted/*.json -> data/kpis.json
```

## Conventions to preserve

- **KPI parsing is anchor-based** (regex on fixed BRSR phrasing), not
  table-structure-based. PyMuPDF flattens tables to plain text with no
  reliable column markers, so this is deliberate — see the module docstring
  in `src/kpi/parse_kpis.py`. Don't "fix" a KPI parser by trying to detect
  table columns; anchor on more specific surrounding text instead.
- **Section-break detection in `extract.py` uses validating heuristics**: a
  candidate "Principle N" or "Essential/Leadership Indicators" heading only
  counts as real if expected content (the NGRBC statement text / a numbered
  item) follows within a bounded window. This exists because heading
  casing/format varies a lot across companies and years, and a single fixed
  regex produces false positives from tables of contents and cross-reference
  call-outs (e.g. "as reported in Q11 ... above"). Don't replace it with a
  simple regex — that's what `scripts/extract_brsr_json.py` does, and it's
  the reason that script is considered less reliable.
- **`_norm()` collapses whitespace before every KPI regex match** because PDF
  text wraps mid-phrase (e.g. "per rupee \n of turnover"). Any new KPI parser
  function should call it first, same as the existing ones.

## Known bugs (full detail in `PLAN.md`)

- `ghg_intensity` parser is broken for ~9/10 reports — it captures the "1"
  and "2" from the phrase "Scope 1 and Scope 2" instead of the real values.
  Fix before using this KPI in any deliverable.
- `gender_pay_gap` never returns a `prior_year_value`.
- KOTAK is missing FY2024-25 and FY2025-26 source PDFs.

## Testing

No test suite exists yet. Sanity-check any parser change against the printed
`found/5` counts from `python -m src.kpi.parse_kpis`, and spot-check a couple
of `data/kpis.json` records against the source PDF text directly.
