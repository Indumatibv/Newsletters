# ============================================================
# BULK FOOTNOTE COMPLIANCE SUMMARY GENERATOR
# ============================================================

import requests
import re


# ============================================================
# STRICT INLINE FOOTNOTE CLAUSE EXTRACTION
# ============================================================

def extract_clause_with_footnote_marker(text,footnote_num):

    marker = f"{footnote_num}["

    if marker not in text:
        return text

    pattern = rf'([^.]*?{re.escape(marker)}.*?[.])'

    match = re.search(
        pattern,
        text,
        flags=re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return text

# ============================================================
# DETECT AMENDMENT TYPE
# ============================================================

def detect_amendment_type(footer_text):

    footer_lower = footer_text.lower()

    if "inserted" in footer_lower:
        return "inserted"

    elif "omitted" in footer_lower:
        return "omitted"

    elif "substituted" in footer_lower:
        return "substituted"

    return "unknown"


# ============================================================
# GENERATE SUMMARY FOR SINGLE FOOTER
# ============================================================

def generate_summary_for_footer(footer_id,footer_payload):

    footer_text = footer_payload.get(
        "footer_text",
        ""
    ).strip()


    amendment_type = detect_amendment_type(
        footer_text
    )


    regulation_chunks = footer_payload.get(
        "mapped_regulation_chunks",
        []
    )


    # ========================================================
    # EXTRACT REGULATION NUMBERS
    # ========================================================

    mapped_regulation_numbers = []

    extracted_clauses = []


    for chunk in regulation_chunks:

        chunk_text = chunk.get(
            "text",
            ""
        )

        regulation_number = str(
            chunk.get("section", "")
        ).strip()

        if regulation_number:

            mapped_regulation_numbers.append(
                regulation_number
            )

        isolated_clause = (
            extract_clause_with_footnote_marker(
                chunk_text,
                footer_id
            )
        )

        extracted_clauses.append(
            isolated_clause
        )


    mapped_regulation_numbers = sorted(
        list(
            set(
                mapped_regulation_numbers
            )
        )
    )


    regulation_numbers_text = ", ".join(
        mapped_regulation_numbers
    )


    filtered_context = "\n\n".join(
        dict.fromkeys(
            extracted_clauses
        )
    )


    # ========================================================
    # PROMPT
    # ========================================================

    prompt = f"""
[SYSTEM INSTRUCTION]

You are a factual legal documentation parser.

You must generate a compliance summary strictly from the provided contexts.

Do not infer.
Do not speculate.
Do not introduce external legal interpretation.
Do not generate broader governance implications unless explicitly mentioned.

=======================================================
AMENDMENT TYPE
=======================================================

{amendment_type}

AMENDMENT TYPE OVERRIDE RULE

The amendment type has already been determined from CONTEXT A.

The first word of "Gist of amendment" MUST exactly match the amendment type supplied above.

If AMENDMENT TYPE = substituted:
- Gist of amendment MUST begin with "Substituted:"
- Do not begin with Inserted: or Omitted:

If AMENDMENT TYPE = inserted:
- Gist of amendment MUST begin with "Inserted:"
- Do not begin with Substituted: or Omitted:

If AMENDMENT TYPE = omitted:
- Gist of amendment MUST begin with "Omitted:"
- Do not begin with Substituted: or Inserted:

Use the amendment type provided above even if CONTEXT B could be interpreted differently.

Never change the amendment type.

=======================================================
CONTEXT A: TARGET FOOTNOTE
=======================================================

{footer_text}

=======================================================
CONTEXT B: TARGET REGULATION CLAUSE
=======================================================

{filtered_context}

=======================================================
MAPPED REGULATION NUMBERS
=======================================================

{regulation_numbers_text}

=======================================================
INTERPRETATION RULES
=======================================================

- CONTEXT A contains amendment metadata and, where available, the prior legal provision before amendment.

- CONTEXT B contains the currently applicable amended regulation text.

Use CONTEXT A and CONTEXT B together.

Compare the provisions of the regulation as they existed prior to the amendment with the amended provisions and provide a consolidated gist highlighting the key changes.

The comparison must be based only on the text provided in CONTEXT A and CONTEXT B.

Do not infer legal consequences that are not expressly supported by the text.

Do not assume obligations continue, cease, expand, or reduce unless such conclusion is directly supported by the amended provision.

AMENDMENT TERMINOLOGY RULE

When the amendment type is:
- substituted -> use only the word "substituted"
- inserted -> use only the word "inserted"
- omitted -> use only the word "omitted"

Do not replace these terms with synonyms such as:
- replaced
- changed
- modified
- revised
- added
- introduced
- included
- removed
- deleted
- dropped

For substituted provisions:
- Use the word "substituted" in the gist and do not use words such as "replaced", "changed", "modified", or "revised".
- Explain what provision has been substituted and what the amended provision now states.
- Clearly identify both the prior provision and the amended provision wherever possible.
- Base the comparison only on the text provided in CONTEXT A and CONTEXT B.
- Do not infer consequences that are not expressly supported by the text.

For inserted provisions:
- Use the word "inserted" in the gist and do not use words such as "added", "introduced", or "included".
- Explain what new requirement, obligation, exemption, disclosure, threshold, timeline, condition, or provision has been inserted.
- Base the description only on the inserted text and amended provision.
- Do not infer consequences that are not expressly supported by the text.

For omitted provisions:
- Use the word "omitted" in the gist and do not use words such as "removed", "deleted", or "dropped".
- Explain what requirement, obligation, exemption, disclosure, threshold, timeline, condition, or provision has been omitted.
- Base the description only on the omitted text and amended provision.
- Do not infer consequences that are not expressly supported by the text.

Focus on the actual textual change between the prior and amended provisions.

- Do not mechanically compare old and new wording.


EDITORIAL AMENDMENT FILTER

Do not generate amendment summaries for amendments that are purely editorial in nature and do not change legal meaning, compliance requirements, applicability, rights, obligations, thresholds, timelines, disclosures, approvals, exemptions, or responsibilities.

Examples:
- capitalization changes
- grammar corrections
- punctuation corrections
- spelling corrections
- insertion or omission of words such as "a", "an", "the"
- reference changes such as "regulation" to "chapter"
- omission of the word "regulation"

If the amendment only changes:
- wording
- drafting style
- cross references
- capitalization
- punctuation
- grammar
- formatting

and does not change any compliance requirement, threshold, timeline, disclosure, approval, applicability, right, obligation, exemption, or responsibility,

treat it as an editorial amendment.

If the amendment is purely editorial, output:

Gist of amendment:
Editorial amendment only. No substantive regulatory change.

WORD-LEVEL AMENDMENT FILTER

If the footer only indicates substitution, insertion or omission of:
- a single word
- a phrase
- a letter
- punctuation
- capitalization
- reference terminology
- chapter/regulation references

and the footer does not provide any prior substantive provision,

treat the amendment as editorial unless the amended text clearly introduces, removes or changes:
- obligations
- thresholds
- timelines
- disclosures
- approvals
- exemptions
- applicability
- responsibilities
- rights

In such cases output:

Gist of amendment:
Editorial amendment only. No substantive regulatory change.

=======================================================
MANDATORY OUTPUT FORMAT
=======================================================

Your output must contain ONLY the following four fields.

Do not include:
- introductory lines
- dates
- circular references
- circular index references
- amendment notification references
- amendment regulation titles
- section numbers
- administrative references
- email ids
- commentary
- assumptions
- meta-analysis

-------------------------------------------------------

Regulation Number:
(State the mapped regulation number(s) associated with this amendment.)

Gist of amendment:
Compare the prior provision and amended provision and provide a concise consolidated gist of the key change.

If the amendment changes a number, percentage, monetary value, threshold, quantity, frequency, timeline, deadline, or number of days:

- State both the amended value and the previous value.
- Mention the previous value in brackets.

Existing provisions of Law prior to amendment:
Extract the prior provision from CONTEXT A exactly as provided.

Retain key amendment words such as inserted, substituted, omitted, prior to substitution, prior to omission, etc., wherever present in the footer text.

Do not paraphrase.
Do not omit material wording.
If unavailable, write:
"Not explicitly mentioned"

Action point for listed entity if any:
(State only compliance actions directly resulting from the amendment text.)
"""


    # ========================================================
    # OLLAMA CALL
    # ========================================================

    OLLAMA_URL = "http://localhost:11434/api/generate"

    payload = {

        "model": "mistral:latest",

        "prompt": prompt,

        "stream": False,

        "options": {

            "temperature": 0.0,

            "top_p": 0.1
        }
    }


    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=90
        )

        response.raise_for_status()

        summary_result = response.json().get(
            "response",
            ""
        ).strip()

        # ====================================================
        # FORCE CORRECT AMENDMENT TYPE PREFIX
        # ====================================================

        if amendment_type == "omitted":

            summary_result = re.sub(
                r'(Gist of amendment:\s*)(Inserted:|Substituted:|Omitted:)?\s*',
                r'\1Omitted: ',
                summary_result,
                count=1,
                flags=re.IGNORECASE
            )

        elif amendment_type == "inserted":

            summary_result = re.sub(
                r'(Gist of amendment:\s*)(Inserted:|Substituted:|Omitted:)?\s*',
                r'\1Inserted: ',
                summary_result,
                count=1,
                flags=re.IGNORECASE
            )

        elif amendment_type == "substituted":

            summary_result = re.sub(
                r'(Gist of amendment:\s*)(Inserted:|Substituted:|Omitted:)?\s*',
                r'\1Substituted: ',
                summary_result,
                count=1,
                flags=re.IGNORECASE
            )


        return summary_result

    except Exception as e:

        return f"[ERROR] {str(e)}"


