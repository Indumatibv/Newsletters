#!/usr/bin/env python

# ============================================================
# REGULATION PARSING AGENT
# ============================================================
#
# PURPOSE:
#
# 1. Read Searching_agent_output.xlsx
# 2. Filter rows by configurable month
# 3. Process ONLY amendment regulation PDFs
# 4. Skip:
#       - Last amended on
#       - amended as on
# 5. Extract effective date from amendment PDF
# 6. Find corresponding consolidated regulation PDF
# 7. Send consolidated PDF path to Extract_Chunks_1.py.py
#
# ============================================================

import re
import logging
from pathlib import Path
from datetime import datetime
import json
import html as _html
import pandas as pd
import shutil
import html as _html

# ============================================================
# IMPORT FROM Extract_Chunks_1.py.py
# ============================================================

# from agents.SEBI_Regulations.Extract_Chunks_1 import process_regulation_pdf
# from agents.SEBI_Regulations.Subsection_Chunks_1b import create_subsection_chunks
# from agents.SEBI_Regulations.Extract_footnote_2 import (process_regulation_footnotes)
# from agents.SEBI_Regulations.Filtered_footnote_3 import (filter_footers_by_date)
# from agents.SEBI_Regulations.Mapping_chunk_footer_4 import (map_footers_to_exact_chapter_sections)
# from agents.SEBI_Regulations.Summary_all_5 import (process_all_footers)
# from agents.SEBI_Regulations.Combined_summary_6 import (generate_master_summary)
# from agents.SEBI_other_subdomains.SEBI_informal_guidance import (process_informal_guidance)
# from agents.SEBI_other_subdomains.SEBI_master_circular import (process_master_circular)
# from agents.SEBI_other_subdomains.SEBI_consultation_paper import (process_consultation_paper)
# from agents.SEBI_other_subdomains.SEBI_press_release import (process_press_release)
# from agents.SEBI_other_subdomains.SEBI_circulars import (process_circular)
# from agents.SEBI_other_subdomains.SEBI_NSE_BSE_circulars import (process_nse_bse_circular)
# from agents.SEBI_other_subdomains.ignore_from_titles import (should_ignore_title)

from SEBI_Regulations.Extract_Chunks_1 import process_regulation_pdf
from SEBI_Regulations.Subsection_Chunks_1b import create_subsection_chunks
from SEBI_Regulations.Extract_footnote_2 import (process_regulation_footnotes)
from SEBI_Regulations.Filtered_footnote_3 import (filter_footers_by_date)
from SEBI_Regulations.Mapping_chunk_footer_4 import (map_footers_to_exact_chapter_sections)
from SEBI_Regulations.Summary_all_5 import (process_all_footers)
from SEBI_Regulations.Combined_summary_6 import (generate_master_summary)
from SEBI_other_subdomains.SEBI_informal_guidance import (process_informal_guidance)
from SEBI_other_subdomains.SEBI_master_circular import (process_master_circular)
from SEBI_other_subdomains.SEBI_consultation_paper import (process_consultation_paper)
from SEBI_other_subdomains.SEBI_press_release import (process_press_release)
from SEBI_other_subdomains.SEBI_circulars import (process_circular)
from SEBI_other_subdomains.SEBI_NSE_BSE_circulars import (process_nse_bse_circular)
from SEBI_other_subdomains.ignore_from_titles import (should_ignore_title)
# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

EXCEL_PATH = DATA_DIR / "test.xlsx"

# ============================================================
# MONTH CONTROL
# ============================================================

# RUN_MONTH = None
RUN_MONTH = "2026-04"
# Examples:
#
# RUN_MONTH = None
# -> current month
#
# RUN_MONTH = "2026-01"
# -> January 2026
#
# RUN_MONTH = "2026-04"
# -> April 2026

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ============================================================
# TITLE DETECTION
# ============================================================

AMENDED_TITLE_PATTERN = re.compile(
    r'last\s+amended\s+on|amended\s+as\s+on',
    re.IGNORECASE
)

