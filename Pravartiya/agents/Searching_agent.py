#!/usr/bin/env python
# agents/searching_agent.py
# =========================================================================
# CRITICAL FIX FOR WINDOWS - MUST BE AT THE VERY TOP OF THE SCRIPT
# =========================================================================
import sys
import asyncio
from matplotlib.pyplot import title
import nest_asyncio
import platform
import os
from pathlib import Path
# Apply Windows-specific event loop fix (must run before other asyncio use)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    nest_asyncio.apply()
# =========================================================================

import logging
from urllib.parse import urljoin, parse_qs, unquote, urlparse
from crawl4ai import AsyncWebCrawler
from bs4 import BeautifulSoup
import aiohttp
import base64
from datetime import datetime, timedelta
import pandas as pd
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import json
import tempfile
import unicodedata

import hashlib
import glob
import shutil
import requests
 
from selenium.common.exceptions import NoSuchWindowException, WebDriverException

try:
    import undetected_chromedriver as uc
    _UC_AVAILABLE = True
except ImportError:
    _UC_AVAILABLE = False
  
# ---------------------- Logging ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ---- GLOBAL TITLE TRACKING FOR BSE vs NSE DEDUP ----
BSE_TITLES_NORMALIZED = set()

#----mca-----
 

# ── Constants ──────────────────────────────────────────────
 
MCA_HOME_URL        = "https://www.mca.gov.in/"
MCA_DMS_BASE        = "https://www.mca.gov.in/bin/ebook/dms/getdocument"
MCA_DMS_PR_BASE     = "https://www.mca.gov.in/bin/dms/getdocument"   # Press Release endpoint
MCA_MAX_NAV_RETRIES = 5
MCA_MAX_DRV_RETRIES = 3   # retries when driver window dies on startup
MCA_DOMAIN_NAME     = "Companies Act"   # display name in Excel Verticals column
 
MCA_IGNORE_KEYWORDS = [
    "bid queries",
    "vacancy advertisement",
    "career notices",
    "corrigendum filling up post",
    "request for proposal",
]

#------------------------
def normalize_title_for_compare(title: str) -> str:
    """
    Normalize titles for cross-exchange comparison.
    - lowercase
    - remove extra spaces
    - strip punctuation
    """
    if not title:
        return ""

    title = unicodedata.normalize("NFKD", title)
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def safe_pdf_filename(title: str | None, pdf_url: str, max_base_len: int = 80) -> str:
    """
    Generates a filesystem-safe, collision-proof PDF filename.
    """
    if title:
        base = sanitize_filename(title).replace(".pdf", "")
    else:
        base = os.path.basename(urlparse(pdf_url).path).replace(".pdf", "")

    base = base[:max_base_len].rstrip("_")

    # stable short hash (URL-based)
    h = hashlib.sha1(pdf_url.encode("utf-8")).hexdigest()[:8]

    return f"{base}_{h}.pdf"

# -------- CONFIG --------

# Where PDFs should be stored (keep as-is: your Downloads path)
if platform.system() == "Windows":
    BASE_PATH = r"C:\Users\Admin\Desktop\Indu\Akshayam\Tejomaya_pdfs\Akshayam Data"
else:
    BASE_PATH = "/Users/admin/Downloads/Tejomaya_pdfs/Akshayam Data"

# Ensure base download folder exists
os.makedirs(BASE_PATH, exist_ok=True)

# Excel output goes into the repo data folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_OUTPUT = DATA_DIR / "Searching_agent_output.xlsx"

# -------- CLEAN PREVIOUS RUN OUTPUTS --------

def clean_previous_outputs():
    try:
        month_range_file = DATA_DIR / "month_range.json"
        excel_file = EXCEL_OUTPUT

        # Delete month_range.json
        if month_range_file.exists():
            month_range_file.unlink()
            logging.info("Deleted previous month_range.json")

        # Delete Searching_agent_output.xlsx
        if excel_file.exists():
            excel_file.unlink()
            logging.info("Deleted previous Searching_agent_output.xlsx")

    except Exception as e:
        logging.error("Error cleaning previous outputs: %s", e)


# Call this BEFORE anything starts
clean_previous_outputs()

# GLOBAL LIST FOR FINAL EXCEL
ALL_DOWNLOADED = []

# Excel file containing links
LINKS_EXCEL = DATA_DIR / "Links.xlsx"

# Only process these sheet names (categories)
PROCESS_SHEETS = ["SEBI", "Listed Companies", "IFSCA", "RBI", "IBBI", "ICAI", "Companies Act"]

# IBBI subdomains handled by IBBI v1 scraper
IBBI_1_SCRAPE = [
     "Notifications", "Circulars", "Regulations", "Acts", "Discussion Paper", "Guidelines" 
]

#---------------------------------------------------

