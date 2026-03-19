import json
import re
import pathlib
import urllib.request
from collections import defaultdict

import pdfplumber

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw_sources"
OUT_DIR = REPO_ROOT / "standards" / "common-core" / "math"

PDF_URL = "https://learning.ccsso.org/wp-content/uploads/2022/11/ADA-Compliant-Math-Standards.pdf"
PDF_PATH = RAW_DIR / "ADA-Compliant-Math-Standards.pdf"

OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

GRADE_LABELS = {
    "K": "grade-k",
    "1": "grade-1",
    "2": "grade-2",
    "3": "grade-3",
    "4": "grade-4",
    "5": "grade-5",
    "6": "grade-6",
    "7": "grade-7",
    "8": "grade-8",
    "HS": "high-school",
}

DOMAIN_NAMES = {
    "CC": "Counting and Cardinality",
    "OA": "Operations and Algebraic Thinking",
    "NBT": "Number and Operations in Base Ten",
    "NF": "Number and Operations in Base Ten",
    "MD": "Measurement and Data",
    "G": "Geometry",
    "RP": "Ratios and Proportional Relationships",
    "NS": "The Number System",
    "EE": "Expressions and Equations",
    "F": "Functions",
    "SP": "Statistics and Probability",
    "N": "Number and Quantity",
    "A": "Algebra",
    "S": "Statistics and Probability",
}

CODE_RE = re.compile(
    r'\b(K|[1-8]|HS)\.(CC|OA|NBT|NF|MD|G|RP|NS|EE|F|SP|N|A|S)\.[A-Z0-9]+\.\d+\b'
)

def download_pdf():
    if PDF_PATH.exists():
        print(f"Using existing PDF: {PDF_PATH}")
        return
    print(f"Downloading PDF from {PDF_URL} ...")
    urllib.request.urlretrieve(PDF_URL, PDF_PATH)
    print(f"Saved PDF to {PDF_PATH}")

def clean_text(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r'[ \t]+', ' ', text)
    return text

def extract_full_text():
    chunks = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
            else:
                print(f"Warning: page {i + 1} had no extracted text")
    full_text = "\n".join(chunks)
    full_text = clean_text(full_text)
    print(f"Extracted {len(full_text)} characters from PDF")
    return full_text

def parse_standards(full_text: str):
    matches = list(CODE_RE.finditer(full_text))
    print(f"Found {len(matches)} standard code matches")

    grouped = defaultdict(list)

    if not matches:
        return grouped

    for i, match in enumerate(matches):
        code = match.group(0)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        statement = full_text[start:end].strip()
        statement = re.sub(r'\s+', ' ', statement)

        grade_code = code.split(".")[0]
        domain_code = code.split(".")[1]

        grade_key = GRADE_LABELS.get(grade_code)
        if not grade_key:
            continue

        grouped[grade_key].append({
            "code": code,
            "statement": statement,
            "domain_code": domain_code,
            "domain": DOMAIN_NAMES.get(domain_code, ""),
            "tags": [domain_code.lower()] if domain_code else []
        })

    for grade_key, standards in grouped.items():
        seen = set()
        deduped = []
        for s in standards:
            if s["code"] not in seen:
                seen.add(s["code"])
                deduped.append(s)
        grouped[grade_key] = deduped

    return grouped

def write_outputs(grouped):
    if not grouped:
        print("No grouped standards were produced.")
        return

    for grade_key, standards in grouped.items():
        payload = {
            "framework": "Common Core",
            "subject": "math",
            "grade": grade_key,
            "source": PDF_URL,
            "license_note": (
                "Common Core State Standards text sourced from the official CCSSO-hosted ADA-compliant Mathematics standards PDF. "
                "See Common Core public license for permitted use and attribution requirements."
            ),
            "standards": standards,
        }

        out_path = OUT_DIR / f"{grade_key}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"Wrote {out_path} ({len(standards)} standards)")

def main():
    download_pdf()
    full_text = extract_full_text()
    grouped = parse_standards(full_text)
    write_outputs(grouped)

if __name__ == "__main__":
    main()