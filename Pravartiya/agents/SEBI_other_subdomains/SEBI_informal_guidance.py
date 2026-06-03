import logging
import re
import html
from unstructured.partition.pdf import partition_pdf
from langchain_community.llms import Ollama

llm = Ollama(
    model="mistral:latest"
)

# ============================================================
# PDF TEXT EXTRACTION
# ============================================================
def clean_html_entities(text: str) -> str:
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

Regulation reference given by SEBI and gist of that Regulation reference

Response from SEBI

If multiple queries exist:

Query 1

Regulation reference given by SEBI and gist of that Regulation reference

Response from SEBI

Query 2

Regulation reference given by SEBI and gist of that Regulation reference

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
- Focus on the regulatory clarification being sought.

3. Regulation reference given by SEBI and gist of that Regulation reference

- Identify the regulations, circulars, provisions or guidance relied upon by SEBI.
- The gist MUST be derived from the regulatory provisions and explanatory statements cited by SEBI in the letter before answering the query.
- Where the letter contains clause (a), clause (b), clause (c), numbered provisions or explanatory paragraphs before the query, use those provisions to prepare the gist.
- Explain what the cited regulation, circular or provision requires, permits or prohibits in the context of the query.
- Explain why the provision is relevant to the query.
- Where the same regulatory provisions apply to multiple queries, identify the provisions most relevant to the specific query and summarize only those provisions.
- Do NOT merely list regulation names.
- Do NOT copy regulation text verbatim.
- Do NOT reproduce the entire provision.
- Write the gist as a concise newsletter-style paragraph.
- The gist should summarize the substance of the provision in plain language.
- Mention the regulation reference cited by SEBI before explaining its gist.
- Do not omit the regulation number, circular reference or clause reference.
- Do NOT include SEBI's interpretation, clarification, conclusion or final position in this section.
- Only explain what the cited regulation, circular or provision provides.
- SEBI's interpretation must be captured only under "Response from SEBI".
- A response that only contains regulation names is incorrect.
- In such cases, do NOT derive a regulation gist from SEBI's response.
- Do NOT move SEBI's response into the regulation gist section.
- If no regulation, circular, provision or guidance is cited by SEBI for a query, write exactly:

  Regulation reference given by SEBI and gist of that Regulation reference:

  No specific regulation or provision was cited by SEBI for this query.

- Do not create a regulation gist from factual observations, SEBI responses, assumptions or inferred principles.

4. Response from SEBI
- Map each response to the correct query.
- Summarize SEBI's response in concise newsletter style.
- Do not reproduce paragraph numbering such as 4.1, 4.2, 4.3 etc.
- Do not copy large portions of the letter verbatim.
- Extract the regulatory conclusion and rationale.
- Present the response as a coherent paragraph.
- If SEBI has declined to provide guidance, clearly state that SEBI declined to provide guidance and summarize the reason.
- Do not infer or create a response where SEBI has not provided one.
- If SEBI answers multiple queries together, correctly map the answer to each relevant query.
- If SEBI states that a query is general in nature, does not cite applicable legal provisions, falls outside the scope of the Informal Guidance Scheme, or otherwise declines to answer, explicitly state that SEBI declined to provide guidance and summarize the reason.
- Do not convert SEBI's refusal to provide guidance into a substantive regulatory answer.
- Where no specific regulation has been cited by SEBI, keep the regulation section as:
  "No specific regulation or provision was cited by SEBI for this query."
- Place SEBI's entire substantive reasoning under "Response from SEBI".
- Do not use the standard disclaimer, caveat, approval paragraph, enforcement position paragraph, or concluding paragraphs of the letter as a response to any query.
- Responses must be derived only from the section where SEBI answers the query.
- Where SEBI declines to answer a query and later sections of the letter contain standard disclaimers, caveats, enforcement statements, scope limitations or concluding remarks, do NOT treat those paragraphs as the response.
- The response must be taken only from the specific section addressing that query.
- Where SEBI provides a shared response for multiple queries, map the same response to every query explicitly covered by that response section.
- If a response section refers to multiple query numbers, every referenced query must receive that response in the output.
- Do not assign a different response, disclaimer, caveat or concluding paragraph to a query that is already covered by a shared response section.

IMPORTANT:

Many SEBI letters provide:
- all queries first
- all responses later

You MUST correctly map every query to its corresponding response.
Where SEBI provides a shared response for multiple queries, map that response to all referenced queries.

- Include EVERY query raised in the letter.
- Do not stop after the first query.
- For each query identified in the letter, generate a separate section consisting of:

  Query

  Regulation reference given by SEBI and gist of that Regulation reference

  Response from SEBI

- Verify that every query appearing in the letter has been addressed in the output.
- A summary that omits any query from the letter is incorrect.
- Do not summarize multiple queries into a single concluding paragraph.
- Every query appearing in the letter must be explicitly shown in the output.
- Queries that do not have a specific regulation reference must still be included with their corresponding SEBI response.

Every Query section must be immediately followed by:
- Regulation reference given by SEBI and gist of that Regulation reference
- Response from SEBI

Do NOT group all queries together and all responses together.

Do not merge distinct queries unless SEBI has explicitly provided a common response for multiple queries.

If SEBI provides a common response for multiple queries:

- Preserve the original query numbering and sequencing from the letter.
- Do not renumber queries.
- Do not reassign the content of one query to another query.
- Do not omit any query.
- Every query identified in the letter must either:
  (a) have its own response, or
  (b) be explicitly included in a grouped response if SEBI answered multiple queries together.
- When grouping queries, retain all original query numbers covered by the shared response.

Do not invent information.

If only one query exists in the document:

Use:

Query

Regulation reference given by SEBI and gist of that Regulation reference

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

Do NOT reproduce:
- paragraph numbers
- section numbers

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

        # summary = llm.invoke(
        #     INFORMAL_GUIDANCE_PROMPT.format(
        #         text=cleaned_text[:25000]
        #     )
        # )
        summary = llm.invoke(
            INFORMAL_GUIDANCE_PROMPT.format(
                text=cleaned_text[:18000]
            )
        )
        # print("RAW LLM OUTPUT:", repr(summary[:200]))  # ADD THIS

        # prev = None
        # while prev != summary:
        #     prev = summary
        #     summary = html.unescape(summary)
        summary = clean_html_entities(summary)
        # print("AFTER UNESCAPE:", repr(summary[:200]))  # ADD THIS

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