import logging

from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

llm = Ollama(
    model="mistral:latest"
)

# ============================================================
# PDF TEXT EXTRACTION
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
# PROMPT
# ============================================================

CONSULTATION_PAPER_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary.

The document is a SEBI Consultation Paper.

Generate a newsletter-style summary.

RULES:

Start EXACTLY with:

SEBI has issued this consultation paper proposing the following changes...

Include:

1. Background of the consultation paper.
2. Objective of the consultation paper.
3. Key proposals / points on which views of the public are sought.

IMPORTANT:

- Explain why SEBI is proposing changes.
- Focus on the proposed changes in law, regulations, framework or process.
- Summarize the key proposals.
- Do not reproduce consultation questions verbatim.
- Do not provide clause-by-clause summaries.
- Do not include email addresses.
- Do not include URLs.
- Do not include procedural submission instructions.
- Do not include annexures.

End the summary with:

Comments may be submitted till <date>.

Extract the date from the consultation paper.

Return ONLY the final summary.

DOCUMENT:

{text}
"""


# ============================================================
# SUMMARY GENERATION
# ============================================================

def generate_consultation_paper_summary(
    text: str
) -> str:

    try:

        summary = llm.invoke(
            CONSULTATION_PAPER_PROMPT.format(
                text=text[:15000]
            )
        )

        return summary.strip()

    except Exception as e:

        logging.error(
            f"Consultation paper summary failed: {e}"
        )

        return "NA"


# ============================================================
# MAIN PROCESSOR
# ============================================================

def process_consultation_paper(
    pdf_path,
    metadata=None
):

    text = extract_pdf_text(
        pdf_path
    )

    summary = generate_consultation_paper_summary(
        text
    )

    return {

        "summary": summary
    }