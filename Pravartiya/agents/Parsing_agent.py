# conda activate tejomaya
# python -m agents.newsletter_parsing_agent

#!/usr/bin/env python
# agents/newsletter_parsing_agent.py
# ============================================================
# PRAVARTIYA NEWSLETTER PARSING AGENT (TEJOMAYA v1)
# Processes SEBI Regulation PDFs that do NOT have
# "last amended on" / "amended as on" in their title,
# checks for Official Gazette effective date logic,
# and produces structured newsletter-style summaries.
#
# NOTE: Uses month_range.json (not week_range.json) because
# Pravartiya is a monthly newsletter covering one full month
# of SEBI data.  Expected format:
#   {"month_start": "2026-04-01", "month_end": "2026-04-30"}
# ============================================================

import sys
from pathlib import Path

# Force project root into PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from storage.minio_client import MinIOClient

import os
import re
import json
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf
from openpyxl import load_workbook, Workbook
from datetime import datetime
import torch
import warnings
import time

from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate

# ---------------------- Logging ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

warnings.filterwarnings("ignore")
load_dotenv()

# ---------------------- GPU Detection ----------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if device.type == "cuda":
    os.environ["OLLAMA_USE_GPU"] = "1"
    os.environ["OLLAMA_NUM_GPU_LAYERS"] = "35"
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")
else:
    os.environ["OLLAMA_USE_GPU"] = "0"
    print("Using CPU")

# ---------------------- LLM ----------------------
llm = Ollama(model="mistral:latest")

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_EXCEL_DIR = DATA_DIR / "output_excels"
OUTPUT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

CREATED_EXCELS = set()

# ============================================================
# MONTHLY FOLDER
# Pravartiya covers one full calendar month of SEBI data.
# Reads month_range.json produced by the newsletter searching agent.
# Expected JSON format:
#   {"month_start": "2026-04-01", "month_end": "2026-04-30"}
# Output folder pattern: newsletter_2026-04-01_to_2026-04-30
# ============================================================

def get_month_folder() -> Path:
    month_json = DATA_DIR / "month_range.json"
    if not month_json.exists():
        raise RuntimeError(
            "month_range.json not found in data/. "
            "Run the newsletter searching agent first to generate it. "
            "Expected format: "
            '{"month_start": "2026-04-01", "month_end": "2026-04-30"}'
        )

    with open(month_json, "r") as f:
        month = json.load(f)

    for key in ("month_start", "month_end"):
        if key not in month:
            raise KeyError(
                f"month_range.json is missing the '{key}' key. "
                f'Expected: {{"month_start": "YYYY-MM-01", "month_end": "YYYY-MM-DD"}}'
            )

    ms = datetime.strptime(month["month_start"], "%Y-%m-%d")
    me = datetime.strptime(month["month_end"], "%Y-%m-%d")

    # e.g. newsletter_2026-04-01_to_2026-04-30
    folder = OUTPUT_EXCEL_DIR / f"newsletter_{ms:%Y-%m-%d}_to_{me:%Y-%m-%d}"

    # Always start fresh so re-runs are idempotent
    if folder.exists():
        import shutil
        shutil.rmtree(folder)

    folder.mkdir(parents=True)
    logging.info(f"Month range  : {ms:%d %B %Y} -> {me:%d %B %Y}")
    logging.info(f"Output folder: {folder}")
    return folder


MONTH_FOLDER = get_month_folder()
logging.info(f"Monthly newsletter folder -> {MONTH_FOLDER}")


# ============================================================
# STEP 1 — TITLE FILTER
# Check if title contains "last amended on" or "amended as on"
# If YES  → skip this PDF (not for newsletter)
# If NO   → proceed to effective date check
# ============================================================

AMENDED_TITLE_PATTERN = re.compile(
    r'last\s+amended\s+on|amended\s+as\s+on',
    re.IGNORECASE
)

def is_amended_title(title: str) -> bool:
    """Return True if title already carries an amendment-date label."""
    if not isinstance(title, str):
        return False
    return bool(AMENDED_TITLE_PATTERN.search(title))


# ============================================================
# STEP 2 — GAZETTE EFFECTIVE DATE DETECTION
# Look for "They shall come into force on the date of their
# publication in the Official Gazette" inside the PDF text.
# If found → effective date = the notification date at top of doc
# ============================================================

GAZETTE_FORCE_PATTERN = re.compile(
    r'they\s+shall\s+come\s+into\s+force\s+on\s+the\s+date\s+of\s+their\s+publication\s+in\s+the\s+official\s+gazette',
    re.IGNORECASE
)

