"""
Extract every BRSR PDF in brsr_reports_pdf/ into a structured JSON database.

Usage:
    python -m src.extraction.extract                # process all PDFs in brsr_reports_pdf/
    python -m src.extraction.extract <one.pdf>       # process a single file

For each PDF, writes data/extracted/<COMPANY>_<FY>.json with:
    - company, fy (parsed from filename "COMPANY_FYSTART-FYEND.pdf")
    - general_disclosures (Section A/B, everything before Principle 1)
    - principles: list of {principle_no, title, essential_indicators, leadership_indicators}
      each indicator item = {no, question, text}
    - assurance_statement

BRSR tables get flattened to text by PyMuPDF (no reliable column markers), so
"text" is the best-effort raw block for each numbered item. Clean numeric
KPI values are pulled out separately in src/kpi/parse_kpis.py, which anchors
on known indicator phrasing rather than trying to parse every table generically.
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "brsr_reports_pdf"
OUT_DIR = ROOT / "data" / "extracted"

# Heading casing/format for "PRINCIPLE N ..." and "Essential/Leadership
# Indicators" varies a lot across companies and years (ALL CAPS vs mixed
# case, tab vs space, a running page-header wedged in between). Rather than
# one fixed regex, both section breaks are detected with a validating
# heuristic: a candidate match only counts as a real section break if real
# content (the fixed NGRBC statement text / a "1." numbered item) follows it
# within a bounded window. This filters out the many false positives that
# show up in tables of contents, cross-reference call-outs ("as reported in
# Q11 of Essential Indicators above") and policy-link summaries.
PRINCIPLE_CANDIDATE_RE = re.compile(r"\bPrinciple\s+(\d)\b", re.IGNORECASE)
BUSINESSES_RE = re.compile(r"Businesses", re.IGNORECASE)
INDICATOR_HEADER_CANDIDATE_RE = re.compile(r"(Essential Indicators|Leadership Indicators)", re.IGNORECASE)
BACKREF_RE = re.compile(r"\s*above", re.IGNORECASE)
ITEM_RE = re.compile(r"(?:^|\n)[\s\x07•]*(\d{1,2})\.\s+")
ASSURANCE_RE = re.compile(r"Independent Assurance Statement", re.IGNORECASE)
FILENAME_RE = re.compile(r"^([A-Za-z]+)_(\d{4}-\d{4})$")

BUSINESSES_WINDOW = 100  # chars after "Principle N" to look for "Businesses"
INDICATOR_ITEM_WINDOW = 500  # chars after a header candidate to find "1."
FALLBACK_WINDOW = 15000  # chars after a fallback "Principle N" candidate to look for both indicator headers


def find_indicator_headers(text):
    """Real (position, label) pairs for 'Essential/Leadership Indicators'
    headers: the candidate must not be an "... above" backreference, and a
    numbered item ("1.") must start within INDICATOR_ITEM_WINDOW chars."""
    headers = []
    for m in INDICATOR_HEADER_CANDIDATE_RE.finditer(text):
        tail = text[m.end():m.end() + 20]
        if BACKREF_RE.match(tail):
            continue
        window = text[m.end():m.end() + INDICATOR_ITEM_WINDOW]
        item_m = ITEM_RE.search(window)
        # Ideally the first item is "1.", but multi-column pages can shuffle
        # PyMuPDF's text order so the true item 1 lands elsewhere; accept any
        # low item number as still-real content, just not a coincidental
        # numbered list buried deep in an unrelated paragraph.
        if not item_m or int(item_m.group(1)) > 5:
            continue
        item_start = m.end() + item_m.start(1)
        label = "essential_indicators" if "essential" in m.group(1).lower() else "leadership_indicators"
        headers.append((m.start(), item_start, label))
    return headers


def find_principle_headers(text):
    """Real (position, principle_no) pairs for 'PRINCIPLE N' section
    headings: the candidate must be followed shortly by "Businesses" (the
    fixed NGRBC statement always starts "Businesses should..."/"Businesses,
    when..."), and its segment (up to the next candidate) must contain at
    least one real Essential/Leadership Indicators header."""
    raw_candidates = []
    for m in PRINCIPLE_CANDIDATE_RE.finditer(text):
        tail = text[m.end():m.end() + BUSINESSES_WINDOW]
        if BUSINESSES_RE.search(tail):
            raw_candidates.append((m.start(), int(m.group(1))))

    real = []
    for i, (pos, no) in enumerate(raw_candidates):
        end = raw_candidates[i + 1][0] if i + 1 < len(raw_candidates) else len(text)
        segment = text[pos:end]
        if find_indicator_headers(segment):
            real.append((pos, no))

    found_nos = {no for _, no in real}
    missing = set(range(1, 10)) - found_nos
    if missing:
        real.extend(find_principle_headers_fallback(text, missing))
        real.sort(key=lambda item: item[0])
    return real


def find_principle_headers_fallback(text, missing):
    """Recovers principle numbers the primary heuristic missed entirely.

    Some filings (e.g. a BRSR bundled into a much larger Integrated Annual
    Report) skip the NGRBC "Businesses should..." statement right after the
    "PRINCIPLE N" heading and jump straight into indicator content, so the
    primary pass's "Businesses" check never fires for the real header.
    Only called for principle numbers still missing after the primary pass,
    so it can't regress filings that already extract cleanly. Requires BOTH
    an essential and a leadership indicator header within FALLBACK_WINDOW
    chars, to reject stray cross-references (e.g. annexure indicator-mapping
    lists like "Principle 1: Essential Indicator 1, Leadership Indicator 1")."""
    recovered = {}
    for m in PRINCIPLE_CANDIDATE_RE.finditer(text):
        no = int(m.group(1))
        if no not in missing or no in recovered:
            continue
        window = text[m.end():m.end() + FALLBACK_WINDOW]
        labels = {label for _, _, label in find_indicator_headers(window)}
        if {"essential_indicators", "leadership_indicators"} <= labels:
            recovered[no] = m.start()
    return [(pos, no) for no, pos in recovered.items()]


def parse_filename(pdf_path):
    stem = Path(pdf_path).stem
    m = FILENAME_RE.match(stem)
    if not m:
        return stem, None
    return m.group(1).upper(), m.group(2)


def extract_pages(pdf_path):
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return pages


def split_indicator_items(block_text):
    """Split an Essential/Leadership Indicators block into numbered items."""
    matches = list(ITEM_RE.finditer(block_text))
    items = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block_text)
        no = m.group(1)
        text = block_text[start:end].strip()
        question = text.split("\n")[0].strip()
        items.append({"no": no, "question": question, "text": text})
    return items


def split_indicator_types(principle_text):
    headers = find_indicator_headers(principle_text)
    result = {"essential_indicators": [], "leadership_indicators": []}
    for i, (_header_pos, item_start, label) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else len(principle_text)
        block = principle_text[item_start:end].strip()
        result[label] = split_indicator_items(block)
    return result


def build_structure(pdf_path):
    pages = extract_pages(pdf_path)
    full_text = "\n".join(pages)
    company, fy = parse_filename(pdf_path)

    principle_headers = find_principle_headers(full_text)
    assurance_match = ASSURANCE_RE.search(full_text)

    general_end = principle_headers[0][0] if principle_headers else len(full_text)
    general_disclosures = full_text[:general_end].strip()

    principles = []
    for i, (pos, no) in enumerate(principle_headers):
        start = pos
        end = principle_headers[i + 1][0] if i + 1 < len(principle_headers) else (
            assurance_match.start() if assurance_match else len(full_text)
        )
        body = full_text[start:end].strip()
        biz_m = BUSINESSES_RE.search(body[:200])
        title_raw = body[biz_m.start():biz_m.start() + 200] if biz_m else body[:200]
        title = re.sub(r"\s+", " ", title_raw.split("\n\n")[0]).strip(" .:")
        principles.append(
            {
                "principle_no": no,
                "title": title,
                **split_indicator_types(body),
            }
        )

    assurance_statement = full_text[assurance_match.start():].strip() if assurance_match else None

    return {
        "source_file": Path(pdf_path).name,
        "company": company,
        "fy": fy,
        "page_count": len(pages),
        "general_disclosures": general_disclosures,
        "principles": principles,
        "assurance_statement": assurance_statement,
        "full_text": full_text,
    }


def process_one(pdf_path, out_dir=OUT_DIR):
    data = build_structure(pdf_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{data['company']}_{data['fy']}.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    n_essential = sum(len(p["essential_indicators"]) for p in data["principles"])
    n_leadership = sum(len(p["leadership_indicators"]) for p in data["principles"])
    print(
        f"{data['company']:8s} {data['fy']:10s} -> {out_path.relative_to(ROOT)}  "
        f"({data['page_count']} pages, {len(data['principles'])} principles, "
        f"{n_essential} essential + {n_leadership} leadership items)"
    )
    return out_path


def main():
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted(PDF_DIR.glob("*.pdf"))

    if not targets:
        print(f"No PDFs found in {PDF_DIR}")
        sys.exit(1)

    for pdf_path in targets:
        process_one(pdf_path)


if __name__ == "__main__":
    main()
