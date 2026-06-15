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

- Use both contexts together to identify the practical legal effect of the amendment.

- For substituted provisions, compare the prior provision in CONTEXT A with the amended provision in CONTEXT B and summarize only the material regulatory change.

- For omitted provisions, identify which requirement, obligation, exemption, disclosure, or timeline stands removed.

- For inserted provisions, identify the newly introduced requirement, obligation, disclosure, exemption, timeline, or compliance condition.

- Do not mechanically compare old and new wording.

- Focus only on the material legal and compliance impact reflected in the text.

=======================================================
MANDATORY OUTPUT FORMAT
=======================================================

Your output must contain ONLY the following four fields.

Do not include:
- introductory lines
- dates
- circular references
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
(State only the exact legal and practical effect of the amendment reflected in the text.)

Existing provisions of Law prior to amendment:
(Extract only the prior legal provision from the footer text if available.

If not available, write:
"Not explicitly mentioned")

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