# Patterns for the notification date at the top of SEBI PDFs.
# unstructured "fast" strategy can merge lines, so we scan a wider window
# and use multiple patterns from most-specific to broadest fallback.
#
# Target examples:
#   "Mumbai, the 15th April, 2026"
#   "New Delhi, the 3rd March 2025"
#   "MUMBAI, THE 15TH APRIL, 2026"  (all-caps in some PDFs)

# All known SEBI notification city names (covers most regulation PDFs)
_CITY_PAT = (
    r"(?:mumbai|bombay|new\s+delhi|delhi|hyderabad|chennai|madras"
    r"|kolkata|calcutta|bangalore|bengaluru|ahmedabad|pune)"
)

# NOTIFICATION_DATE_PATTERNS = [
#     # Most specific: "Mumbai, the 15th April, 2026"
#     re.compile(
#         _CITY_PAT + r",?\s+the\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})",
#         re.IGNORECASE
#     ),
#     # City without "the": "Mumbai, 15 April 2026"
#     re.compile(
#         _CITY_PAT + r",?\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})",
#         re.IGNORECASE
#     ),
#     # "dated the 15th April, 2026" or "dated 15th April, 2026"
#     re.compile(
#         r"dated\s+(?:the\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})",
#         re.IGNORECASE
#     ),
#     # Bare "the 15th April, 2026" anywhere in top section
#     re.compile(
#         r"\bthe\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})\b",
#         re.IGNORECASE
#     ),
#     # Broadest fallback: any "15th April, 2026" / "15 April 2026"
#     re.compile(
#         r"\b(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,}\s*,?\s*\d{4})\b"
#     ),
# ]

NOTIFICATION_DATE_PATTERNS = [

    # Mumbai, the 15th April, 2026
    re.compile(
        _CITY_PAT + r",?\s+the\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})",
        re.IGNORECASE
    ),

    # APRIL 15, 2026
    re.compile(
        r"\b([A-Z]+(?:\s+\d{1,2}),\s+\d{4})\b",
        re.IGNORECASE
    ),

    # 15 April 2026
    re.compile(
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s*,?\s*\d{4})\b",
        re.IGNORECASE
    ),
]

# Month names to reject false positives in the broadest fallback
_VALID_MONTHS = {
    "january","february","march","april","may","june",
    "july","august","september","october","november","december",
    "jan","feb","mar","apr","jun","jul","aug","sep","oct","nov","dec"
}


def extract_notification_date(text: str) -> str:
    """
    Extract the notification / publication date from the top portion
    of a SEBI regulation PDF.

    Scans the first 3000 characters (wider than before) to handle
    PDFs where unstructured merges the Gazette header into a single
    long string before the city+date line appears.

    Returns a clean human-readable string like "15th April, 2026" or "N/A".
    """
    # Wider window — merged-line PDFs can push the date past 1500 chars
    sample = text[:3000]

    # DEBUG: log the raw sample so we can see exactly what unstructured extracted
    logging.debug(f"extract_notification_date RAW SAMPLE:\n{sample!r}")
    # Temporarily also log at INFO level for diagnosis — remove after fix confirmed
    logging.info(f"[DATE DEBUG] First 3000 chars of PDF text:\n{sample[:1000]!r}")

    for i, pattern in enumerate(NOTIFICATION_DATE_PATTERNS):
        match = pattern.search(sample)
        if match:
            raw = match.group(1).strip().rstrip(",").strip()

            # For the broadest fallback (last pattern), validate month word
            if i == len(NOTIFICATION_DATE_PATTERNS) - 1:
                words = raw.lower().split()
                has_valid_month = any(w in _VALID_MONTHS for w in words)
                if not has_valid_month:
                    continue

            logging.info(f"extract_notification_date: matched pattern {i} -> {raw!r}")
            return raw

    logging.warning("extract_notification_date: no date found in first 3000 chars")
    return "N/A"


def gazette_force_present(text: str) -> bool:
    """Return True if the Gazette-force clause is found in the PDF."""
    return bool(GAZETTE_FORCE_PATTERN.search(text))


def determine_effective_date(text: str) -> str:
    """
    If the Gazette-force clause is present, effective date = notification date.
    Otherwise returns 'N/A'.
    """
    if gazette_force_present(text):
        return extract_notification_date(text)
    return "N/A"


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