def load_link_tasks_from_excel():
    tasks = []

    if not LINKS_EXCEL.exists():
        logging.error("Links Excel not found: %s", LINKS_EXCEL)
        return tasks

    xls = pd.ExcelFile(LINKS_EXCEL)

    for sheet in xls.sheet_names:
        if sheet not in PROCESS_SHEETS:
            logging.info("Skipping sheet (not in PROCESS_SHEETS): %s", sheet)
            continue

        df = pd.read_excel(LINKS_EXCEL, sheet_name=sheet)

        # Expect first column = SUBFOLDER
        # Second column = URL
        if df.shape[1] < 2:
            logging.warning("Invalid format in sheet: %s", sheet)
            continue

        subfolder_col = df.columns[0]
        link_col = df.columns[1]

        for _, row in df.iterrows():
            subfolder = str(row[subfolder_col]).strip()
            url = str(row[link_col]).strip()

            if not subfolder or not url or url.lower() == "nan":
                continue

            tasks.append({
                "category": sheet,    # sheet name = CATEGORY
                "subfolder": subfolder,
                "url": url
            })

    logging.info("Loaded %d link tasks from Excel", len(tasks))
    return tasks

def detect_aif_category(title: str) -> bool:
    aif_keywords = [
        "portfolio manager",
        "angel investor",
        "angel fund",
        "infrastructure investment trust",
        "invit",
        "real estate investment trust",
        "reit",
        "research analyst",
        "investment advisor",
        "alternative investment fund",
        "aif"
    ]

    title_lower = title.lower()
    return any(keyword in title_lower for keyword in aif_keywords)

