import json

# ============================================================
# MAP FILTERED FOOTNOTES TO REGULATION CHUNKS
# ============================================================

def map_footers_to_exact_chapter_sections(

    filtered_footnotes,

    regulation_chunks
):

    mapped_output = {}

    # ========================================================
    # PROCESS EACH FOOTNOTE
    # ========================================================

    for footer_num, footer_text in filtered_footnotes.items():

        footer_id_int = int(footer_num)

        matched_boundaries = set()

        # ====================================================
        # FIND REFERENCED CHAPTER/SECTION
        # ====================================================

        for chunk in regulation_chunks:

            ch_name = str(
                chunk.get("chapter") or ""
            ).strip()

            sec_no = str(
                chunk.get("section") or ""
            ).strip()

            if footer_id_int in chunk.get(
                "footer_reference",
                []
            ):

                if sec_no:

                    # matched_boundaries.add(
                    #     (ch_name, sec_no)
                    # )
                    sub_no = str(
                        chunk.get("subsection") or ""
                    ).strip()

                    matched_boundaries.add(
                        (ch_name, sec_no, sub_no)
                    )
        # ====================================================
        # COLLECT MATCHING CHUNKS
        # ====================================================

        matching_chunks = []

        for chunk in regulation_chunks:

            # current_ch = str(
            #     chunk.get("chapter") or ""
            # ).strip()

            # current_sec = str(
            #     chunk.get("section") or ""
            # ).strip()

            # if (
            #     current_ch,
            #     current_sec
            # ) in matched_boundaries:
            current_ch = str(
                chunk.get("chapter") or ""
            ).strip()

            current_sec = str(
                chunk.get("section") or ""
            ).strip()

            current_sub = str(
                chunk.get("subsection") or ""
            ).strip()

            if (
                current_ch,
                current_sec,
                current_sub
            ) in matched_boundaries:
                matched_chunk_copy = chunk.copy()

                if (
                    "footer_reference"
                    in matched_chunk_copy
                ):

                    del matched_chunk_copy[
                        "footer_reference"
                    ]

                matching_chunks.append(
                    matched_chunk_copy
                )

        # ====================================================
        # BUILD OUTPUT
        # ====================================================

        mapped_output[footer_num] = {

            "footer_text":
                footer_text,

            # "matched_scopes": [

            #     f"{ch} -> Section {sec}"

            #     for ch, sec in matched_boundaries
            # ],
            "matched_scopes": [

                f"{ch} -> Section {sec}" + (f" -> {sub}" if sub else "")

                for ch, sec, sub in matched_boundaries
            ],
            "mapped_regulation_chunks":
                matching_chunks
        }

    return mapped_output