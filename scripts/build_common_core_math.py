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
    "NF": "Number and Operations—Fractions",
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

STOP_PATTERNS = [
    r'COMMON CORE STATE STANDARDS for MATHEMATICS',
    r'Mathematics \| Grade [K1-8]',
    r'GRADE [K1-8] \| \d+',
    r'Grade [K1-8] Overview',
    r'Number and Operations in Base Ten',
    r'Number and Operations-Fractions',
    r'Operations and Algebraic Thinking',
    r'Measurement and Data',
    r'Geometry',
    r'The Number System',
    r'Expressions and Equations',
    r'Ratios and Proportional Relationships',
    r'Statistics and Probability',
    r'Functions',
    r'Number and Quantity',
    r'Algebra',
    r'A\.[A-Z]',
    r'B\.[A-Z]',
    r'C\.[A-Z]',
    r'D\.[A-Z]',
    r'Grade [1-8] Overview',
    r'Mathematical Practices',
    r'In Grade [1-8], instructional time should focus on',
]

FOOTNOTE_RE = re.compile(r'\b\d+See Glossary.*$', re.IGNORECASE)
TRAILING_NUM_RE = re.compile(r'\s+\d+\.$')
GRADE_TRANSITION_RE = re.compile(r'Mathematics \| Grade [K1-8].*$', re.IGNORECASE)

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
    text = text.replace("�", "?")
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

def trim_statement(statement: str) -> str:
    statement = re.sub(r'\s+', ' ', statement).strip()

    for pattern in STOP_PATTERNS:
        m = re.search(pattern, statement)
        if m:
            statement = statement[:m.start()].strip()

    statement = FOOTNOTE_RE.sub("", statement)
    statement = GRADE_TRANSITION_RE.sub("", statement)
    statement = TRAILING_NUM_RE.sub("", statement)

    # remove stray leading bullets or labels
    statement = re.sub(r'^[a-d]\.\s*', lambda m: m.group(0), statement)

    # collapse spaces again after trimming
    statement = re.sub(r'\s+', ' ', statement).strip()

    return statement

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

        raw_statement = full_text[start:end].strip()
        statement = trim_statement(raw_statement)

        if not statement:
            continue

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