# ============================================================
# REUSABLE SUMMARY PROCESSOR
# ============================================================

def process_all_footers(mapped_data):

    # print(
    #     f"Loading JSON from: {input_json_path}"
    # )

    # with open(
    #     input_json_path,
    #     "r",
    #     encoding="utf-8"
    # ) as f:

    #     mapped_data = json.load(f)


    total = len(mapped_data)

    print(
        f"Total footnotes found: {total}"
    )


    processed_count = 0


    for footer_id, payload in mapped_data.items():

        print(
            f"\nProcessing Footer ID: {footer_id}"
        )

        summary = generate_summary_for_footer(

            footer_id=footer_id,

            footer_payload=payload
        )

        mapped_data[footer_id][
            "footnote_number"
        ] = str(footer_id)
        # ====================================================
        # ADD SUMMARY TO ORIGINAL JSON
        # ====================================================

        mapped_data[footer_id][
            "summary"
        ] = summary


        processed_count += 1

        print(
            f"Completed {processed_count}/{total}"
        )


    # ========================================================
    # SAVE UPDATED JSON
    # ========================================================

    # with open(
    #     output_json_path,
    #     "w",
    #     encoding="utf-8"
    # ) as out_f:

    #     json.dump(
    #         mapped_data,
    #         out_f,
    #         indent=2,
    #         ensure_ascii=False
        # )


    print(
        "\n=================================================="
    )

    print(
        "Completed summary generation"
    )

    print(
        "=================================================="
    )

    return mapped_data
    

# ============================================================
# RUN
# ============================================================

# if __name__ == "__main__":

#     process_all_footers(

#         input_json_path="footers_mapped_to_regulations.json",

#         output_json_path="footers_with_compliance_summary.json"
#     )