# ============================================================
# GAZETTE DETECTION
# ============================================================

GAZETTE_FORCE_PATTERN = re.compile(
    r'they\s+shall\s+come\s+into\s+force\s+on\s+the\s+date\s+of\s+their\s+publication\s+in\s+the\s+official\s+gazette',
    re.IGNORECASE
)

_CITY_PAT = (
    r"(?:mumbai|bombay|new\s+delhi|delhi|hyderabad|"
    r"chennai|madras|kolkata|calcutta|bangalore|"
    r"bengaluru|ahmedabad|pune)"
)

NOTIFICATION_DATE_PATTERNS = [

    re.compile(
        _CITY_PAT + r",?\s+the\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s*\d{4})",
        re.IGNORECASE
    ),

    re.compile(
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s*,?\s*\d{4})\b",
        re.IGNORECASE
    ),
]

# ============================================================
# HELPERS
# ============================================================

def get_month_date_range(run_month=None):

    today = datetime.today()

    if run_month is None:

        year = today.year
        month = today.month

    else:

        year, month = map(int, run_month.split("-"))

    start_date = datetime(year, month, 1)

    if month == 12:

        end_date = datetime(year + 1, 1, 1)

    else:

        end_date = datetime(year, month + 1, 1)

    return start_date, end_date


def parse_row_date(row):

    for col in [
        "Date",
        "IssueDate",
        "Published",
        "PublishedDate",
        "Issue Date"
    ]:

        val = row.get(col)

        if pd.notna(val):

            try:
                return pd.to_datetime(val)

            except Exception:
                pass

    return None


def is_amended_title(title: str) -> bool:

    if not isinstance(title, str):

        return False

    return bool(
        AMENDED_TITLE_PATTERN.search(title)
    )


def is_amendment_regulation(title: str) -> bool:

    if not isinstance(title, str):

        return False

    return bool(
        re.search(
            r'\(amendment\)',
            title,
            re.IGNORECASE
        )
    )


def normalize_regulation_title(title: str) -> str:

    if not isinstance(title, str):

        return ""

    title = re.sub(
        r'\[(last\s+amended\s+on|amended\s+as\s+on).*?\]',
        '',
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r'\(amendment\)',
        '',
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r'regulations[,]?\s*\d{4}',
        'regulations',
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r'\s+',
        ' ',
        title
    ).strip()

    return title.lower()


def find_last_amended_pdf(
    amendment_title: str,
    df: pd.DataFrame
):

    amendment_base = normalize_regulation_title(
        amendment_title
    )

    amended_rows = df[
        df["Title"].str.contains(
            r'last\s+amended\s+on|amended\s+as\s+on',
            case=False,
            na=False,
            regex=True
        )
    ]

    for _, row in amended_rows.iterrows():

        candidate_base = normalize_regulation_title(
            row["Title"]
        )

        if amendment_base == candidate_base:

            return row

    return None

# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pdf_text(pdf_path: Path):

    import pdfplumber

    full_text = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text()

            if text:

                full_text.append(text)

    return "\n".join(full_text)

# ============================================================
# EFFECTIVE DATE
# ============================================================

def extract_notification_date(text: str):

    sample = text[:3000]

    for pattern in NOTIFICATION_DATE_PATTERNS:

        match = pattern.search(sample)

        if match:

            return match.group(1).strip()

    return "N/A"


def determine_effective_date(text: str):

    if GAZETTE_FORCE_PATTERN.search(text):

        return extract_notification_date(text)

    return "N/A"

# ============================================================
# MAIN
# ============================================================

