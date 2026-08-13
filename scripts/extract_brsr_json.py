"""
Extract a BRSR (Business Responsibility & Sustainability Report) PDF into a
structured JSON database.

Usage:
    python extract_brsr_json.py <input.pdf> [output.json]

What it does:
    1. Reads the PDF page by page with PyMuPDF.
    2. Splits the text into the 9 NGRBC Principle sections (Section C of a
       BRSR), plus a "general" bucket for everything before Principle 1
       (Section A/B disclosures) and everything after Principle 9
       (Assurance Statement, etc).
    3. Within each principle, splits further into "Essential Indicators"
       and "Leadership Indicators".
    4. Within each indicator block, splits on the numbered-question pattern
       (e.g. "1.", "2.", "10.") so each item keeps its question + the raw
       text that follows it (tables get flattened to text by PyMuPDF, so the
       "answer" field is the best-effort raw block, not a clean value).

The output JSON is intentionally a straightforward, literal structure -
good as a searchable database of the whole document. Pulling out single
clean "KPI: value" pairs for a spreadsheet still benefits from a human (or
an LLM) reading the raw block, because BRSR tables come out as flattened
text with no reliable column markers.
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

PRINCIPLE_RE = re.compile(r"PRINCIPLE\s+(\d+)[.:]?\s*(.*)", re.IGNORECASE)
INDICATOR_HEADER_RE = re.compile(r"^(Essential Indicators|Leadership Indicators)\s*$", re.MULTILINE)
ITEM_RE = re.compile(r"(?:^|\n)(\d{1,2})\.\s+")
ASSURANCE_RE = re.compile(r"Independent Assurance Statement", re.IGNORECASE)


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
    headers = list(INDICATOR_HEADER_RE.finditer(principle_text))
    result = {}
    for i, h in enumerate(headers):
        label = h.group(1)
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(principle_text)
        block = principle_text[start:end].strip()
        key = "essential_indicators" if "Essential" in label else "leadership_indicators"
        result[key] = split_indicator_items(block)
    return result


def build_structure(pdf_path):
    pages = extract_pages(pdf_path)
    full_text = "\n".join(pages)

    principle_matches = list(PRINCIPLE_RE.finditer(full_text))
    assurance_match = ASSURANCE_RE.search(full_text)

    general_end = principle_matches[0].start() if principle_matches else len(full_text)
    general_disclosures = full_text[:general_end].strip()

    principles = []
    for i, m in enumerate(principle_matches):
        start = m.end()
        end = principle_matches[i + 1].start() if i + 1 < len(principle_matches) else (
            assurance_match.start() if assurance_match else len(full_text)
        )
        body = full_text[start:end].strip()
        principles.append(
            {
                "principle_no": int(m.group(1)),
                "title": m.group(2).strip().split("\n")[0].strip(" .:"),
                **split_indicator_types(body),
            }
        )

    assurance_statement = full_text[assurance_match.start():].strip() if assurance_match else None

    return {
        "source_file": Path(pdf_path).name,
        "page_count": len(pages),
        "general_disclosures": general_disclosures,
        "principles": principles,
        "assurance_statement": assurance_statement,
        "pages": [{"page": i + 1, "text": t} for i, t in enumerate(pages)],
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(pdf_path).with_suffix(".json"))

    data = build_structure(pdf_path)

    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}")
    print(f"  pages: {data['page_count']}")
    print(f"  principles found: {len(data['principles'])}")
    for p in data["principles"]:
        print(
            f"    Principle {p['principle_no']}: "
            f"{len(p.get('essential_indicators', []))} essential, "
            f"{len(p.get('leadership_indicators', []))} leadership indicators"
        )


if __name__ == "__main__":
    main()