# def extract_pdf_text(pdf_path: Path) -> str:
#     raw = partition_pdf(
#         filename=str(pdf_path),
#         strategy="fast",
#         include_page_breaks=False
#     )
#     text = "\n".join(str(el) for el in raw if el).strip()

#     if not text:
#         logging.info("Fallback to hi_res OCR")
#         raw = partition_pdf(filename=str(pdf_path), strategy="hi_res")
#         text = "\n".join(str(el) for el in raw if el).strip()

#     return text
def extract_pdf_text(pdf_path: Path) -> str:

    raw = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=False
    )

    text = "\n".join(
        str(el) for el in raw if el
    ).strip()

    if not text:

        logging.info("Fallback to hi_res OCR")

        raw = partition_pdf(
            filename=str(pdf_path),
            strategy="hi_res"
        )

        text = "\n".join(
            str(el) for el in raw if el
        ).strip()

    # ========================================================
    # KEEP ONLY ENGLISH NOTIFICATION SECTION
    # ========================================================

    upper_text = text.upper()

    english_start = upper_text.find(
        "SECURITIES AND EXCHANGE BOARD OF INDIA"
    )

    if english_start != -1:

        text = text[english_start:]

    return text

# ============================================================
# REGULATION CORE EXTRACTOR (same as main Parsing_agent)
# ============================================================

def extract_regulation_core(text: str) -> str:
    lines = text.splitlines()
    keep = []
    capture = False

    for line in lines:
        clean = line.strip()
        if not clean:
            continue

        if re.search(r'in exercise of the powers conferred', clean, re.IGNORECASE):
            capture = True
            continue

        if not capture:
            continue

        if re.search(
            r'(first|second|third|fourth|fifth|sixth|seventh|eighth)\s+amendment',
            clean, re.IGNORECASE
        ):
            continue

        if re.search(r'as amended upto|as amended up to', clean, re.IGNORECASE):
            continue

        if re.match(r'^\([a-z]+\)', clean):
            continue

        if len(clean) > 10:
            keep.append(clean)

        if len(keep) >= 4000:
            break

    return "\n".join(keep)


def is_amendment_regulation(text: str) -> bool:
    return bool(re.search(r'\bamendment\b', text, re.IGNORECASE))


# ============================================================
# FORMAT THE FINAL NEWSLETTER SUMMARY BLOCK
#
# Format:
#   <Title> dated (<issue_date_from_website>)
#   Effective date - <effective_date>
#   -----
#   <bullet summary>
# ============================================================

def build_newsletter_summary(
    title: str,
    issue_date: str,
    effective_date: str,
) -> str:
    """
    Build the two-line newsletter header for a regulation entry.

    Format:
        <Title> dated <issue_date>
        Effective date - <effective_date>

    issue_date     : date shown on the SEBI website (from Searching_agent_output.xlsx)
    effective_date : extracted from the PDF via Gazette clause, or "N/A"

    No LLM summary is included at this stage — only the metadata header.
    """
    # ── Line 1: title + website issue date ──────────────────
    if issue_date and str(issue_date).strip() not in ("", "nan", "NaT", "None"):
        # Format datetime objects nicely; keep plain strings as-is
        line1 = f"{title} dated {issue_date}"
    else:
        line1 = title

    # ── Line 2: effective date ───────────────────────────────
    if effective_date and effective_date != "N/A":
        line2 = f"Effective date - {effective_date}"
    else:
        line2 = "Effective date - N/A"

    return f"{line1}\n{line2}"


# ============================================================
# EXCEL UPDATE
# ============================================================

def update_excel(row: pd.Series):
    vertical = row["Verticals"]
    sub = row["SubCategory"]

    excel_path = MONTH_FOLDER / f"{vertical}_Newsletter.xlsx"
    CREATED_EXCELS.add(excel_path.name)

    if excel_path.exists():
        wb = load_workbook(excel_path)
    else:
        wb = Workbook()
        wb.remove(wb.active)

    sheet_name = sub if sub else "Regulations"
    if sheet_name not in wb.sheetnames:
        ws = wb.create_sheet(title=sheet_name)
        ws.append(list(row.index))
    else:
        ws = wb[sheet_name]

    ws.append([row.get(c, "NA") for c in row.index])
    wb.save(excel_path)
    wb.close()


# ============================================================
# PROCESS A SINGLE ROW
# ============================================================

