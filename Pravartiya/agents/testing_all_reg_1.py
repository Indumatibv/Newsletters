import pdfplumber
import re
import json


# ============================================================
# CLEAN LEGAL TEXT
# ============================================================
def clean_legal_text(text):
    # Remove standalone page numbers
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)

    # Remove excessive spaces/tabs
    text = re.sub(r'[ \t]+', ' ', text)

    # Normalize newlines
    text = re.sub(r'\\n{2,}', '\n\n', text)

    return text.strip()


# ============================================================
# FIXED: EXTRACT TEXT BY RECOGNIZING THE VISUAL FOOTER LINE
# ============================================================
def extract_pdf_text(pdf_path):
    full_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_height = page.height
            page_width = page.width
            
            # Get all vector/drawing lines on this page
            lines = page.lines
            
            footer_line_y = None
            
            # Find horizontal lines drawn in the bottom region of the page
            for line in lines:
                is_horizontal = (line['top'] == line['bottom'] or abs(line['top'] - line['bottom']) < 1)
                is_in_bottom_region = line['top'] > (page_height * 0.65)
                is_long_enough = (line['x1'] - line['x0']) > 40
                
                if is_horizontal and is_in_bottom_region and is_long_enough:
                    # Capture the vertical position of the uppermost separator line
                    footer_line_y = line['top']
                    break

            if footer_line_y:
                # CROP THE PAGE: Keep everything from top (0) down to the physical separator line
                # Bounding box format: (x0, y0, x1, y1)
                cropped_page = page.within_bbox((0, 0, page_width, footer_line_y - 2))
                text = cropped_page.extract_text()
            else:
                # Fallback if a page does not have a physical separator line drawn
                text = page.extract_text()

            if text:
                full_text.append(text)

    return "\n".join(full_text)


# ============================================================
# CREATE REGULATION CHUNKS
# ============================================================
# def create_regulation_chunks(title, text):
#     chunks = []
#     text = clean_legal_text(text)

#     # ========================================================
#     # REMOVE INDEX / PREAMBLE
#     # ========================================================
#     start_match = re.search(
#         r'(CHAPTER\s+[IVXLC]+|SCHEDULE\s+[IVXLC0-9\-A-Z ]+)',
#         text,
#         re.IGNORECASE
#     )
#     if start_match:
#         text = text[start_match.start():]

#     # ========================================================
#     # CHAPTER / SCHEDULE DETECTION
#     # ========================================================
#     chapter_pattern = re.compile(
#         r'(CHAPTER\s+[IVXLC]+)\s*\n([^\n]+)',
#         re.MULTILINE
#     )

#     schedule_pattern = re.compile(
#         r'^\s*(SCHEDULE\s+[IVXLC0-9\-A-Z ]+)'
#         r'(?:\s*\n([^\n]+))?',
#         re.MULTILINE
#     )
#     chapter_matches = []

#     for m in chapter_pattern.finditer(text):
#         chapter_matches.append({"match": m, "is_schedule": False})

#     for m in schedule_pattern.finditer(text):
#         chapter_matches.append({"match": m, "is_schedule": True})

#     # Sort by position
#     chapter_matches = sorted(
#         chapter_matches,
#         key=lambda x: x["match"].start()
#     )

#     if not chapter_matches:
#         chapter_matches = [None]

#     # ========================================================
#     # PROCESS CHAPTERS / SCHEDULES
#     # ========================================================
#     for idx in range(len(chapter_matches)):
#         if chapter_matches[idx]:
#             current_match = chapter_matches[idx]["match"]
#             is_schedule = chapter_matches[idx]["is_schedule"]
#             ch_start = current_match.start()
#             ch_end = (
#                 chapter_matches[idx + 1]["match"].start()
#                 if idx + 1 < len(chapter_matches)
#                 else len(text)
#             )

#             chapter_text = text[ch_start:ch_end]
#             chapter = current_match.group(1).strip()
#             chapter_title = (
#                 current_match.group(2).strip()
#                 if current_match.group(2)
#                 else ""
#             )
#         else:
#             chapter_text = text
#             chapter = None
#             chapter_title = None
#             is_schedule = False

#         # ====================================================
#         # REGULATION / PARAGRAPH DETECTION
#         # ====================================================
#         if is_schedule:
#             regulation_pattern = re.compile(
#                 r'\n([A-Z0-9\-]+(?:\.[A-Z0-9]+)?|[IVXLC]+|PART\s+[A-Z])\.\s+(.*?)(?=\n)',
#                 re.MULTILINE | re.IGNORECASE
#             )
#         else:
#             regulation_pattern = re.compile(
#                 r'(?:(?<=\n)([^\n]+)\n)?^(\d+[A-Z\-]*)\.\s+',
#                 re.MULTILINE
#             )

