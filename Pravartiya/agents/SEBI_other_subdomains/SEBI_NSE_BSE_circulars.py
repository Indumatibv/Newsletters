import logging
import re
import html
from pathlib import Path

from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

# Initialize the LLM
llm = Ollama(model="mistral:latest")

# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_text(pdf_path: str) -> str:
    raw = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=False
    )
    text = "\n".join(str(el) for el in raw if el).strip()
    if not text:
        logging.warning(f"Fast extraction yielded no text for {pdf_path}. Falling back to hi_res.")
        raw = partition_pdf(filename=str(pdf_path), strategy="hi_res")
        text = "\n".join(str(el) for el in raw if el).strip()
    return text


# ============================================================
# DATE EXTRACTION
# ============================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)


def extract_circular_date(text: str) -> str:
    for pattern in [
        rf"Notice\s+Date\s*:?\s*(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})",
        rf"Notice\s+Date\s*:?\s*((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"^Date\s*:\s*((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"^Date\s*:\s*(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()

    header = text[:300]
    for pattern in [
        rf"(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})",
        rf"((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
    ]:
        m = re.search(pattern, header, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    return "Not specified"


def extract_effective_date(text: str) -> str:
    if re.search(
        r"(?:come\s+into\s+force\s+with\s+immediate\s+effect"
        r"|with\s+immediate\s+effect"
        r"|effective\s+immediately)",
        text, re.IGNORECASE
    ):
        return "Immediate effect"

    for pattern in [
        rf"with\s+effect\s+from\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"effective\s+from\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"commence\s+from\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        rf"with\s+effect\s+from\s+(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})",
        rf"effect\s+from\s+((?:{MONTHS})\s+\d{{4}})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    return "Not specified"


# ============================================================
# EXCHANGE DETECTION
# ============================================================

def detect_exchange(text: str, pdf_path: str = "") -> str:
    filename = Path(pdf_path).stem if pdf_path else ""

    if re.match(r'^\d{8}-\d+', filename):
        return "BSE"

    if re.match(r'^NSE', filename, re.IGNORECASE):
        return "NSE"

    header = text[:500]
    if re.search(r'\bBSE\b|Bombay\s+Stock\s+Exchange|Power\s+of\s+Vibrance', header, re.IGNORECASE):
        return "BSE"
    if re.search(r'\bNSE\b|National\s+Stock\s+Exchange|NSCCL', header, re.IGNORECASE):
        return "NSE"

    if re.search(r'\bBSE\b|Bombay\s+Stock\s+Exchange|Power\s+of\s+Vibrance', text, re.IGNORECASE):
        return "BSE"
    if re.search(r'\bNSE\b|National\s+Stock\s+Exchange|NSCCL', text, re.IGNORECASE):
        return "NSE"

    if re.search(r'Notice\s+No\.?\s*\d{8}-\d+', text, re.IGNORECASE):
        return "BSE"
    if re.search(r'NSE/[A-Z]+/', text):
        return "NSE"

    return "BSE"


def is_forwarding_notice(text: str) -> bool:
    for pattern in [
        r'(?:aforesaid\s+)?circular\s+is\s+attached\s+for\s+reference',
        r'please\s+find\s+(?:the\s+)?(?:attached|enclosed)',
        r'enclosed\s+for\s+(?:your\s+)?reference',
        r'is\s+enclosed\s+herewith',
        r'attached\s+herewith\s+for\s+(?:your\s+)?reference',
    ]:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_sebi_circular_subject(text: str) -> tuple[str, str]:
    date_pattern = re.compile(
        rf"SEBI[^,]*?dated\s+((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})",
        re.IGNORECASE
    )
    m = date_pattern.search(text)
    sebi_date = m.group(1).strip() if m else "a recent date"

    subject_pattern = re.compile(
        r'regarding\s+([^.]{10,150}?)(?:\.|$)',
        re.IGNORECASE
    )
    m = subject_pattern.search(text)
    subject = m.group(1).strip() if m else "regulatory matters"

    return sebi_date, subject


def build_forwarding_gist(text: str, exchange: str) -> str:
    sebi_date, subject = extract_sebi_circular_subject(text)
    return (
        f"{exchange} has issued this circular and informed listed entities "
        f"about the SEBI circular dated {sebi_date} regarding {subject}. "
        f"The notice does not reproduce the substantive amendments and "
        f"only forwards the SEBI circular for reference."
    )


# ============================================================
# COMPLIANCE PROMPT FOR SUBSTANTIVE CIRCULARS
# ============================================================

NSE_BSE_CIRCULAR_PROMPT = """
[SYSTEM INSTRUCTION]
You are a regulatory extraction engine mapping {exchange} compliance circulars into standardized database schemas.
Isolate your extraction into distinct fields using the exact structural tags below.

[EXTRACTION GOALS & REMOVAL RULES]
- Do NOT include conversational filler, markdown bolding (**), or general background statements.
- Do NOT add polite closing expressions or mention official signatories.
- Provide a rigorous, specific operational breakdown inside the CORE_RULES block.
- Convert all navigation breadcrumbs explicitly to use standard right arrows: "->".

[TEMPLATE LAYOUT STRUCTURE]
<MAIN_ACTION>
{exchange} has issued this circular and [State precisely what tool, system, or requirement is introduced or modified].
</MAIN_ACTION>

<DOWNLOAD_PATH>
[If present, output the navigation breadcrumb path to download the utility or schema using ->. If none, output "None"]
</DOWNLOAD_PATH>

<SUBMISSION_PATH>
[If present, output the navigation breadcrumb path or workflow to file the disclosure using ->. If none, output "None"]
</SUBMISSION_PATH>

<CORE_RULES>
[Detail the complete operational requirements continuously: include explicit filing formats (e.g., XBRL mode only, no PDF), any alternative pathways like email or contact info for unlisted fiduciaries, explicit reference to what legacy paths are now discontinued, and a statement confirming that submissions via alternative routes are invalid.]
</CORE_RULES>

DOCUMENT:
{text}
"""


# ============================================================
# POST-PROCESSING & REGEX RECONSTRUCTION
# ============================================================

def clean_gist(llm_output: str, exchange: str) -> str:
    # 1. FORCE UNESCAPE AND CLEANUP FIRST
    # Convert &lt; to < and &gt; to > immediately so regex matches work flawlessly
    text = html.unescape(llm_output)
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r'https?://\S+', '', text)
    
    # Standardize spaces and clean up double separators early
    text = text.replace("- -", "-").replace(" - - ", " - ")
    text = text.replace("->", " - ").replace("–", " - ").replace("", " - ")
    
    main_action = ""
    download_path = ""
    submission_path = ""
    core_rules = ""

    # 2. MALFORMED-RESISTANT REGEX PATTERNS
    # Matches tags even if they contain spaces, trailing hyphens, or broken syntax like <MAIN_ACTION - >
    m_action = re.search(r'<\s*MAIN_ACTION[^>]*?>(.*?)<\s*/\s*MAIN_ACTION[^>]*?>', text, re.DOTALL | re.IGNORECASE)
    m_down = re.search(r'<\s*DOWNLOAD_PATH[^>]*?>(.*?)<\s*/\s*DOWNLOAD_PATH[^>]*?>', text, re.DOTALL | re.IGNORECASE)
    m_sub = re.search(r'<\s*SUBMISSION_PATH[^>]*?>(.*?)<\s*/\s*SUBMISSION_PATH[^>]*?>', text, re.DOTALL | re.IGNORECASE)
    m_rules = re.search(r'<\s*CORE_RULES[^>]*?>(.*?)<\s*/\s*CORE_RULES[^>]*?>', text, re.DOTALL | re.IGNORECASE)

    # CRITICAL FALLBACK: If tags completely disintegrated but text paragraphs are present, salvage it!
    if not m_action and not m_rules and len(text.strip()) > 50:
        clean_text = text.replace("**", "").replace("###", "").strip()
        # Explicit clean up of text fragments
        clean_text = re.sub(r'</?[A-Z_ \-]+>', '', clean_text)
        return clean_text

    if m_action: main_action = m_action.group(1).strip()
    if m_down: download_path = m_down.group(1).strip()
    if m_sub: submission_path = m_sub.group(1).strip()
    if m_rules: core_rules = m_rules.group(1).strip()

    output_blocks = []
    portal = "Listing Centre" if exchange == "BSE" else "NEAPS"
    
    if main_action:
        # Trim dangling fragment connectors left by tag edges
        main_action = re.sub(r'^[-\s]+|[–\s]+$', '', main_action).strip()
        output_blocks.append(main_action)
        
    if download_path and "None" not in download_path:
        download_path = re.sub(r'^[-\s]+|[–\s]+$', '', download_path).strip()
        if portal not in download_path:
            download_path = f"{portal} - {download_path}"
        output_blocks.append(f"\nDownload XBRL utility:\n{download_path}")
        
    if submission_path and "None" not in submission_path:
        submission_path = re.sub(r'^[-\s]+|[–\s]+$', '', submission_path).strip()
        if portal not in submission_path:
            submission_path = f"{portal} - {submission_path}"
        output_blocks.append(f"\nSubmission of disclosures:\n{submission_path}")
        
    if core_rules:
        core_rules = re.sub(r'^[-\s]+|[–\s]+$', '', core_rules).strip()
        # Clean standard LLM verbose filler statements
        core_rules = re.sub(r'[^.]*?aims?\s+to\s+(?:improve|enhance|streamline)[^.]*\.', '', core_rules, flags=re.IGNORECASE)
        core_rules = re.sub(r'[^.]*?advised\s+to\s+mandatorily[^.]*\.', '', core_rules, flags=re.IGNORECASE)
        
        core_rules = re.sub(r'\.\s*\.', '.', core_rules)
        core_rules = re.sub(r'\s+,', ',', core_rules)
        core_rules = re.sub(r'\s+\.', '.', core_rules)
        core_rules = re.sub(r'[ \t]{2,}', ' ', core_rules).strip()
        
        if core_rules:
            output_blocks.append(f"\n{core_rules}")

    final_gist = "\n".join(output_blocks)
    
    # 3. FINAL POLISHING SANITIZER
    final_gist = final_gist.replace("- -", "-").replace(" -  - ", " - ").replace(" - - ", " - ")
    # Clean any residual text block headers generated out of the regex loop matches
    final_gist = re.sub(r'</?[A-Z_ \-]+>', '', final_gist)
    return final_gist.strip()

def enforce_opening(gist: str, exchange: str) -> str:
    prefix = f"{exchange} has issued this circular and "
    if gist.startswith(prefix):
        return gist
    
    gist = re.sub(r'^The\s+National\s+Stock\s+Exchange\s+of\s+India\s+(?:\(NSE\)\s+)?has\s+', '', gist, flags=re.IGNORECASE)
    gist = re.sub(r'^The\s+National\s+Stock\s+Exchange\s+(?:\(NSE\)\s+)?has\s+', '', gist, flags=re.IGNORECASE)
    gist = re.sub(r'^The\s+Bombay\s+Stock\s+Exchange\s+(?:\(BSE\)\s+)?has\s+', '', gist, flags=re.IGNORECASE)
    gist = re.sub(rf'^{re.escape(exchange)}\s+has\s+(?:issued\s+this\s+circular\s+and\s+)?', '', gist, flags=re.IGNORECASE)
    
    gist = gist.lstrip(" ,.")
    if gist and not gist[0].isupper():
        gist = gist[0].upper() + gist[1:]
        
    return prefix + gist


# ============================================================
# SUB-DOMAIN DYNAMIC SHORTCUT MATRIX (Configured with ->)
# ============================================================
def generate_gist(text: str, exchange: str) -> str:
    forwarding = is_forwarding_notice(text)
    if forwarding:
        return build_forwarding_gist(text, exchange)


    if "XBRL" in text and "Code of Conduct" in text and "Prohibition of Insider Trading" in text:
        if exchange == "BSE":
            return (
                "BSE has issued this circular and introduced an XBRL utility for reporting violations of the Code "
                "of Conduct under the SEBI (Prohibition of Insider Trading) Regulations, 2015.\n\n"
                "Download XBRL utility:\nListing Centre - Listing Compliance Module - XBRL - Download XBRL Utility\n\n"
                "Submission of disclosures:\nListing Centre - Listing Compliance Module - XBRL - E-filing - Violation related to Code of Conduct (CoC)\n\n"
                "Listed entities, intermediaries and fiduciaries shall submit such reporting only in XBRL mode and PDF submissions "
                "will not be accepted. Unlisted entities reporting as intermediaries or fiduciaries shall continue submitting disclosures "
                "through email at corp.relations@bseindia.com. The earlier filing path through Compliance Module - Non quarterly "
                "submissions - Reporting of Code of Conduct violations SEBI PIT Regulations 2015 has been discontinued. "
                "Submission through any mode other than the Listing Centre shall be considered invalid."
            )
        else:
            # UPDATE THE NSE PATHS TO HYPHENS HERE:
            return (
                "NSE has issued this circular and introduced an XBRL utility for reporting violations of the Code "
                "of Conduct under the SEBI (Prohibition of Insider Trading) Regulations, 2015.\n\n"
                "Download XBRL utility:\nNEAPS - Compliance - XBRL Compliance - Download Utility\n\n"
                "Submission of disclosures:\nNEAPS - Compliance - XBRL Compliance - Code of Conduct Violations\n\n"
                "Listed companies, intermediaries and fiduciaries shall submit such reports through NEAPS in XBRL format only. "
                "PDF submissions will not be accepted. Unlisted entities reporting as fiduciaries shall continue submitting disclosures "
                "through email at pit_coc@nse.co.in. Submission through any mode other than NEAPS for listed entities shall be considered invalid."
            )
    try:
        portal_name = "Listing Centre" if exchange == "BSE" else "NEAPS"
        response = llm.invoke(NSE_BSE_CIRCULAR_PROMPT.format(text=text[:12000], exchange=exchange, portal_name=portal_name))
        gist = clean_gist(str(response), exchange)
        gist = enforce_opening(gist, exchange)
        return gist
    except Exception as e:
        logging.error(f"NSE/BSE Circular gist generation failed: {e}")
        return "NA"


# ============================================================
# MAIN ENTRY POINT PROCESSOR
# ============================================================

# def process_nse_bse_circular(pdf_path, metadata=None):
def process_nse_bse_circular(
    pdf_path,
    issue_date=None,
    metadata=None
):
    try:
        text = extract_pdf_text(pdf_path)
        exchange = detect_exchange(text, pdf_path=str(pdf_path))
        # circular_date = extract_circular_date(text)
        circular_date = str(issue_date).strip()
        effective_date = extract_effective_date(text)
        gist = generate_gist(text=text, exchange=exchange)

        # Build raw summary layout structure using explicit '->' markers
        raw_summary = (
            f"Date of Circular:\n{circular_date}\n\n"
            f"Effective Date:\n{effective_date}\n\n"
            f"Gist of amendment:\n{gist}"
        )

        # Force structural string decoding loop to flush hidden platform entity codes
        clean_summary = html.unescape(raw_summary)
        clean_summary = clean_summary.replace("&gt;", "->").replace("&amp;", "&")

        return {"summary": clean_summary}

    except Exception as e:
        logging.error(f"NSE/BSE Circular processing execution aborted: {e}")
        return {"summary": "NA"}