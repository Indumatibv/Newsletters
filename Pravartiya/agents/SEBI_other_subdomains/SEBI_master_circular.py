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

def extract_pdf_text(
    pdf_path: str
) -> str:

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
# MASTER CIRCULAR CORE EXTRACTION
# ============================================================

def extract_master_circular_core(
    text: str
) -> str:

    lines = text.splitlines()

    keep = []

    for line in lines:

        clean = line.strip()

        if not clean:
            continue

        if re.search(
            r'table of contents|contents|index|arrangement|abbreviations',
            clean,
            re.IGNORECASE
        ):
            break

        if len(clean) > 30:
            keep.append(clean)

        if len(keep) >= 25:
            break

    return "\n".join(keep)


# ============================================================
# PROMPT
# ============================================================

MASTER_CIRCULAR_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary.

The document is a SEBI Master Circular.

RULES:

- Start EXACTLY with:

SEBI has issued a master circular for ...

- Clearly identify the topic covered by the master circular.

- State that the circular consolidates all currently applicable instructions,
  circulars, directions and regulatory requirements relating to the subject.

- Emphasize that it serves as a single reference document and has been issued
  for ease of reference.

- Do NOT narrate the history of earlier circulars.

- Do NOT provide clause-by-clause summaries.

- Do NOT describe annexures, schedules, forms or procedural details.

- Keep the summary concise.

- End EXACTLY with:

It consolidates existing circulars, supersedes older ones where specified, and is to be read going forward.

Return ONLY the final summary.

DOCUMENT:

{text}
"""


# ============================================================
# SUMMARY GENERATION
# ============================================================

def generate_master_circular_summary(
    text: str
) -> str:

    core_text = extract_master_circular_core(
        text
    )

    try:

        summary = llm.invoke(
            MASTER_CIRCULAR_PROMPT.format(
                text=core_text
            )
        )

        return summary.strip()

    except Exception as e:

        logging.error(
            f"Master Circular summary failed: {e}"
        )

        return "NA"


# ============================================================
# MAIN PROCESSOR
# ============================================================

def process_master_circular(
    pdf_path,
    metadata=None
):

    text = extract_pdf_text(
        pdf_path
    )

    summary = generate_master_circular_summary(
        text
    )

    return {
        "summary": summary
    }