def process_newsletter_row(row: pd.Series) -> pd.Series | None:
    """
    Main processing function for one Excel row.

    Logic:
    1. Only process rows where SubCategory == "regulations" (case-insensitive)
    2. Skip if Title contains "last amended on" / "amended as on"
    3. Extract PDF text
    4. Detect effective date via Gazette clause
    5. Build header-only entry (title + effective date — no LLM summary)
    """

    sub = row.get("SubCategory", "")
    if not isinstance(sub, str) or sub.strip().lower() != "regulations":
        logging.info(f"Skipping non-regulation row: SubCategory={sub!r}")
        return None

    title = row.get("Title", "")

    # ── STEP 1: Title check ──────────────────────────────────
    if is_amended_title(title):
        logging.info(f"Skipping amended-title row: {title!r}")
        return None

    pdf_path = Path(row["Path"])

    # ── STEP 2: Extract text ─────────────────────────────────
    try:
        text = extract_pdf_text(pdf_path)
    except Exception as e:
        logging.error(f"PDF extraction failed for {pdf_path}: {e}")
        row["Summary"] = "NA"
        row["EmbeddingText"] = "NA"
        row["EffectiveDate"] = "N/A"
        return row

    # ── STEP 3: Determine effective date from PDF ────────────
    # DEBUG: log raw extracted text head so we can tune patterns
    logging.info(f"--- RAW TEXT SAMPLE (first 3000 chars) ---\n{repr(text[:3000])}")
    effective_date = determine_effective_date(text)
    logging.info(f"Effective date for {pdf_path.name}: {effective_date!r}")

    # ── STEP 4: Get issue date from the Excel row ─────────────
    # Try common column names that the searching agent may use.
    issue_date = ""
    for col in ["Date", "IssueDate", "Published", "PublishedDate", "Issue Date"]:
        val = row.get(col, "")
        if val and str(val).strip() not in ("", "nan", "NaT", "None"):
            if isinstance(val, datetime):
                # e.g. "Apr 16, 2026"
                issue_date = val.strftime("%b %d, %Y")
            else:
                issue_date = str(val).strip()
            break

    # ── STEP 5: Build header-only newsletter entry ────────────
    # No LLM summary at this stage — just the two-line metadata header.
    final_summary = build_newsletter_summary(
        title=title,
        issue_date=issue_date,
        effective_date=effective_date,
    )

    row["Summary"] = final_summary
    row["EmbeddingText"] = text[:8000]   # kept for future embedding use
    row["EffectiveDate"] = effective_date

    return row


# ============================================================
# MAIN
# ============================================================

def main(excel_file: str):
    df = pd.read_excel(excel_file)

    required = ["Verticals", "SubCategory", "Path"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Add EffectiveDate column if missing
    if "EffectiveDate" not in df.columns:
        df["EffectiveDate"] = ""

    logging.info(f"Total rows in input: {len(df)}")

    # Only process SEBI "Listed Companies" or "listed companies" verticals
    # Adjust the filter if your vertical name differs
    sebi_mask = df["Verticals"].str.strip().str.lower().isin(
        {"listed companies", "sebi", "aif"}
    )
    df_sebi = df[sebi_mask].copy()
    logging.info(f"SEBI rows to consider: {len(df_sebi)}")

    start = time.time()
    processed_count = 0

    for idx, row in df_sebi.iterrows():
        logging.info(f"[{idx+1}] Processing: {row.get('Title', '')[:80]}")
        processed = process_newsletter_row(row)
        if processed is None:
            continue
        update_excel(processed)
        processed_count += 1

    logging.info(
        f"Newsletter parsing complete. "
        f"Processed {processed_count} regulations in {time.time() - start:.2f}s"
    )

    # ── MinIO Upload ──────────────────────────────────────────
    try:
        minio = MinIOClient()
        month_folder_name = MONTH_FOLDER.name
        minio_prefix = f"monthly_outputs/{month_folder_name}/"

        minio.delete_prefix(minio_prefix)

        for excel_name in CREATED_EXCELS:
            local_excel = MONTH_FOLDER / excel_name
            object_path = f"{minio_prefix}{excel_name}"
            minio.upload_file(
                local_path=str(local_excel),
                object_path=object_path
            )

        logging.info(
            f"Uploaded newsletter Excel files to MinIO -> "
            f"bucket={minio.bucket}, prefix={minio_prefix}"
        )

    except Exception as e:
        logging.error(f"MinIO upload failed: {e}")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    excel = DATA_DIR / "Searching_agent_output.xlsx"
    if not excel.exists():
        raise FileNotFoundError("Searching_agent_output.xlsx not found")

    main(str(excel))