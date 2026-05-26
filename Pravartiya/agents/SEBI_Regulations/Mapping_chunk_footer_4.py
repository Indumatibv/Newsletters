import json

# def map_footers_to_exact_chapter_sections(footers_json_path, chunks_json_path, output_json_path):
#     # 1. Load the filtered footnotes dataset
#     with open(footers_json_path, "r", encoding="utf-8") as f:
#         filtered_footers = json.load(f)

#     # 2. Load the main regulation chunks dataset 
#     with open(chunks_json_path, "r", encoding="utf-8") as f:
#         regulation_chunks = json.load(f)

#     mapped_output = {}

#     # 3. Process every filtered footer one-by-one
#     for footer_num, footer_text in filtered_footers.items():
#         footer_id_int = int(footer_num)
        
#         # Step A: Locate the exact (Chapter, Section) scope where this footer reference exists
#         matched_boundaries = set()
#         for chunk in regulation_chunks:
#             # Convert values safely to strings to avoid type-mismatch gaps (e.g. None vs "")
#             ch_name = str(chunk.get("chapter") or "").strip()
#             sec_no = str(chunk.get("section") or "").strip()
            
#             # Check if our target footnote integer is inside this chunk's reference array
#             if footer_id_int in chunk.get("footer_reference", []):
#                 if sec_no:
#                     # Lock down this specific chapter + section combo boundary
#                     matched_boundaries.add((ch_name, sec_no))

#         # Step B: Scan and collect ALL chunks that reside inside those captured boundaries
#         matching_chunks = []
#         for chunk in regulation_chunks:
#             current_ch = str(chunk.get("chapter") or "").strip()
#             current_sec = str(chunk.get("section") or "").strip()
            
#             # If this dictionary block matches the exact chapter and section caught in Step A
#             if (current_ch, current_sec) in matched_boundaries:
#                 matched_chunk_copy = chunk.copy()
                
#                 # Keep the output clean by stripping the original list reference 
#                 if "footer_reference" in matched_chunk_copy:
#                     del matched_chunk_copy["footer_reference"]
                    
#                 matching_chunks.append(matched_chunk_copy)

#         # 4. Bind the consolidated list array under the specific footer key
#         mapped_output[footer_num] = {
#             "footer_text": footer_text,
#             "matched_scopes": [f"{ch} -> Section {sec}" for ch, sec in matched_boundaries],
#             "mapped_regulation_chunks": matching_chunks  # Now guaranteed to have ALL matching dictionaries
#         }

#     # 5. Write out the combined structured map back to JSON
#     with open(output_json_path, "w", encoding="utf-8") as f:
#         json.dump(mapped_output, f, indent=4, ensure_ascii=False)

#     print(f"Mapping complete! Successfully tied {len(filtered_footers)} footers to all matching chapter-section blocks.")
#     print(f"Saved complete relationship file to '{output_json_path}'.")

# if __name__ == "__main__":
#     FILTERED_FOOTERS_PATH = "filtered_footers.json"
#     REGULATION_CHUNKS_PATH = "regulation_chunks.json"
#     OUTPUT_MAPPED_PATH = "footers_mapped_to_regulations.json"

#     map_footers_to_exact_chapter_sections(
#         footers_json_path=FILTERED_FOOTERS_PATH,
#         chunks_json_path=REGULATION_CHUNKS_PATH,
#         output_json_path=OUTPUT_MAPPED_PATH
#     )
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

                    matched_boundaries.add(
                        (ch_name, sec_no)
                    )

        # ====================================================
        # COLLECT MATCHING CHUNKS
        # ====================================================

        matching_chunks = []

        for chunk in regulation_chunks:

            current_ch = str(
                chunk.get("chapter") or ""
            ).strip()

            current_sec = str(
                chunk.get("section") or ""
            ).strip()

            if (
                current_ch,
                current_sec
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

            "matched_scopes": [

                f"{ch} -> Section {sec}"

                for ch, sec in matched_boundaries
            ],

            "mapped_regulation_chunks":
                matching_chunks
        }

    return mapped_output