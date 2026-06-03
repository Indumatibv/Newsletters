import logging
import re

from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

llm = Ollama(
    model="mistral:latest"
)

# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_text(pdf_path: str) -> str:

    raw = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=False
    )

    text = "\n".join(
        str(el)
        for el in raw
        if el
    ).strip()

    if not text:
        logging.warning(
            f"Fast extraction yielded no text for {pdf_path}. Falling back to hi_res."
        )
        raw = partition_pdf(
            filename=str(pdf_path),
            strategy="hi_res"
        )
        text = "\n".join(
            str(el)
            for el in raw
            if el
        ).strip()

    return text


# ============================================================
# PROMPT
# ============================================================

PRESS_RELEASE_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary.

The document is a SEBI Press Release.

Requirements:

- Start EXACTLY with:

  The press release issued states that

- Summarize ONLY the key outcome, decision, action or development that a reader
  should know.

- Focus on:
  - What SEBI has done or decided
  - What has changed, been introduced, approved, operationalised or clarified
  - The impact on regulated entities, investors or market participants

- The summary must focus on the REGULATORY OUTCOME only.

- Do NOT mention the names of any specific companies, agencies, exchanges,
  or other entities that have been recognised, appointed, empanelled, or
  designated to implement the outcome — even if they are named in the document.
  Describe what the framework or mechanism does, not who operates it.

- Do NOT mention:
  - Pilot phases or implementation history
  - Background chronology or recognition/appointment processes
  - Operational arrangements or data centre details
  - Website links, website availability, or calls to action
  - Contact details, venue, location, or media references
  - Dates, unless essential to understanding the outcome

- Keep the summary concise.
- Write 2 to 3 sentences maximum.
- Maximum 80 words.
- Write as a single paragraph.
- Do NOT end with a call to action or website reference.

EXAMPLES OF WHAT NOT TO WRITE:
- "...with CARE Ratings Limited as the recognised agency and NSE acting as the data centre." [WRONG — names implementing entities]
- "CARE Ratings Limited was granted recognition as PaRRVA." [WRONG — describes recognition process]
- "The website of PaRRVA can be accessed here." [WRONG — website reference]

EXAMPLE OF CORRECT STYLE:
- "The press release issued states that SEBI has operationalised a verification agency for past risk and return, enabling regulated entities to showcase verified performance in their advertisements while providing investors access to authenticated data."

Return ONLY the final summary. No introductory text. No notes.

DOCUMENT:

{text}
"""


# ============================================================
# POST-PROCESSING CLEANUP
# ============================================================

# Website reference patterns
WEBSITE_PATTERNS = [
    re.compile(
        r'[^.]*?(?:website|web\s+portal|web\s+page)[^.]*'
        r'(?:can\s+be\s+accessed|is\s+(?:now\s+)?(?:accessible|available))[^.]*\.',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:Access|Visit|See)\s+the\s+\S+\s+(?:website|portal)[^.]*\.',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:For\s+more\s+(?:details|information)|More\s+details)[^.]*\.',
        re.IGNORECASE
    ),
    re.compile(
        r'The\s+\S+\s+website[^.]*\.',
        re.IGNORECASE
    ),
]

# Implementing entity name patterns — catches all common phrasings
IMPLEMENTING_ENTITY_PATTERNS = [
    # "X Limited has been granted recognition / recognised / appointed / empanelled"
    re.compile(
        r'[A-Z][\w\s,]+(?:Limited|Ltd\.?|LLP|Exchange|Corporation)\s+'
        r'(?:has\s+been|was|were)\s+'
        r'(?:granted\s+recognition|recogni[sz]ed|appointed|empanelled|'
        r'designated|selected)[^.]*\.',
        re.IGNORECASE
    ),
    # "X Limited is acting / acts as"
    re.compile(
        r'[A-Z][\w\s,]+(?:Limited|Ltd\.?|LLP|Exchange|Corporation)\s+'
        r'(?:is\s+acting|acts|will\s+act)\s+as[^.]*\.',
        re.IGNORECASE
    ),
    # ", with X Limited as the recognised agency / data centre / operator"
    re.compile(
        r',\s+with\s+[A-Z][\w\s,]+(?:Limited|Ltd\.?|LLP|Exchange|Corporation)'
        r'\s+(?:as|acting)[^,.]+'
        r'(?:and\s+[A-Z][\w\s,]+(?:Limited|Ltd\.?|LLP|Exchange|Corporation)'
        r'\s+(?:as|acting)[^,.]+)?',
        re.IGNORECASE
    ),
    # "X Limited acting as"
    re.compile(
        r'[A-Z][\w\s,]+(?:Limited|Ltd\.?|LLP|Exchange|Corporation)\s+'
        r'acting\s+as[^.]*\.',
        re.IGNORECASE
    ),
]


def remove_unwanted_sentences(text: str) -> str:
    """
    Removes sentences or clauses matching website references
    and implementing entity details.
    """
    for pattern in WEBSITE_PATTERNS + IMPLEMENTING_ENTITY_PATTERNS:
        text = pattern.sub('', text)

    # Clean up any double spaces or leading commas left after removal
    text = re.sub(r'\s*,\s*\.', '.', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.strip()
    return text


def enforce_opening(summary: str) -> str:
    """Ensures the summary starts with the required phrase."""
    required = "the press release issued states that"
    if not summary.lower().startswith(required):
        summary = "The press release issued states that " + summary.lstrip(". ")
    return summary


def truncate_to_word_limit(text: str, max_words: int = 80) -> str:
    """Truncates to max_words at a sentence boundary where possible."""
    words = text.split()
    if len(words) <= max_words:
        return text
    truncated = " ".join(words[:max_words])
    last_period = truncated.rfind('.')
    if last_period > 0:
        return truncated[:last_period + 1]
    return truncated + "."


# ============================================================
# SUMMARY GENERATION
# ============================================================

def generate_press_release_summary(text: str) -> str:

    core_text = re.sub(r"\s+", " ", text).strip()
    core_text = core_text[:12000]

    try:
        summary = llm.invoke(
            PRESS_RELEASE_PROMPT.format(text=core_text)
        )

        summary = summary.strip()

        # Remove unwanted sentences and clauses
        summary = remove_unwanted_sentences(summary)

        # Normalize whitespace
        summary = re.sub(r"\s+", " ", summary).strip()

        # Enforce required opening phrase
        summary = enforce_opening(summary)

        # Enforce word limit
        summary = truncate_to_word_limit(summary, max_words=80)

        return summary

    except Exception as e:
        logging.error(f"Press Release summary failed: {e}")
        return "NA"


# ============================================================
# MAIN PROCESSOR
# ============================================================

def process_press_release(pdf_path, metadata=None):

    text = extract_pdf_text(pdf_path)

    summary = generate_press_release_summary(text)

    return {
        "summary": summary
    }