def extract_detail_links_from_listing(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.select("a.points[href]"):
        detail_url = urljoin(base_url, a["href"])
        title = a.get_text(strip=True)
        links.append({"url": detail_url, "title": title})

    return links

def extract_sebi_pdf_from_iframe(iframe_src: str, page_url: str) -> str | None:
    if not iframe_src:
        return None

    iframe_src = urljoin(page_url, iframe_src)
    parsed = urlparse(iframe_src)
    qs = parse_qs(parsed.query)

    pdf = qs.get("file", [None])[0]
    if not pdf:
        return None

    return unquote(pdf)

def is_ignored_sebi_title(title: str) -> bool:
    """
    Returns True if SEBI title should be ignored based on business rules.
    - Most keywords: case-insensitive
    - KRAs / CRAs: case-sensitive (exact)
    """

    if not title:
        return False

    # # Case-insensitive keywords
    # ignore_keywords_ci = [
    #     "mutual fund",
    #     "mutual funds",
    #     "alternative investment fund",
    #     "alternative investment funds",
    #     "aif",
    #     "niveshak shivir",
    #     "inauguration",
    #     "survey",
    #     "municipal bond",
    #     "contest",
    #     "campaign",
    #     "annual report",
    #     "newspaper advertisement",
    # ]

    ignore_keywords_ci = [
        "mutual fund",
        "mutual funds",

        "alternative investment fund",
        "alternative investment funds",
        "aif",

        "kra",
        "kras",

        "invit",
        "infrastructure investment trust",

        "niveshak shivir",
        "inauguration",
        "survey",

        "municipal bond",
        "minicipal bond",

        "contest",
        "campaign",

        "annual report",
        "newspaper advertisement",

        "intermediaries",
        "research analyst",
        "stock broker",
        "stock brocker",

        "portfolio investor",
        "portfolio investors",

        "real estate investment trust",

        "collective investment scheme",
    ]

    title_lower = title.lower()

    for kw in ignore_keywords_ci:
        if kw in title_lower:
            return True

    # Case-sensitive checks for KRA/KRAs (DO NOT lowercase)
    if "KRAs" in title or "KRA" in title:
        return True

    # INVIT — case-insensitive
    if "invit" in title.lower() or "infrastructure investment trust" in title.lower():
        return True

    return False


#-------------------------------------------------------

# -------- MONTH RANGE LOGIC --------
def get_month_range(year: int = None, month: int = None):
    """
    Returns (month_start, month_end) for a given month.

    - If year and month are both provided, uses that specific month.
    - If neither is provided, defaults to the previous calendar month.

    Usage:
        get_month_range()            # previous month (default)
        get_month_range(2025, 3)     # March 2025
    """
    if year is not None and month is not None:
        # Use the explicitly specified month
        month_start = datetime(year, month, 1, 0, 0, 0, 0)
    else:
        # Default: previous calendar month
        today = datetime.today()
        first_of_current = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_of_prev = first_of_current - timedelta(days=1)
        month_start = last_of_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Last day of the target month: go to first of next month, subtract 1 day
    if month_start.month == 12:
        first_of_next = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        first_of_next = month_start.replace(month=month_start.month + 1, day=1)
    month_end = (first_of_next - timedelta(days=1)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    logging.info("Target range: %s -> %s", month_start.date(), month_end.date())
    return month_start, month_end


# ── Navigation ─────────────────────────────────────────────
 
def _on_target_page(driver, url: str) -> bool:
    keyword = url.rstrip("/").split("/")[-1].split(".")[0]  # e.g. "notifications"
    return keyword in driver.current_url
 

# -------- HELPERS --------

def is_last_amended_title(title: str) -> bool:
    """
    Ignore SEBI amendment-only titles.
    Handles NBSPs, spacing, and punctuation variations.
    """
    if not title:
        return False

    # normalize unicode + spaces
    t = unicodedata.normalize("NFKD", title).lower()
    t = re.sub(r"\s+", " ", t)  # collapse all whitespace

    return (
        "last amended on" in t
        or "amended as on" in t
    )

def sanitize_filename(title: str, max_length: int = 100) -> str:
    # 1) Normalize unicode -> removes emojis, accents, fancy characters
    normalized = unicodedata.normalize("NFKD", title)
    ascii_text = normalized.encode("ascii", "ignore").decode()

    # 2) Replace all non-alphanumeric characters with _
    ascii_text = re.sub(r'[^A-Za-z0-9]+', '_', ascii_text)

    # 3) Remove repeated underscores
    ascii_text = re.sub(r'_+', '_', ascii_text)

    # 4) Remove leading/trailing underscores
    ascii_text = ascii_text.strip('_')

    # 5) Truncate safely
    if len(ascii_text) > max_length:
        ascii_text = ascii_text[:max_length]

    # 6) Guarantee filename exists
    if not ascii_text:
        ascii_text = "document"

    return ascii_text + ".pdf"

#-----------------------------------------------------

def ensure_year_month_structure(base_folder: str, category: str, subfolder: str, year: str, month_full: str) -> str:
    subfolder_path = os.path.join(base_folder, category, subfolder)
    year_path = os.path.join(subfolder_path, year)
    os.makedirs(year_path, exist_ok=True)
    month_path = os.path.join(year_path, month_full)
    os.makedirs(month_path, exist_ok=True)
    return month_path


async def download_pdf(session: aiohttp.ClientSession, pdf_url: str, save_dir: str, title: str | None = None) -> str | None:
    try:
        parsed = urlparse(pdf_url)
        qs = parse_qs(parsed.query)

        filename = qs.get("fileName", [None])[0]
        if filename:
            # Sanitize URL-provided filenames too — they can be very long
            filename = sanitize_filename(filename.replace(".pdf", "")[:80])
        else:
            filename = safe_pdf_filename(title, pdf_url)

        file_path = os.path.join(save_dir, filename)

        if os.path.exists(file_path):
            logging.warning("Overwriting existing file: %s", file_path)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,application/octet-stream,*/*",
        }

        # ---- RBI REFERER FIX ----
        if "rbidocs.rbi.org.in" in parsed.netloc:
            headers["Referer"] = "https://www.rbi.org.in/"
        else:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}"

        async with session.get(pdf_url, headers=headers, timeout=60) as resp:
            if resp.status != 200:
                logging.warning("IFSCA download failed (%s): %s", resp.status, pdf_url)
                return None

            data = await resp.read()
            content_type = resp.headers.get("Content-Type", "").lower()

            # HARD VALIDATION
            if not (
                data[:4] == b"%PDF"
                or "pdf" in content_type
                or "octet-stream" in content_type
            ):
                logging.error(
                    "Not a valid PDF. Content-Type=%s URL=%s",
                    content_type,
                    pdf_url,
                )
                return None

            os.makedirs(os.path.dirname(file_path), exist_ok=True)  # ← HERE ✓
            with open(file_path, "wb") as f:
                f.write(data)

            logging.info("Valid PDF saved -> %s", file_path)
            return file_path

    except Exception as e:
        logging.warning("aiohttp failed, retrying with requests: %s | %s", pdf_url, e)

        try:
            resp = requests.get(pdf_url, headers=headers, timeout=60)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "").lower()

            if not (
                resp.content[:4] == b"%PDF"
                or "pdf" in content_type
                or "octet-stream" in content_type
            ):
                logging.error(
                    "Fallback not a valid PDF. Content-Type=%s URL=%s",
                    content_type,
                    pdf_url,
                )
                return None

            os.makedirs(os.path.dirname(file_path), exist_ok=True)  # IMPORTANT

            with open(file_path, "wb") as f:
                f.write(resp.content)

            logging.info("Fallback PDF saved -> %s", file_path)
            return file_path

        except Exception as e2:
            logging.error("Requests fallback failed: %s | %s", pdf_url, e2)
            return None
#-----------------------------------------------------

async def direct_nse_pdf_download(pdf_url: str, save_path: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://www.nseindia.com/"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(pdf_url, timeout=30) as r:
                if r.status == 200:
                    data = await r.read()
                    with open(save_path, "wb") as f:
                        f.write(data)
                    logging.info("Direct NSE PDF downloaded: %s", save_path)
                    return True
                else:
                    logging.error("NSE PDF failed (%s): %s", r.status, pdf_url)
                    return False
    except Exception as e:
        logging.error("NSE Direct download error: %s", e)
        return False

async def scrape_nse(task, week_start, week_end):
    logging.info("NSE LISTED COMPANIES SCRAPER -> %s", task["url"])

    # 1) Crawl page using Crawl4AI
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=task["url"])

    soup = BeautifulSoup(result.html, "html.parser")
    rows = soup.select("table tbody tr")
    logging.info("NSE rows detected: %d", len(rows))

    if not rows:
        logging.error("No rows found on NSE page")
        return

    # top_10 = rows[:10]
    # logging.info("Processing top 10 NSE circulars")

    # -------- LOOP --------
    # for row in top_10:
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        title = cols[0].get_text(strip=True)
        normalized_title = normalize_title_for_compare(title)

        if normalized_title in BSE_TITLES_NORMALIZED:
            logging.info(
                "Skipping NSE circular (already downloaded from BSE): %s",
                title
            )
            continue

        # Extract date
        text = cols[1].get_text(" ", strip=True)
        date_match = re.search(r"\d{2}/\d{2}/\d{4}", text)
        if not date_match:
            logging.warning("Bad date format: %s", text)
            continue

        dt = datetime.strptime(date_match.group(), "%d/%m/%Y")

        # Week filter
        if not (week_start <= dt <= week_end):
            logging.info("Skipping %s (outside week)", dt.date())
            continue

        # Extract PDF viewer URL
        a = cols[1].find("a", href=True)
        if not a:
            logging.warning("No link for %s", title)
            continue

        pdf_url = a["href"]
        if pdf_url.startswith("//"):
            pdf_url = "https:" + pdf_url

        logging.info("NSE PDF URL: %s", pdf_url)

        # -------- DIRECT DOWNLOAD (NO SELENIUM) --------
        year = str(dt.year)
        month_full = dt.strftime("%B")

        save_dir = ensure_year_month_structure(
            BASE_PATH, task["category"], task["subfolder"], year, month_full
        )

        # filename = sanitize_filename(title)
        filename = safe_pdf_filename(title, pdf_url)

        file_path = os.path.join(save_dir, filename)

        success = await direct_nse_pdf_download(pdf_url, file_path)

        if not success:
            logging.error("NSE direct PDF failed: %s", pdf_url)
            continue

        logging.info("NSE PDF Saved -> %s", file_path)

        # Record in final Excel
        ALL_DOWNLOADED.append({
            "Verticals": task["category"],
            "SubCategory": task["subfolder"],
            "Year": year,
            "Month": month_full,
            "IssueDate": dt.strftime("%Y-%m-%d"),
            "Title": title,
            "PDF_URL": pdf_url,
            "File Name": filename,
            "Path": file_path
        })

    logging.info("NSE LISTED COMPANIES -> DONE")

# BSE_DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
def get_latest_bse_pdf(download_dir, existing, wait_seconds=15) -> str | None:
# def get_latest_bse_pdf(existing, wait_seconds=15) -> str | None:
    end_time = time.time() + wait_seconds

    while time.time() < end_time:
        # current = set(glob.glob(os.path.join(run_download_dir, "*.pdf")))
        current = set(glob.glob(os.path.join(download_dir, "*.pdf")))
        new_files = current - existing

        for f in new_files:
            if not f.endswith(".crdownload"):
                return f

        time.sleep(1)

    return None

def bse_get_pdf_url_from_detail_page(detail_url: str, driver) -> str | None:
    """
    Navigate to BSE detail page, use CDP to intercept the PDF network
    request triggered by clicking button.btnbr.
    """
    listing_url = driver.current_url
    captured_pdf_url = []

    try:
        # Enable CDP Network and listen for requests
        driver.execute_cdp_cmd("Network.enable", {})

        # Set up a JS-side interceptor using fetch/XHR monkey-patch BEFORE page loads
        driver.get(detail_url)
        time.sleep(5)

        # Inject JS to intercept window.open calls
        driver.execute_script("""
            window._bse_pdf_url = null;
            const _orig_open = window.open;
            window.open = function(url, ...args) {
                window._bse_pdf_url = url;
                return _orig_open.apply(this, arguments);
            };
            // Also intercept fetch
            const _orig_fetch = window.fetch;
            window.fetch = function(url, ...args) {
                if (typeof url === 'string' && url.toLowerCase().includes('pdf')) {
                    window._bse_pdf_url = url;
                }
                return _orig_fetch.apply(this, arguments);
            };
        """)

        try:
            pdf_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btnbr"))
            )
        except Exception:
            logging.warning("BSE detail: button.btnbr not found: %s", detail_url)
            return None

        existing_handles = set(driver.window_handles)

        # Click
        driver.execute_script("arguments[0].click();", pdf_button)
        time.sleep(4)

        # --- Strategy 1: check our window.open interceptor ---
        intercepted = driver.execute_script("return window._bse_pdf_url;")
        if intercepted:
            logging.info("BSE detail: intercepted window.open URL: %s", intercepted)
            if not intercepted.startswith("http"):
                intercepted = urljoin("https://www.bseindia.com", intercepted)
            return intercepted

        # --- Strategy 2: new tab opened ---
        new_handles = set(driver.window_handles) - existing_handles
        if new_handles:
            pdf_tab = new_handles.pop()
            driver.switch_to.window(pdf_tab)
            time.sleep(2)
            tab_url = driver.current_url
            logging.info("BSE detail: new tab URL: %s", tab_url)
            driver.close()
            driver.switch_to.window(list(existing_handles)[0])
            if tab_url and tab_url not in ("about:blank", detail_url):
                return tab_url

        # --- Strategy 3: check CDP network log for PDF requests ---
        try:
            logs = driver.execute_script("""
                return window.performance.getEntriesByType('resource')
                    .map(e => e.name);
            """)
            logging.info("BSE detail: all resource URLs: %s", logs[:10])
            for u in logs:
                if any(x in u.lower() for x in [".pdf", "getfile", "download", "circular"]):
                    logging.info("BSE detail: PDF from resource: %s", u)
                    return u
        except Exception as e:
            logging.warning("BSE: resource log failed: %s", e)

        # --- Strategy 4: check page source for any downloadable link ---
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for tag in soup.select("embed, iframe, object"):
            src = tag.get("src", "") or tag.get("data", "")
            if src:
                return urljoin("https://www.bseindia.com", src)

        logging.warning("BSE detail: all strategies failed: %s", detail_url)
        return None

    except Exception as e:
        logging.warning("BSE detail page extraction failed: %s | %s", detail_url, e)
        return None

    finally:
        try:
            driver.execute_cdp_cmd("Network.disable", {})
        except Exception:
            pass
        try:
            if driver.current_url != listing_url:
                driver.get(listing_url)
                time.sleep(5)
        except Exception:
            pass

async def scrape_bse(task, week_start, week_end):
    logging.info("BSE SCRAPER (Angular) -> %s", task["url"])
    run_download_dir = tempfile.mkdtemp(prefix="bse_dl_")

    MAX_RETRIES = 3
    driver = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info("BSE: driver attempt %d/%d", attempt, MAX_RETRIES)

            if _UC_AVAILABLE:
                opts = uc.ChromeOptions()
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                # driver = uc.Chrome(options=opts, version_main=147)
                prefs = {
                    "download.default_directory": run_download_dir,
                    "download.prompt_for_download": False,
                    "plugins.always_open_pdf_externally": True,
                    "download.directory_upgrade": True,
                }

                opts.add_experimental_option("prefs", prefs)

                driver = uc.Chrome(options=opts, version_main=148)
            # else:
            #     opts = webdriver.ChromeOptions()
            #     opts.add_argument("--no-sandbox")
            #     opts.add_argument("--disable-dev-shm-usage")
            #     opts.add_argument("--disable-blink-features=AutomationControlled")
            #     opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            #     opts.add_experimental_option("useAutomationExtension", False)
            #     driver = webdriver.Chrome(options=opts)
            else:
                opts = webdriver.ChromeOptions()
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_experimental_option("excludeSwitches", ["enable-automation"])
                opts.add_experimental_option("useAutomationExtension", False)

                prefs = {
                    "download.default_directory": run_download_dir,
                    "download.prompt_for_download": False,
                    "plugins.always_open_pdf_externally": True,
                    "download.directory_upgrade": True,
                }

                opts.add_experimental_option("prefs", prefs)

                driver = webdriver.Chrome(options=opts)

            time.sleep(2)  # let uc stabilise before touching the window

            driver.get(task["url"])
            logging.info("BSE: page loaded, waiting for Angular table...")

            time.sleep(5)  # let Angular fully render
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(2)

            selectors = [
                "table tr td.tdcolumn",
                "table tr td",
                "tr td a[href*='bseindia.com/downloads']",
                "tbody tr",
            ]

            found = False
            for sel in selectors:
                try:
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    logging.info("BSE: table found with selector: %s", sel)
                    found = True
                    break
                except Exception:
                    logging.warning("BSE: selector not found: %s", sel)
                    continue

            if not found:
                logging.warning("BSE: no selector matched — waiting 15s and trying anyway")
                time.sleep(15)

            page_src = driver.page_source
            logging.info("BSE: page source length: %d", len(page_src))

            if "tdcolumn" in page_src:
                logging.info("BSE: 'tdcolumn' found in page source — Angular rendered OK")
            elif "Circulars" in page_src:
                logging.info("BSE: 'Circulars' found but tdcolumn missing — partial render")
            else:
                logging.error("BSE: page source seems wrong — possible block or redirect")
                logging.info("BSE page snippet: %s", page_src[:2000])
                return

            soup = BeautifulSoup(page_src, "html.parser")
            rows = soup.select("table tr")
            logging.info("BSE: total rows found: %d", len(rows))

            async with aiohttp.ClientSession() as session:
                for row in rows:
                    cols = row.find_all("td", class_="tdcolumn")
                    if len(cols) < 2:
                        continue

                    a = cols[0].find("a", href=True)
                    if not a:
                        continue

                    # title = a.get_text(strip=True)
                    # pdf_url = a["href"]
                    title = a.get_text(strip=True)
                    pdf_url = a["href"]

                    if pdf_url.startswith("/"):
                        pdf_url = urljoin("https://www.bseindia.com", pdf_url)

                    actual_pdf_url = pdf_url

                    is_detail_page = (
                        "DispNewNoticesCirculars?page=" in pdf_url
                        or not pdf_url.lower().endswith(".pdf")
                    )
                    date_text = cols[1].get_text(strip=True)
                    try:
                        dt = datetime.strptime(date_text.strip(), "%B %d, %Y")
                    except Exception:
                        logging.warning("BSE bad date: %s", date_text)
                        continue

                    if not (week_start <= dt <= week_end):
                        logging.info("BSE skipping outside week: %s | %s", dt.date(), title[:60])
                        continue
                    if is_detail_page:
                        logging.info("BSE detail page detected: %s", pdf_url)

                        existing_downloads = set(
                            glob.glob(os.path.join(run_download_dir, "*.pdf"))
                        )

                        actual_pdf_url = bse_get_pdf_url_from_detail_page(
                            pdf_url,
                            driver
                        )

                        logging.info(
                            "BSE detail: resolved URL = %r",
                            actual_pdf_url
                        )

                        if not actual_pdf_url:
                            logging.warning(
                                "BSE: could not extract PDF from detail page: %s",
                                pdf_url
                            )
                            continue
                    normalized_title = normalize_title_for_compare(title)
                    if normalized_title in BSE_TITLES_NORMALIZED:
                        logging.info("BSE duplicate skipped: %s", title)
                        continue

                    year = str(dt.year)
                    month_full = dt.strftime("%B")

                    save_dir = ensure_year_month_structure(
                        BASE_PATH,
                        task["category"],
                        task["subfolder"],
                        year,
                        month_full
                    )

                    # downloaded_path = await download_pdf(
                    #     session, pdf_url, save_dir, title
                    # )
                    if is_detail_page:

                        # latest_pdf = get_latest_bse_pdf(
                        #     existing_downloads,
                        #     wait_seconds=15
                        # )

                        # if not latest_pdf:
                        #     logging.error(
                        #         "BSE: browser download not found for: %s",
                        #         title
                        #     )
                        #     continue

                        # filename = safe_pdf_filename(
                        #     title,
                        #     actual_pdf_url
                        # )

                        # final_path = os.path.join(save_dir, filename)

                        # shutil.move(latest_pdf, final_path)

                        # downloaded_path = final_path

                        # latest_pdf = get_latest_bse_pdf(
                        #     existing_downloads,
                        #     wait_seconds=15
                        # )
                        latest_pdf = get_latest_bse_pdf(
                            run_download_dir,
                            existing_downloads,
                            wait_seconds=15
                        )
                        if not latest_pdf:
                            logging.error(
                                "BSE: browser download not found for: %s",
                                title
                            )
                            continue

                        downloaded_filename = os.path.basename(latest_pdf)

                        filename = safe_pdf_filename(
                            title,
                            actual_pdf_url
                        )

                        final_path = os.path.join(save_dir, filename)

                        shutil.move(latest_pdf, final_path)
                        downloaded_filename = os.path.basename(latest_pdf)

                        # if (
                        #     not actual_pdf_url
                        #     or "DispNewNoticesCirculars" in actual_pdf_url
                        #     or not actual_pdf_url.lower().endswith(".pdf")
                        # ):
                        #     actual_pdf_url = (
                        #         "https://www.bseindia.com/downloads/UploadDocs/Notices/"
                        #         + downloaded_filename
                        #     )

                        if (
                            not actual_pdf_url
                            or "DispNewNoticesCirculars" in actual_pdf_url
                            or not actual_pdf_url.lower().endswith(".pdf")
                        ):
                            actual_pdf_url = pdf_url
                        
                        downloaded_path = final_path
                        logging.info(
                            "BSE: moved browser download -> %s",
                            final_path
                        )

                    else:

                        downloaded_path = await download_pdf(
                            session,
                            actual_pdf_url,
                            save_dir,
                            title
                        )
                    if not downloaded_path:
                        logging.error("BSE PDF failed: %s", pdf_url)
                        continue

                    filename = os.path.basename(downloaded_path)

                    ALL_DOWNLOADED.append({
                        "Verticals": task["category"],
                        "SubCategory": task["subfolder"],
                        "Year": year,
                        "Month": month_full,
                        "IssueDate": dt.strftime("%Y-%m-%d"),
                        "Title": title,
                        # "PDF_URL": pdf_url,
                        "PDF_URL": actual_pdf_url,
                        "File Name": filename,
                        "Path": os.path.abspath(downloaded_path)
                    })

                    BSE_TITLES_NORMALIZED.add(normalized_title)
                    logging.info("BSE downloaded: %s", filename)

            # success — break out of retry loop
            break

        except (NoSuchWindowException, WebDriverException) as exc:
            logging.warning("BSE: driver window lost on attempt %d/%d (%s). Retrying...",
                            attempt, MAX_RETRIES, exc)
            time.sleep(3)

        except Exception as e:
            logging.exception("BSE scraper error: %s", e)
            break  # non-driver errors shouldn't retry

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
            try:
                shutil.rmtree(run_download_dir, ignore_errors=True)
            except Exception:
                pass
    logging.info("BSE SCRAPER -> DONE")

async def scrape_sebi_informal_guidance(task, week_start, week_end):
    logging.info("SEBI INFORMAL GUIDANCE SCRAPER -> %s", task["url"])

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=task["url"])
    
    soup = BeautifulSoup(result.html, "html.parser")
    # 1. Get all rows from the listing table
    rows = soup.find_all("tr", class_=["odd", "even"])

    async with aiohttp.ClientSession() as session:
        for row in rows:
            # Extract Date from the first <td>
            date_td = row.find("td")
            if not date_td: continue
            
            date_text = date_td.get_text(strip=True)
            try:
                dt = datetime.strptime(date_text, "%b %d, %Y")
            except ValueError: continue

            # --- WEEK RANGE FILTER ---
            if dt < week_start: break  # SEBI is usually chronological
            if dt > week_end: continue

            # 2. Get Title and Detail Page Link
            link_tag = row.select_one("a.points")
            if not link_tag: continue
            
            detail_url = urljoin("https://www.sebi.gov.in", link_tag["href"])
            title = link_tag.get("title") or link_tag.get_text(strip=True)
            title = unicodedata.normalize("NFKD", title)

            # --- IGNORE LOGIC ---
            if is_ignored_sebi_title(title):
                logging.info("Skipping (Ignored Keyword): %s", title)
                continue

            # 3. OPEN DETAIL PAGE to find the actual PDF
            try:
                async with session.get(detail_url, timeout=30) as resp:
                    if resp.status != 200: continue
                    detail_html = await resp.text()
                
                detail_soup = BeautifulSoup(detail_html, "html.parser")
                
                # Look for the specific link text you mentioned
                pdf_link_tag = detail_soup.find("a", string=re.compile("Informal Guidance Letter by SEBI", re.I))
                
                if pdf_link_tag and pdf_link_tag.get("href"):
                    pdf_url = urljoin(detail_url, pdf_link_tag["href"])
                else:
                    # Fallback to your existing iframe helper if the specific text isn't found
                    iframe = detail_soup.select_one("iframe")
                    pdf_url = extract_sebi_pdf_from_iframe(iframe.get("src"), detail_url) if iframe else None

                if not pdf_url:
                    logging.warning("No PDF link found for: %s", title)
                    continue

                # 4. DOWNLOAD AND RECORD
                year, month_full = str(dt.year), dt.strftime("%B")
                save_dir = ensure_year_month_structure(BASE_PATH, task["category"], task["subfolder"], year, month_full)
                
                downloaded_path = await download_pdf(session, pdf_url, save_dir, title)

                if downloaded_path:
                    ALL_DOWNLOADED.append({
                        "Verticals": task["category"],
                        "SubCategory": task["subfolder"],
                        "Year": year,
                        "Month": month_full,
                        "IssueDate": dt.strftime("%Y-%m-%d"),
                        "Title": title,
                        "PDF_URL": pdf_url,
                        "File Name": os.path.basename(downloaded_path),
                        "Path": os.path.abspath(downloaded_path)
                    })
            except Exception as e:
                logging.error("Error processing %s: %s", detail_url, e)

async def scrape_sebi(task, week_start, week_end):
    category = task["category"]
    subfolder = task["subfolder"]
    detail_url = task["url"]

    logging.info("SEBI Scraper -> [%s > %s]: %s", category, subfolder, detail_url)

    # ---- Crawl page ----
    async with AsyncWebCrawler() as crawler:
        try:
            detail_result = await crawler.arun(url=detail_url)
        except Exception as e:
            logging.exception("Crawler failed for %s : %s", detail_url, e)
            return

    soup_detail = BeautifulSoup(detail_result.html, "html.parser")

    # ---- Extract title ----
    if "title" not in task:
        title_elem = soup_detail.select_one("h1, h2, h3")
        if title_elem:
            task["title"] = title_elem.get_text(strip=True)
        else:
            logging.warning("No title found at %s", detail_url)
            task["title"] = "Untitled"
    
    # ---- SKIP non-relevant SEBI PDFs based on title ----
    if category == "SEBI" and is_ignored_sebi_title(task["title"]):
        logging.info(
            "Skipping SEBI document based on ignore list: %s",
            task["title"]
        )
        return

    # ---- Detect nested listing pages ----
    # if "doListing=yes" in detail_url:
    if "doListing" in detail_url:

        detail_links = extract_detail_links_from_listing(detail_result.html, detail_url)

        if not detail_links:
            logging.warning("No detail links inside listing: %s", detail_url)
            return

        logging.info("Found %d SEBI inner links in listing: %s", len(detail_links), detail_url)

        for item in detail_links:
            await scrape_sebi(
                {
                    "category": category,
                    "subfolder": subfolder,
                    "url": item["url"],
                    "title": item["title"]
                },
                week_start,
                week_end
            )

        return

    # ---- Extract date ----
    date_elem = soup_detail.select_one("h5")
    if not date_elem:
        logging.warning("No date found at %s", detail_url)
        return

    try:
        dt = datetime.strptime(date_elem.get_text(strip=True), "%b %d, %Y")
    except Exception:
        logging.warning("Invalid date format for %s", detail_url)
        return

    # ---- Week range filter ----
    if not (week_start <= dt <= week_end):
        logging.info("Skipping (out of weekly range): %s", dt.date())
        return

    year = str(dt.year)
    month_full = dt.strftime("%B")

    # ---- Category stays as SEBI ----
    category = category

    # ---- Folder Structure ----
    save_path = ensure_year_month_structure(
        BASE_PATH, category, subfolder, year, month_full
    )

    # ---- Detect PDF ----

    pdf_url = None

    iframe = soup_detail.select_one("iframe")
    if iframe:
        pdf_url = extract_sebi_pdf_from_iframe(
            iframe.get("src"),
            detail_url
        )

    # fallback: download button
    if not pdf_url:
        pdf_btn = soup_detail.select_one("button#download")
        if pdf_btn:
            pdf_url = detail_url.replace(".html", ".pdf")


    file_path = None

    # ---- Try direct PDF download ----
    if pdf_url:
        async with aiohttp.ClientSession() as session:
            # file_path = await download_pdf(session, pdf_url, save_path)
            file_path = await download_pdf(
                session,
                pdf_url,
                save_path,
                title=task["title"]
            )

    # ---- Fallback -> printToPDF ----
    if not file_path:
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            driver = webdriver.Chrome(options=options)

            driver.get(detail_url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
            )

            pdf_data = base64.b64decode(
                driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})["data"]
            )

            # filename = sanitize_filename(task["title"])
            filename = safe_pdf_filename(task["title"], detail_url)
            file_path = os.path.join(save_path, filename)

            with open(file_path, "wb") as f:
                f.write(pdf_data)

        except Exception:
            logging.exception("PrintToPDF fallback failed: %s", detail_url)
            file_path = None

        finally:
            try:
                driver.quit()
            except:
                pass

    # ---- Finally append to results ----
    if file_path:
        ALL_DOWNLOADED.append({
            "Verticals": category,
            "SubCategory": subfolder,
            "Year": year,
            "Month": month_full,
            "IssueDate": dt.strftime("%Y-%m-%d"),
            "Title": task["title"],
            "PDF_URL": pdf_url if pdf_url else "PrintToPDF",
            "File Name": os.path.basename(file_path),
            "Path": os.path.abspath(file_path)
        })

#-----------------------------------------------------

async def scrape_generic_link(task, week_start, week_end):
    category = task["category"]
    subfolder = task["subfolder"]
    url = task["url"]

    logging.info("Processing [%s > %s] => %s", category, subfolder, url)

    # SEBI website (current logic)

    if category == "SEBI":
        # Check if this specific link is for Informal Guidance
        if "Informal Guidance" in subfolder:
            return await scrape_sebi_informal_guidance(task, week_start, week_end)
        else:
            # Fallback to your existing SEBI scraper for other subfolders
            return await scrape_sebi(task, week_start, week_end)

    # if category == "SEBI":
    #     return await scrape_sebi(task, week_start, week_end)

    # if category == "IFSCA":

    #     # SPECIAL CASE: Public Consultation
    #     if is_ifsca_public_consultation(task["url"]):
    #         return await scrape_ifsca_public_consultation(task, week_start, week_end)

    #     # DEFAULT: Notifications / Circulars / Others
    #     return await scrape_ifsca(task, week_start, week_end)

    # LISTED COMPANIES (NSE/BSE logic)
    if category == "Listed Companies":
        
        # NSE
        if "nse" in subfolder.lower():
            return await scrape_nse(task, week_start, week_end)

        # BSE
        if "bse" in subfolder.lower():
            return await scrape_bse(task, week_start, week_end)

        logging.warning("No scraper defined for subfolder: %s", subfolder)
        return

    # if category == "IBBI":

    #     if subfolder in IBBI_1_SCRAPE:
    #         return await scrape_ibbi_1(task, week_start, week_end)

    #     logging.warning("No IBBI scraper mapped for subfolder: %s", subfolder)
    #     return

    # if category == "RBI":
    #     return await scrape_rbi(task, week_start, week_end)

    # if category == "ICAI":
    #     return await scrape_icai(task, week_start, week_end)
    
    # if category == "Companies Act":
    #     return await scrape_mca(task, week_start, week_end)
    
    logging.warning("Unknown category: %s", category)

#---------------------------------------------------------------------

async def main():
    # ── MONTH CONTROL ──────────────────────────────────────────────────
    # Set TARGET_YEAR and TARGET_MONTH to run for a specific month.
    # Leave both as None to automatically use the previous calendar month.
    #
    # Examples:
    #   TARGET_YEAR, TARGET_MONTH = None, None   ← previous month (default)
    #   TARGET_YEAR, TARGET_MONTH = 2025, 3      ← March 2025
    #   TARGET_YEAR, TARGET_MONTH = 2024, 12     ← December 2024
    # ──────────────────────────────────────────────────────────────────
    # TARGET_YEAR  = None
    # TARGET_MONTH = None

    TARGET_YEAR  = 2026
    TARGET_MONTH = 2
    month_start, month_end = get_month_range(TARGET_YEAR, TARGET_MONTH)

    tasks = load_link_tasks_from_excel()
    if not tasks:
        logging.info("No tasks found in Excel.")
        return

    for task in tasks:
        await scrape_generic_link(task, month_start, month_end)

    if ALL_DOWNLOADED:
        df = pd.DataFrame(ALL_DOWNLOADED)
        df.to_excel(EXCEL_OUTPUT, index=False)
        # Write month range for parsing agent
        month_info = {
            "month_start": month_start.strftime("%Y-%m-%d"),
            "month_end": month_end.strftime("%Y-%m-%d")
        }

        with open(DATA_DIR / "month_range.json", "w") as f:
            json.dump(month_info, f)

        logging.info("FINAL EXCEL GENERATED: %s", EXCEL_OUTPUT)
    else:
        logging.info("No PDFs downloaded for the previous month.")

#-------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    except Exception:
        logging.exception("Fatal error in searching_agent")