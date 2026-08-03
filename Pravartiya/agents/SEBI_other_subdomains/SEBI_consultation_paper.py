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

RULES

Start EXACTLY with:

**SEBI has issued this consultation paper proposing the following changes:**

Include the following sections in the same order:

### Background

* Explain the background and context that led SEBI to issue the consultation paper.
* Explain why SEBI is proposing the changes.

### Proposals

For every major proposal in the consultation paper, create a separate proposal section.

First identify all the major proposals discussed in the consultation paper.

Count the total number of major proposals.

Generate one separate Proposal section for each proposal identified.

Do not merge two or more proposals into one.

Do not omit any major proposal.

Every major proposal discussed in the consultation paper must appear exactly once in the summary.

For each proposal, provide:

**Proposal:**
* Explain the proposal in simple newsletter-style language.
* Describe the proposal in 2–4 sentences. Do not use only a heading or title. Clearly explain what SEBI is proposing.

**Existing provision (with regulation reference):**
* Briefly explain the existing legal or regulatory provision relevant to that proposal.
* Mention the applicable regulation, clause, circular or framework reference wherever available.

**Recommendation of committee (if any):**
* Mention the recommendation of any committee, working group or expert committee relevant to that proposal.
* Include this section only if a committee recommendation is explicitly mentioned in the consultation paper. Otherwise, do not generate this section.

Important Instructions

* This is a consultation paper proposing changes to the law. Focus on the proposed amendments or regulatory changes.
* Cover every major proposal separately.
* Ensure that the total number of Proposal sections in the summary matches the total number of major proposals discussed in the consultation paper.
* Where multiple proposals relate to different aspects of the proposed framework, summarize each proposal separately without combining them.
* Do not reproduce consultation questions verbatim.
* Do not provide clause-by-clause summaries.
* Do not include email addresses.
* Do not include URLs.
* Do not include procedural instructions for submitting comments.
* Do not include annexures.
* Use concise newsletter-style language.

End the summary with exactly:

**Deadline for submitting comments on the consultation paper: <date>**

Extract the deadline from the consultation paper.

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