#         regulation_matches = []
#         for m in regulation_pattern.finditer(chapter_text):
#             if is_schedule:
#                 regulation_matches.append({
#                     "start": m.start(),
#                     "section": m.group(1).strip(),
#                     "inferred_heading": m.group(2).strip()
#                 })
#             else:
#                 raw_heading = m.group(1).strip() if m.group(1) else ""
#                 if any(x in raw_heading.lower() for x in ["chapter", "schedule", "provided that", "page"]):
#                     raw_heading = ""

#                 regulation_matches.append({
#                     "start": m.start(),
#                     "section": m.group(2).strip(),
#                     "inferred_heading": raw_heading
#                 })

#         if is_schedule and not regulation_matches:
#             clean_fallback_text = re.sub(r'\s*\n\s*', ' ', chapter_text).strip()
#             chunks.append({
#                 "title": title,
#                 "chapter": chapter,
#                 "chapter_title": chapter_title,
#                 "section": "FULL",
#                 "section_heading": chapter_title,
#                 "footer_reference": [],
#                 "text": clean_fallback_text
#             })
#             continue

#         # ====================================================
#         # PROCESS REGULATIONS / SECTIONS
#         # ====================================================
#         for r_idx in range(len(regulation_matches)):
#             r_start = regulation_matches[r_idx]["start"]
#             r_end = (
#                 regulation_matches[r_idx + 1]["start"]
#                 if r_idx + 1 < len(regulation_matches)
#                 else len(chapter_text)
#             )

#             regulation_block = chapter_text[r_start:r_end].strip()
#             section = regulation_matches[r_idx]["section"]
#             regulation_heading = regulation_matches[r_idx]["inferred_heading"].strip()

#             # Extract Footnote reference numbers from the text block
#             footer_refs = re.findall(r'\b(\d+)(?=\[)', regulation_block)
#             footer_refs = sorted(list(set([int(x) for x in footer_refs])))

#             regulation_text = regulation_block
            
#             if regulation_heading and regulation_text.startswith(regulation_heading):
#                 regulation_text = regulation_text[len(regulation_heading):].strip()

#             if regulation_text.startswith(section):
#                 prefix_len = len(section) + 1
#                 regulation_text = regulation_text[prefix_len:].strip()

#             # Flatten layout breaks and spaces
#             regulation_text = re.sub(r'\s*\n\s*', ' ', regulation_text)
#             regulation_text = re.sub(r'[ \t]+', ' ', regulation_text).strip()
            
#             regulation_heading = re.sub(r'\s*\n\s*', ' ', regulation_heading)
#             regulation_heading = re.sub(r'[ \t]+', ' ', regulation_heading).strip()

#             if not regulation_heading:
#                 regulation_heading = regulation_text[:60] + "..." if len(regulation_text) > 60 else regulation_text

#             chunks.append({
#                 "title": title,
#                 "chapter": chapter,
#                 "chapter_title": chapter_title,
#                 "section": section,
#                 "section_heading": regulation_heading,
#                 "footer_reference": footer_refs,
#                 "text": regulation_text
#             })

#     return chunks