def main():

    if not EXCEL_PATH.exists():

        raise FileNotFoundError(
            f"Excel not found: {EXCEL_PATH}"
        )

    logging.info(
        f"Reading Excel: {EXCEL_PATH}"
    )

    df = pd.read_excel(EXCEL_PATH)


    # ========================================================
    # FRESH OUTPUT FOLDER FOR THIS RUN
    # ========================================================

    month_folder = (
        RUN_MONTH
        if RUN_MONTH
        else datetime.today().strftime("%Y-%m")
    )

    excel_output_dir = (
        BASE_DIR /
        "data" /
        "output_excels" /
        month_folder
    )

    if excel_output_dir.exists():

        shutil.rmtree(
            excel_output_dir
        )

    excel_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )
    # ========================================================
    # MONTH FILTER
    # ========================================================

    start_date, end_date = get_month_date_range(
        RUN_MONTH
    )

    logging.info(
        f"Filtering rows from "
        f"{start_date.date()} "
        f"to "
        f"{end_date.date()}"
    )

    filtered_rows = []

    for _, row in df.iterrows():

        row_date = parse_row_date(row)

        if row_date is None:

            continue

        if start_date <= row_date < end_date:

            filtered_rows.append(row)

    df = pd.DataFrame(filtered_rows)

    logging.info(
        f"Rows after month filter: {len(df)}"
    )

    # ========================================================
    # PROCESS
    # ========================================================

    results = []

    # for _, row in df.iterrows():

    #     title = row.get("Title", "")

    #     subcategory = str(
    #         row.get("SubCategory", "")
    #     ).strip().lower()

    for _, row in df.iterrows():

        title = row.get("Title", "")

        if should_ignore_title(title):

            logging.info(
                f"Ignoring title: {title}"
            )

            continue

        subcategory = str(
            row.get("SubCategory", "")
        ).strip().lower()
        # ====================================================
        # INFORMAL GUIDANCE
        # ====================================================

        if subcategory == "informal guidance":

            logging.info(
                f"Processing informal guidance: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            informal_output = (
                process_informal_guidance(
                    pdf_path=str(pdf_path)
                )
            )

            summary = informal_output["summary"]


            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(summary).replace("&", "and")

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # MASTER CIRCULAR
        # ====================================================

        if subcategory == "master circular":

            logging.info(
                f"Processing master circular: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            master_output = (
                process_master_circular(
                    pdf_path=str(pdf_path)
                )
            )

            summary = master_output["summary"]

            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(summary)

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # CONSULTATION PAPER
        # ====================================================

        if subcategory == "consultation paper":

            logging.info(
                f"Processing consultation paper: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            consultation_output = (
                process_consultation_paper(
                    pdf_path=str(pdf_path)
                )
            )

            summary = consultation_output[
                "summary"
            ]
         
            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(
                summary
            )

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # PRESS RELEASE
        # ====================================================

        if subcategory == "press release":

            logging.info(
                f"Processing press release: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            press_release_output = (
                process_press_release(
                    pdf_path=str(pdf_path)
                )
            )
            summary = press_release_output[
                "summary"
            ]
            
            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(
                summary
            )

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # CIRCULARS
        # ====================================================

        if subcategory == "circulars":

            logging.info(
                f"Processing circular: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            # circular_output = (
            #     process_circular(
            #         pdf_path=str(pdf_path)
            #     )
            # )
            circular_output = (
                process_circular(
                    pdf_path=str(pdf_path),
                    issue_date=str(
                        row.get("IssueDate", "")
                    ).strip()
                )
            )
            summary = circular_output[
                "summary"
            ]
            
            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(
                summary
            )

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # NSE / BSE CIRCULARS
        # ====================================================

        if subcategory in [
            "circular-nse",
            "circular-bse"
        ]:

            logging.info(
                f"Processing NSE/BSE circular: {title}"
            )

            pdf_path = Path(
                row["Path"]
            )

            if not pdf_path.exists():

                logging.warning(
                    f"Missing PDF: {pdf_path}"
                )

                continue

            # nse_bse_output = (
            #     process_nse_bse_circular(
            #         pdf_path=str(pdf_path)
            #     )
            # )
            nse_bse_output = (
                process_nse_bse_circular(
                    pdf_path=str(pdf_path),
                    issue_date=str(
                        row.get("IssueDate", "")
                    ).strip()
                )
            )

            summary = nse_bse_output["summary"]
            
            summary = _html.unescape(summary)
            # This safely maps any lingering raw brackets to your new hyphen standard
            summary = summary.replace("&gt;", "-").replace("->", "-").replace(" - ", " - ")
            # -------------------------------
            month_folder = (
                RUN_MONTH
                if RUN_MONTH
                else datetime.today().strftime("%Y-%m")
            )

            excel_output_dir = (
                BASE_DIR /
                "data" /
                "output_excels" /
                month_folder
            )

            excel_output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            vertical_name = str(
                row.get("Verticals", "Unknown")
            ).strip()

            safe_vertical_name = re.sub(
                r'[\\/*?:\\[\\]]',
                "_",
                vertical_name
            )

            excel_path = (
                excel_output_dir /
                f"{safe_vertical_name}.xlsx"
            )

            sheet_name = str(
                row.get("SubCategory", "General")
            ).strip()[:31]

            summary = _html.unescape(
                summary
            )

            final_excel_data = {

                "Verticals":
                    row.get("Verticals", ""),

                "SubCategory":
                    row.get("SubCategory", ""),

                "Year":
                    row.get("Year", ""),

                "Month":
                    row.get("Month", ""),

                "IssueDate":
                    str(row.get("IssueDate", "")),

                "Title":
                    row.get("Title", ""),

                "PDF_URL":
                    row.get("PDF_URL", ""),

                "File Name":
                    row.get("File Name", ""),

                "Path":
                    row.get("Path", ""),

                "Summary":
                    summary
            }

            new_row_df = pd.DataFrame(
                [final_excel_data]
            )

            if excel_path.exists():

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="overlay"
                ) as writer:

                    try:

                        existing_df = pd.read_excel(
                            excel_path,
                            sheet_name=sheet_name
                        )

                        startrow = len(existing_df) + 1
                        header = False

                    except Exception:

                        startrow = 0
                        header = True

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False,
                        header=header,
                        startrow=startrow
                    )

            else:

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    new_row_df.to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )

            logging.info(
                f"Updated Excel: {excel_path}"
            )

            continue

        # ====================================================
        # REGULATIONS
        # ====================================================

        if subcategory != "regulations":

            continue

        # ====================================================
        # SKIP CONSOLIDATED PDF
        # ====================================================

        if is_amended_title(title):

            logging.info(
                f"Skipping consolidated PDF: {title}"
            )

            continue

        # ====================================================
        # ONLY AMENDMENT REGULATIONS
        # ====================================================

        if not is_amendment_regulation(title):

            continue

        logging.info(
            f"Processing amendment regulation: {title}"
        )

        amendment_pdf_path = Path(
            row["Path"]
        )

        if not amendment_pdf_path.exists():

            logging.warning(
                f"Missing amendment PDF: "
                f"{amendment_pdf_path}"
            )

            continue

        # ====================================================
        # EFFECTIVE DATE
        # FROM AMENDMENT PDF
        # ====================================================

        amendment_text = extract_pdf_text(
            amendment_pdf_path
        )

        effective_date = determine_effective_date(
            amendment_text
        )

        logging.info(
            f"Effective date: {effective_date}"
        )

        # ====================================================
        # FIND MATCHING CONSOLIDATED PDF
        # ====================================================

        matched_row = find_last_amended_pdf(
            title,
            df
        )

        if matched_row is None:

            logging.warning(
                f"No consolidated PDF found for: "
                f"{title}"
            )

            continue

        consolidated_pdf_path = Path(
            matched_row["Path"]
        )

        if not consolidated_pdf_path.exists():

            logging.warning(
                f"Missing consolidated PDF: "
                f"{consolidated_pdf_path}"
            )

            continue

        logging.info(
            f"Matched consolidated PDF: "
            f"{matched_row['Title']}"
        )

        # ====================================================
        # SEND TO Extract_Chunks_1.py.py
        # ====================================================

        chunks = process_regulation_pdf(
            pdf_path=str(consolidated_pdf_path),
            title=matched_row["Title"]
        )
        subsection_chunks = create_subsection_chunks(chunks)
        # ========================================================
        # FOOTNOTE EXTRACTION
        # ========================================================

        footnotes = process_regulation_footnotes(
            pdf_path=str(consolidated_pdf_path)
        )

        # ========================================================
        # FILTER FOOTNOTES USING ISSUE DATE
        # ========================================================

        filtered_footnotes = filter_footers_by_date(

            footnotes=footnotes,

            issue_date=row.get("IssueDate")
        )

        # ========================================================
        # MAP FILTERED FOOTNOTES TO REGULATION CHUNKS
        # ========================================================

        # mapped_footnotes = (
        #     map_footers_to_exact_chapter_sections(

        #         filtered_footnotes=
        #             filtered_footnotes,

        #         regulation_chunks=
        #             chunks
        #     )
        # )
        mapped_footnotes = (
            map_footers_to_exact_chapter_sections(

                filtered_footnotes=
                    filtered_footnotes,

                regulation_chunks=
                    subsection_chunks
            )
        )
        # ========================================================
        # GENERATE COMPLIANCE SUMMARIES
        # ========================================================

        summarized_footnotes = process_all_footers(

            mapped_data=mapped_footnotes
        )

        # ========================================================
        # GENERATE COMBINED MASTER SUMMARY
        # ========================================================

        # combined_summary = generate_master_summary(
        #     mapped_data=summarized_footnotes
        # )

        # combined_summary = generate_master_summary(
        #     mapped_data=summarized_footnotes,
        #     effective_date=effective_date
        # )

        logging.info(
            f"Generated summaries for "
            f"{len(summarized_footnotes)} "
            f"footnotes"
        )

        logging.info(
            f"Mapped "
            f"{len(mapped_footnotes)} "
            f"footnotes to chunks"
        )

        logging.info(
            f"Filtered "
            f"{len(filtered_footnotes)} "
            f"footnotes for issue date"
        )

        logging.info(
            f"Extracted "
            f"{len(footnotes)} footnotes"
        )
      
        # ========================================================
        # SAFE OUTPUT FOLDER NAME
        # ========================================================


        month_folder = (
            RUN_MONTH
            if RUN_MONTH
            else datetime.today().strftime("%Y-%m")
        )


        output_dir = (
            BASE_DIR /
            "data" /
            "output" /
            month_folder
        )
        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ========================================================
        # SHARED METADATA
        # ========================================================

        metadata = {

            "Verticals":
                row.get("Verticals", ""),

            "SubCategory":
                row.get("SubCategory", ""),

            "Year":
                row.get("Year", ""),

            "Month":
                row.get("Month", ""),

            "IssueDate":
                str(row.get("IssueDate", "")),

            "Title":
                row.get("Title", ""),

            "PDF_URL":
                row.get("PDF_URL", ""),

            "File Name":
                row.get("File Name", ""),

            "Path":
                row.get("Path", ""),

            "effective_date":
                effective_date,

            "amendment_title":
                title,

            "consolidated_title":
                matched_row["Title"],

            "amendment_pdf":
                str(amendment_pdf_path),

            "consolidated_pdf":
                str(consolidated_pdf_path)
        }

        # ========================================================
        # GENERATE COMBINED MASTER SUMMARY
        # ========================================================

        combined_summary = generate_master_summary(
            mapped_data={
                **metadata,
                "mapped_footnotes": summarized_footnotes
            }
        )
        # ========================================================
        # CHUNKS JSON
        # ========================================================

        chunks_data = {

            **metadata,

            "total_chunks":
                len(chunks),

            "chunks":
                chunks
        }
        subsection_chunks_data = {
            **metadata,
            "total_chunks": len(subsection_chunks),
            "chunks": subsection_chunks
        }
        # ========================================================
        # FOOTNOTES JSON
        # ========================================================

        footnotes_data = {

            **metadata,

            "total_footnotes":
                len(filtered_footnotes),

            "footnotes":
                filtered_footnotes
        }

        # ========================================================
        # MAPPED FOOTNOTES JSON
        # ========================================================

        mapped_footnotes_data = {

            **metadata,

            "total_mapped_footnotes":
                len(summarized_footnotes),

            "mapped_footnotes":
                summarized_footnotes
        }


        # ========================================================
        # SAVE CHUNKS JSON
        # ========================================================

        chunks_path = output_dir / "chunks.json"

        with open(
            chunks_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                chunks_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logging.info(
            f"Saved chunks JSON: {chunks_path}"
        )

        # ========================================================
        # SAVE SUBSECTION CHUNKS JSON
        # ========================================================

        subsection_chunks_path = output_dir / "subsection_chunks.json"

        with open(
            subsection_chunks_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                subsection_chunks_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logging.info(
            f"Saved subsection chunks JSON: {subsection_chunks_path}"
        )

        # ========================================================
        # SAVE FOOTNOTES JSON
        # ========================================================

        footnotes_path = output_dir / "footnotes.json"

        with open(
            footnotes_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                footnotes_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logging.info(
            f"Saved footnotes JSON: {footnotes_path}"
        )

        # ========================================================
        # SAVE MAPPED FOOTNOTES JSON
        # ========================================================

        mapped_footnotes_path = (
            output_dir /
            "mapped_footnotes.json"
        )

        with open(
            mapped_footnotes_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                mapped_footnotes_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logging.info(
            f"Saved mapped footnotes JSON: "
            f"{mapped_footnotes_path}"
        )


        # ========================================================
        # OUTPUT EXCEL DIRECTORY
        # ========================================================


        folder_name = (
            RUN_MONTH
            if RUN_MONTH
            else datetime.today().strftime("%Y-%m")
        )

        excel_output_dir = (

            BASE_DIR /

            "data" /

            "output_excels" /

            folder_name
        )

        excel_output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ========================================================
        # EXCEL FILE NAME = VERTICAL
        # ========================================================

        vertical_name = str(
            row.get("Verticals", "Unknown")
        ).strip()

        safe_vertical_name = re.sub(
            r'[\\/*?:\\[\\]]',
            "_",
            vertical_name
        )

        excel_path = (
            excel_output_dir /
            f"{safe_vertical_name}.xlsx"
        )

        # ========================================================
        # SHEET NAME = SUBCATEGORY
        # ========================================================

        sheet_name = str(
            row.get("SubCategory", "General")
        ).strip()

        sheet_name = sheet_name[:31]

        # ========================================================
        # FINAL EXCEL ROW
        # ========================================================
        combined_summary = _html.unescape(combined_summary)
        final_excel_data = {

            **metadata,

            "mapped_footnotes":
                json.dumps(
                    summarized_footnotes,
                    ensure_ascii=False
                ),

            "combined_summary":
                combined_summary
        }

        new_row_df = pd.DataFrame(
            [final_excel_data]
        )

        # ========================================================
        # APPEND TO EXCEL
        # ========================================================

        if excel_path.exists():

            with pd.ExcelWriter(

                excel_path,

                engine="openpyxl",

                mode="a",

                if_sheet_exists="overlay"

            ) as writer:

                try:

                    existing_df = pd.read_excel(
                        excel_path,
                        sheet_name=sheet_name
                    )

                    startrow = len(existing_df) + 1

                    header = False

                except Exception:

                    startrow = 0

                    header = True

                new_row_df.to_excel(

                    writer,

                    sheet_name=sheet_name,

                    index=False,

                    header=header,

                    startrow=startrow
                )

        else:

            with pd.ExcelWriter(

                excel_path,

                engine="openpyxl"

            ) as writer:

                new_row_df.to_excel(

                    writer,

                    sheet_name=sheet_name,

                    index=False
                )

        logging.info(
            f"Updated Excel: {excel_path}"
        )

        results.append(metadata)


        logging.info(
            f"Generated "
            f"{len(chunks)} chunks"
        )

    logging.info(
        f"Completed processing "
        f"{len(results)} regulations"
    )

    return results

# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()