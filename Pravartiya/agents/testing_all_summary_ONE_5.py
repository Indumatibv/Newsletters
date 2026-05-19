# ============================================================
# STRICT FACT-GROUNDED COMPLIANCE SUMMARY GENERATOR
# ============================================================

import json
import requests
import re


# ============================================================
# ISOLATE ONLY TARGET CLAUSE USING FOOTNOTE MARKER
# Example:
# 407[
# ============================================================

def extract_clause_with_footnote_marker(
    text,
    footnote_num
):

    marker = f"{footnote_num}["

    if marker not in text:
        return text

    # Find exact inline amendment fragment
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
# MAIN SUMMARY GENERATOR
# ============================================================

def generate_factual_footer_summary(
    mapped_json_path,
    target_footer_id=None
):

    print(
        f"Loading mapped relationship dataset from '{mapped_json_path}'..."
    )

    with open(
        mapped_json_path,
        "r",
        encoding="utf-8"
    ) as f:

        mapped_data = json.load(f)

    if not mapped_data:

        print("Error: Dataset is empty.")

        return


    # ========================================================
    # TARGET FOOTNOTE
    # ========================================================

    if target_footer_id is not None:

        selected_footer_id = str(
            target_footer_id
        ).strip()

        if selected_footer_id not in mapped_data:

            print(
                f"[ERROR] Footnote ID '{selected_footer_id}' was not found."
            )

            return

    else:

        selected_footer_id = list(
            mapped_data.keys()
        )[0]


    target_entry = mapped_data[
        selected_footer_id
    ]


    footer_text = target_entry.get(
        "footer_text",
        ""
    ).strip()


    regulation_chunks = target_entry.get(
        "mapped_regulation_chunks",
        []
    )


    # ========================================================
    # ISOLATE EXACT CLAUSE
    # ========================================================

    extracted_clauses = []

    for chunk in regulation_chunks:

        chunk_text = chunk.get(
            "text",
            ""
        )

        isolated_clause = (
            extract_clause_with_footnote_marker(
                chunk_text,
                selected_footer_id
            )
        )

        extracted_clauses.append(
            isolated_clause
        )


    filtered_context = "\n\n".join(
        list(set(extracted_clauses))
    )


    # ========================================================
    # STRICT LEGAL PROMPT
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
CONTEXT A: TARGET FOOTNOTE
=======================================================

{footer_text}

=======================================================
CONTEXT B: TARGET REGULATION CLAUSE
=======================================================

{filtered_context}

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

Your output must contain ONLY the following three fields.

Do not include:
- introductory lines
- dates
- circular references
- section numbers
- administrative references
- email ids

-------------------------------------------------------

Gist of amendment:
(State only the exact legal and practical effect of the amendment reflected in the text.

- If a provision is inserted, clearly state the new requirement, obligation, disclosure, exemption, timeline, or compliance condition introduced.

- If a provision is omitted, clearly state that the relevant requirement, obligation, exemption, disclosure requirement, or timeline stands removed.

- If a provision is substituted, summarize the practical regulatory change introduced by the revised provision instead of mechanically comparing old and new wording.

- Focus only on the material change introduced by the amendment.

- Avoid generic statements such as "specified by the Board" where such wording already existed in the earlier provision.

- Do not include commentary, assumptions, interpretation notes, or meta-analysis.

Do not speculate beyond the text.)


Existing provisions of Law prior to amendment:
(Extract only the prior legal provision from the footer text if available.
Do not include commentary, assumptions, or explanatory notes.
If not available, write:
"Not explicitly mentioned")

Action point for listed entity if any:
(State only compliance actions directly resulting from the amendment text.
If a provision is omitted, state that entities should update internal governance records, trackers, timelines, exemptions, or compliance references to remove references to the omitted provision.
Do not speculate beyond the amendment text.)
"""


    # ========================================================
    # OLLAMA REQUEST
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


    print(
        f"Generating summary for Footnote ID: {selected_footer_id}"
    )


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


        print(
            "\n==================== COMPLIANCE SUMMARY ====================\n"
        )

        print(summary_result)

        print(
            "\n============================================================\n"
        )


        output_filename = (
            f"compliance_summary_footer_{selected_footer_id}.txt"
        )

        with open(
            output_filename,
            "w",
            encoding="utf-8"
        ) as out_f:

            out_f.write(summary_result)


        print(
            f"Saved: {output_filename}"
        )


    except Exception as e:

        print(
            f"[ERROR] {e}"
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    CHOSEN_FOOTNOTE_ID = "612"

    generate_factual_footer_summary(

        mapped_json_path="footers_mapped_to_regulations.json",

        target_footer_id=CHOSEN_FOOTNOTE_ID
    )