def create_regulation_chunks(title, text):
    chunks = []
    text = clean_legal_text(text)

    # ========================================================
    # REMOVE INDEX / PREAMBLE
    # ========================================================
    start_match = re.search(
        r'(CHAPTER\s+[IVXLC]+|SCHEDULE\s+[IVXLC0-9\-A-Z ]+)',
        text,
        re.IGNORECASE
    )
    if start_match:
        text = text[start_match.start():]

    # ========================================================
    # CHAPTER / SCHEDULE DETECTION
    # ========================================================
    chapter_pattern = re.compile(
        r'(CHAPTER\s+[IVXLC]+)\s*\n([^\n]+)',
        re.MULTILINE
    )

    schedule_pattern = re.compile(
        r'^\s*(SCHEDULE\s+[IVXLC0-9\-A-Z ]+)'
        r'(?:\s*\n([^\n]+))?',
        re.MULTILINE
    )
    chapter_matches = []

    for m in chapter_pattern.finditer(text):
        chapter_matches.append({"match": m, "is_schedule": False})

    for m in schedule_pattern.finditer(text):
        chapter_matches.append({"match": m, "is_schedule": True})

    # Sort by position
    chapter_matches = sorted(
        chapter_matches,
        key=lambda x: x["match"].start()
    )

    if not chapter_matches:
        chapter_matches = [None]

    # ========================================================
    # PROCESS CHAPTERS / SCHEDULES
    # ========================================================
    for idx in range(len(chapter_matches)):
        if chapter_matches[idx]:
            current_match = chapter_matches[idx]["match"]
            is_schedule = chapter_matches[idx]["is_schedule"]
            ch_start = current_match.start()
            ch_end = (
                chapter_matches[idx + 1]["match"].start()
                if idx + 1 < len(chapter_matches)
                else len(text)
            )

            chapter_text = text[ch_start:ch_end]
            chapter = current_match.group(1).strip()
            chapter_title = (
                current_match.group(2).strip()
                if current_match.group(2)
                else ""
            )
        else:
            chapter_text = text
            chapter = None
            chapter_title = None
            is_schedule = False

        # ====================================================
        # REGULATION / PARAGRAPH DETECTION
        # ====================================================
        if is_schedule:
            regulation_pattern = re.compile(
                r'\n([A-Z0-9\-]+(?:\.[A-Z0-9]+)?|[IVXLC]+|PART\s+[A-Z])\.\s+(.*?)(?=\n)',
                re.MULTILINE | re.IGNORECASE
            )
        else:
            regulation_pattern = re.compile(
                r'(?:(?<=\n)([^\n]+)\n)?^(\d+[A-Z\-]*)\.\s+',
                re.MULTILINE
            )

        regulation_matches = []
        for m in regulation_pattern.finditer(chapter_text):
            if is_schedule:
                regulation_matches.append({
                    "start": m.start(),
                    "section": m.group(1).strip(),
                    "inferred_heading": m.group(2).strip()
                })
            else:
                raw_heading = m.group(1).strip() if m.group(1) else ""
                if any(x in raw_heading.lower() for x in ["chapter", "schedule", "provided that", "page"]):
                    raw_heading = ""

                regulation_matches.append({
                    "start": m.start(),
                    "section": m.group(2).strip(),
                    "inferred_heading": raw_heading
                })

        if is_schedule and not regulation_matches:
            clean_fallback_text = re.sub(r'\s*\n\s*', ' ', chapter_text).strip()
            chunks.append({
                "title": title,
                "chapter": chapter,
                "chapter_title": chapter_title,
                "section": "FULL",
                "section_heading": chapter_title,
                "footer_reference": [],
                "text": clean_fallback_text
            })
            continue

        # ====================================================
        # PROCESS REGULATIONS / SECTIONS
        # ====================================================
        for r_idx in range(len(regulation_matches)):
            r_start = regulation_matches[r_idx]["start"]
            r_end = (
                regulation_matches[r_idx + 1]["start"]
                if r_idx + 1 < len(regulation_matches)
                else len(chapter_text)
            )

            regulation_block = chapter_text[r_start:r_end].strip()
            section = regulation_matches[r_idx]["section"]
            regulation_heading = regulation_matches[r_idx]["inferred_heading"].strip()

            # Extract Footnote reference numbers
            footer_refs = re.findall(r'\b(\d+)(?=\[)', regulation_block)
            footer_refs = sorted(list(set([int(x) for x in footer_refs])))

            regulation_text = regulation_block
            
            if regulation_heading and regulation_text.startswith(regulation_heading):
                regulation_text = regulation_text[len(regulation_heading):].strip()

            if regulation_text.startswith(section):
                prefix_len = len(section) + 1
                regulation_text = regulation_text[prefix_len:].strip()

            # =================================================
            # FIX: SURGICAL REMOVAL OF INTERLEAVED FOOTNOTE JUNK
            # =================================================
            # This regex isolates the trailing bracket of text and matches the entire leaked
            # footnote explanation up until the next valid bracketed clause block like 408[(2A) or (3)
            regulation_text = re.sub(
                r'(?<=\])\s*(?:Requirements\)|Regulations\)|Second|Amendment|w\.e\.f\.|Prior to its substitution|Read as under:).*?(?=\s*(?:\d+\[)?\(\d+[A-Z]*\))',
                ' ',
                regulation_text,
                flags=re.IGNORECASE | re.DOTALL
            )

            # Flatten leftover formatting layout artifacts
            regulation_text = re.sub(r'\s*\n\s*', ' ', regulation_text)
            regulation_text = re.sub(r'[ \t]+', ' ', regulation_text).strip()
            
            regulation_heading = re.sub(r'\s*\n\s*', ' ', regulation_heading)
            regulation_heading = re.sub(r'[ \t]+', ' ', regulation_heading).strip()

            if not regulation_heading:
                regulation_heading = regulation_text[:60] + "..." if len(regulation_text) > 60 else regulation_text

            chunks.append({
                "title": title,
                "chapter": chapter,
                "chapter_title": chapter_title,
                "section": section,
                "section_heading": regulation_heading,
                "footer_reference": footer_refs,
                "text": regulation_text
            })

    return chunks
# ============================================================
# MAIN RUNNER
# ============================================================
if __name__ == "__main__":
    PDF_PATH = "/Users/admin/Downloads/1777351317428.pdf"
    TITLE = "SEBI Listing Obligations and Disclosure Requirements Regulations"

    print("Extracting text and isolating layout visual boundaries...")
    text = extract_pdf_text(PDF_PATH)

    print("Generating schema regulation chunks...")
    chunks = create_regulation_chunks(title=TITLE, text=text)

    with open("regulation_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=4, ensure_ascii=False)

    print(f"Success! Created {len(chunks)} text-clean regulation chunks.")