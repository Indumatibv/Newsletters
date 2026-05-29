import logging
import re
import html
from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

import re


llm = Ollama(
    model="mistral:latest"
)

# ============================================================
# PDF TEXT EXTRACTION
# ============================================================
def clean_html_entities(text: str) -> str:
    # Keep unescaping until no more entities remain
    prev = None
    while prev != text:
        prev = text
        text = html.unescape(text)
    return text

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
# CLEANUP
# ============================================================

def clean_text(
    text: str
) -> str:

    # Remove shareholding percentages

    text = re.sub(
        r'\b\d+(?:\.\d+)?\s*%',
        '',
        text
    )

    text = re.sub(
        r'\s+',
        ' ',
        text
    )

    return text.strip()


# ============================================================
# PROMPT
# ============================================================

INFORMAL_GUIDANCE_PROMPT = """
You are a senior SEBI regulatory analyst preparing a Pravartiya newsletter summary.

The document is a SEBI Informal Guidance letter.

Generate the summary using EXACTLY the following structure.

Background & Facts

Query

Regulation reference given by SEBI

Response from SEBI

If multiple queries exist:

Query 1

Regulation reference given by SEBI

Response from SEBI

Query 2

Regulation reference given by SEBI

Response from SEBI

and so on.

RULES:

1. Background & Facts

- Start with the entity seeking guidance.
- Clearly identify the regulatory issue involved.
- Explain why clarification was sought.
- Summarize only the facts necessary to understand the query.
- Facts should focus on the subject matter and relevant regulation, not the underlying transaction.
- Focus on the relevant regulations, circulars or provisions.
- Facts should speak about the subject matter of the query and relevant regulation.
- Do NOT focus on transaction details.
- Do NOT focus on commercial arrangements.
- Ignore percentage shareholding.
- Ignore acquisition percentages.
- Ignore consideration values.
- Write in newsletter style.
- Do NOT begin with phrases such as:
  "The query pertains to"
  "The applicant sought clarification regarding"

2. Query
- Extract every query separately.
- Summarize the query in clear regulatory language.
- Do not reproduce the query verbatim from the letter unless necessary.
- Focus on the regulatory clarification being sought.

3. Regulation reference given by SEBI
- Extract only regulations, circulars, provisions or guidance relied upon by SEBI.

4. Response from SEBI
- Map each response to the correct query.
- Summarize SEBI's response in concise newsletter style.
- Do not reproduce paragraph numbering such as 4.1, 4.2, 4.3 etc.
- Do not copy large portions of the letter verbatim.
- Extract the regulatory conclusion and rationale.
- Present the response as a coherent paragraph.

IMPORTANT:

Many SEBI letters provide:
- all queries first
- all responses later

You MUST correctly map:

Query 1 -> Response 1

Query 2 -> Response 2

Query 3 -> Response 3

Every Query section must be immediately followed by:
- Regulation reference given by SEBI
- Response from SEBI

Do NOT group all queries together and all responses together.

Do not merge queries.

Do not invent information.

If only one query exists in the document:

Use:

Query

Regulation reference given by SEBI

Response from SEBI

Do NOT use Query 1.

Return ONLY the final formatted summary.

Do not include:
- introductory text
- concluding text
- observations
- notes
- disclaimers
- markdown code blocks

The final output must be a summary and not an extraction.

Do NOT reproduce:
- paragraph numbers
- section numbers
- question numbering from the source document unless necessary for understanding.

DOCUMENT:

{text}
"""


# ============================================================
# SUMMARY GENERATOR
# ============================================================

def generate_informal_guidance_summary(
    text: str
) -> str:

    cleaned_text = clean_text(
        text
    )

    try:

        summary = llm.invoke(
            INFORMAL_GUIDANCE_PROMPT.format(
                text=cleaned_text[:50000]
            )
        )
        print("RAW LLM OUTPUT:", repr(summary[:200]))  # ADD THIS

        prev = None
        while prev != summary:
            prev = summary
            summary = html.unescape(summary)
        print("AFTER UNESCAPE:", repr(summary[:200]))  # ADD THIS

        return summary.strip()

    except Exception as e:

        logging.error(
            f"Informal guidance summary failed: {e}"
        )

        return "NA"


# ============================================================
# MAIN PROCESSOR
# ============================================================

def process_informal_guidance(
    pdf_path,
    metadata=None
):

    text = extract_pdf_text(
        pdf_path
    )

    summary = generate_informal_guidance_summary(
        text
    )

    return {

        "summary": summary
    }
